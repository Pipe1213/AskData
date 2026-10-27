from app.schemas.query import ConversationMessage, MemoryContext, QueryPlan
from app.services.business_vocabulary import (
    AVERAGE_WORDS,
    COMPARISON_WORDS,
    CONCEPTS,
    COUNT_WORDS,
    TIME_WORDS,
    TOPK_WORDS,
    concepts_in,
    has_money_intent,
)
from app.utils.text import significant_tokens

SCHEMA_TOKENS = {"schema", "table", "tables", "column", "columns"}
REFERENTIAL_TOKENS = {
    "that",
    "those",
    "them",
    "it",
    "now",
    "same",
    "previous",
    "above",
    "instead",
    "only",
    "also",
}


class PlannerService:
    def build_plan(
        self,
        question: str,
        conversation_context: list[ConversationMessage] | None = None,
        memory_context: MemoryContext | None = None,
    ) -> QueryPlan:
        normalized_question = question.strip()
        question_tokens = significant_tokens(normalized_question)
        memory_summary = self._build_memory_summary(conversation_context, memory_context)

        task_type = self._classify_task_type(normalized_question, question_tokens, conversation_context or [])
        metric_targets = self._metric_targets(question_tokens)
        dimension_targets = self._dimension_targets(question_tokens)
        time_targets = self._time_targets(question_tokens)
        candidate_table_families = self._candidate_table_families(question_tokens)
        metric_targets, dimension_targets, time_targets, candidate_table_families = self._apply_memory_context(
            task_type=task_type,
            question_tokens=question_tokens,
            metric_targets=metric_targets,
            dimension_targets=dimension_targets,
            time_targets=time_targets,
            candidate_table_families=candidate_table_families,
            memory_context=memory_context,
        )
        ambiguity_notes = self._ambiguity_notes(task_type, question_tokens, metric_targets, dimension_targets)
        confidence = self._confidence(task_type, ambiguity_notes, question_tokens)
        retry_guidance = self._retry_guidance(task_type, confidence, time_targets)

        return QueryPlan(
            task_type=task_type,
            execution_strategy="schema_guided" if task_type == "schema_lookup" else "single_query",
            interpreted_goal=self._interpreted_goal(normalized_question, task_type),
            metric_targets=metric_targets,
            dimension_targets=dimension_targets,
            time_targets=time_targets,
            candidate_table_families=candidate_table_families,
            ambiguity_notes=ambiguity_notes,
            retry_guidance=retry_guidance,
            confidence=confidence,
            memory_summary=memory_summary,
            inherited_from_turn_ids=(
                memory_context.inherited_from_turn_ids
                if memory_context is not None
                else []
            ),
        )

    def should_retry_with_broader_retrieval(self, plan: QueryPlan) -> bool:
        return plan.execution_strategy == "single_query" and "broaden_retrieval" in plan.retry_guidance

    def _classify_task_type(
        self,
        normalized_question: str,
        question_tokens: set[str],
        conversation_context: list[ConversationMessage],
    ) -> str:
        split_terms = set(normalized_question.lower().split())
        if question_tokens & SCHEMA_TOKENS and {"contain", "contains", "where", "which"} & split_terms:
            return "schema_lookup"
        if conversation_context and (len(question_tokens) <= 4 or split_terms & REFERENTIAL_TOKENS):
            return "follow_up_refinement"
        if question_tokens & COMPARISON_WORDS:
            return "comparison"
        if question_tokens & TOPK_WORDS:
            return "ranking"
        if question_tokens & TIME_WORDS:
            return "trend"
        if question_tokens & (COUNT_WORDS | AVERAGE_WORDS) or has_money_intent(question_tokens):
            return "aggregation"
        if len(question_tokens) <= 2:
            return "ambiguous"
        return "lookup"

    def _metric_targets(self, question_tokens: set[str]) -> list[str]:
        metric_targets: list[str] = []
        if has_money_intent(question_tokens):
            metric_targets.extend(sorted(CONCEPTS["money"].name_words - {"payment", "invoice"}))
        if question_tokens & COUNT_WORDS:
            metric_targets.append("count")
        if question_tokens & AVERAGE_WORDS:
            metric_targets.extend(["avg", "average"])
        return list(dict.fromkeys(metric_targets))

    def _dimension_targets(self, question_tokens: set[str]) -> list[str]:
        dimension_targets: list[str] = []
        for concept in concepts_in(question_tokens):
            if concept.is_measure:
                continue
            dimension_targets.extend(sorted(concept.name_words))
        if dimension_targets:
            dimension_targets.append("name")
        return list(dict.fromkeys(dimension_targets))

    def _time_targets(self, question_tokens: set[str]) -> list[str]:
        """The time words the question uses; retrieval matches them to date and timestamp columns."""
        return sorted(question_tokens & TIME_WORDS)

    def _candidate_table_families(self, question_tokens: set[str]) -> list[str]:
        """Words likely to appear in the names of the tables the question needs."""
        families: list[str] = []
        for concept in concepts_in(question_tokens):
            families.extend(sorted(concept.name_words))
        return list(dict.fromkeys(families))

    def _ambiguity_notes(
        self,
        task_type: str,
        question_tokens: set[str],
        metric_targets: list[str],
        dimension_targets: list[str],
    ) -> list[str]:
        notes: list[str] = []
        if task_type == "ambiguous":
            notes.append("The question is short and may need more business context.")
        if not metric_targets and question_tokens & (TOPK_WORDS | COMPARISON_WORDS):
            notes.append("The ranking or comparison intent is clear, but the business metric is not explicit.")
        if not dimension_targets and (question_tokens & (TOPK_WORDS | COMPARISON_WORDS) or has_money_intent(question_tokens)):
            notes.append("The likely grouping dimension is not explicit.")
        return notes

    def _confidence(
        self,
        task_type: str,
        ambiguity_notes: list[str],
        question_tokens: set[str],
    ) -> str:
        if task_type == "ambiguous" or len(ambiguity_notes) > 1:
            return "low"
        if task_type in {"follow_up_refinement", "comparison", "trend"} or len(question_tokens) <= 4:
            return "medium"
        return "high"

    def _retry_guidance(
        self,
        task_type: str,
        confidence: str,
        time_targets: list[str],
    ) -> list[str]:
        guidance: list[str] = []
        if task_type != "schema_lookup" and (confidence != "high" or task_type in {"follow_up_refinement", "comparison", "trend"}):
            guidance.append("broaden_retrieval")
        if task_type in {"follow_up_refinement", "comparison", "trend"}:
            guidance.append("semantic_rewrite")
        if task_type == "follow_up_refinement" or (task_type != "schema_lookup" and time_targets):
            guidance.append("retry_no_rows_with_broader_focus")
        return guidance

    def _interpreted_goal(self, question: str, task_type: str) -> str:
        if task_type == "schema_lookup":
            return "Identify the most relevant schema area before answering."
        if task_type == "follow_up_refinement":
            return "Refine the previous successful analysis using the latest instruction."
        if task_type == "ranking":
            return "Return a ranked analytical answer using the strongest matching business metric."
        if task_type == "trend":
            return "Summarize how the requested metric changes over time."
        if task_type == "comparison":
            return "Compare the requested metric across the most likely grouping dimension."
        if task_type == "aggregation":
            return "Aggregate the requested business metric and return a direct analytical answer."
        if task_type == "ambiguous":
            return "Answer conservatively because the request is underspecified."
        return f"Answer the user's business question: {question}"

    def _apply_memory_context(
        self,
        task_type: str,
        question_tokens: set[str],
        metric_targets: list[str],
        dimension_targets: list[str],
        time_targets: list[str],
        candidate_table_families: list[str],
        memory_context: MemoryContext | None,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        if memory_context is None:
            return metric_targets, dimension_targets, time_targets, candidate_table_families

        should_inherit = task_type == "follow_up_refinement" or len(question_tokens) <= 4
        if not should_inherit:
            return metric_targets, dimension_targets, time_targets, candidate_table_families

        explicit_dimension_shift = bool(question_tokens & TIME_WORDS) or any(
            not concept.is_measure for concept in concepts_in(question_tokens)
        )
        explicit_time_shift = bool(question_tokens & TIME_WORDS)

        if not metric_targets:
            metric_targets = list(memory_context.suggested_metric_targets)
        if not dimension_targets and not explicit_time_shift:
            dimension_targets = list(memory_context.suggested_dimension_targets)
        if not time_targets and not explicit_dimension_shift:
            time_targets = list(memory_context.suggested_time_targets)
        if not candidate_table_families:
            candidate_table_families = list(memory_context.suggested_table_families)

        return metric_targets, dimension_targets, time_targets, candidate_table_families

    def _build_memory_summary(
        self,
        conversation_context: list[ConversationMessage] | None,
        memory_context: MemoryContext | None,
    ) -> str | None:
        if memory_context is not None and memory_context.memory_summary:
            return memory_context.memory_summary
        if not conversation_context:
            return None

        recent_messages = conversation_context[-4:]
        parts = [
            f"{message.role}: {message.content.strip()[:140]}"
            for message in recent_messages
            if message.content.strip()
        ]
        if not parts:
            return None

        return " | ".join(parts)
