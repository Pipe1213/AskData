from app.schemas.query import ConversationMessage, QueryPlan
from app.utils.text import significant_tokens

REVENUE_TOKENS = {"revenue", "sale", "sales", "spend", "spent", "earning", "earnings"}
CATEGORY_TOKENS = {"category", "genre"}
CUSTOMER_TOKENS = {"customer", "customers", "buyer", "buyers"}
STAFF_TOKENS = {"staff", "employee", "employees"}
RENTAL_TOKENS = {"rental", "rentals", "rented", "rent"}
TIME_TOKENS = {"date", "dates", "trend", "monthly", "month", "daily", "yearly", "time", "year", "day"}
COUNT_TOKENS = {"count", "counts", "number", "many"}
AVERAGE_TOKENS = {"average", "avg", "mean"}
COMPARISON_TOKENS = {"compare", "comparison", "versus", "vs"}
TOPK_TOKENS = {"top", "highest", "most", "best"}
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
    ) -> QueryPlan:
        normalized_question = question.strip()
        question_tokens = significant_tokens(normalized_question)
        memory_summary = self._build_memory_summary(conversation_context)

        task_type = self._classify_task_type(normalized_question, question_tokens, conversation_context or [])
        metric_targets = self._metric_targets(question_tokens)
        dimension_targets = self._dimension_targets(question_tokens)
        time_targets = self._time_targets(question_tokens)
        candidate_table_families = self._candidate_table_families(question_tokens)
        ambiguity_notes = self._ambiguity_notes(task_type, question_tokens, metric_targets, dimension_targets)
        confidence = self._confidence(task_type, ambiguity_notes, question_tokens)

        return QueryPlan(
            task_type=task_type,
            execution_strategy="schema_guided" if task_type == "schema_lookup" else "single_query",
            interpreted_goal=self._interpreted_goal(normalized_question, task_type),
            metric_targets=metric_targets,
            dimension_targets=dimension_targets,
            time_targets=time_targets,
            candidate_table_families=candidate_table_families,
            ambiguity_notes=ambiguity_notes,
            confidence=confidence,
            memory_summary=memory_summary,
        )

    def should_retry_with_broader_retrieval(self, plan: QueryPlan) -> bool:
        if plan.execution_strategy != "single_query":
            return False
        return plan.confidence != "high" or plan.task_type in {"follow_up_refinement", "comparison", "trend"}

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
        if question_tokens & COMPARISON_TOKENS:
            return "comparison"
        if question_tokens & TOPK_TOKENS:
            return "ranking"
        if question_tokens & TIME_TOKENS:
            return "trend"
        if question_tokens & (COUNT_TOKENS | AVERAGE_TOKENS | REVENUE_TOKENS):
            return "aggregation"
        if len(question_tokens) <= 2:
            return "ambiguous"
        return "lookup"

    def _metric_targets(self, question_tokens: set[str]) -> list[str]:
        metric_targets: list[str] = []
        if question_tokens & REVENUE_TOKENS:
            metric_targets.extend(["amount", "revenue", "total_spent", "total_revenue"])
        if question_tokens & COUNT_TOKENS:
            metric_targets.extend(["count", "rental_count", "payment_count"])
        if question_tokens & AVERAGE_TOKENS:
            metric_targets.extend(["avg", "average"])
        return list(dict.fromkeys(metric_targets))

    def _dimension_targets(self, question_tokens: set[str]) -> list[str]:
        dimension_targets: list[str] = []
        if question_tokens & CUSTOMER_TOKENS:
            dimension_targets.extend(["customer", "customer_id", "first_name", "last_name"])
        if question_tokens & STAFF_TOKENS:
            dimension_targets.extend(["staff", "staff_id", "first_name", "last_name"])
        if question_tokens & CATEGORY_TOKENS:
            dimension_targets.extend(["category", "name", "category_id"])
        if question_tokens & RENTAL_TOKENS:
            dimension_targets.extend(["rental", "inventory", "film"])
        return list(dict.fromkeys(dimension_targets))

    def _time_targets(self, question_tokens: set[str]) -> list[str]:
        if not question_tokens & TIME_TOKENS:
            return []
        return ["payment_date", "rental_date", "month", "year"]

    def _candidate_table_families(self, question_tokens: set[str]) -> list[str]:
        families: list[str] = []
        if question_tokens & REVENUE_TOKENS:
            families.append("payment")
        if question_tokens & CUSTOMER_TOKENS:
            families.append("customer")
        if question_tokens & STAFF_TOKENS:
            families.append("staff")
        if question_tokens & RENTAL_TOKENS:
            families.append("rental")
        if question_tokens & CATEGORY_TOKENS:
            families.extend(["category", "film_category"])
        if question_tokens & TIME_TOKENS and "rental" not in families:
            families.append("rental")
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
        if not metric_targets and question_tokens & (TOPK_TOKENS | COMPARISON_TOKENS):
            notes.append("The ranking or comparison intent is clear, but the business metric is not explicit.")
        if not dimension_targets and question_tokens & (TOPK_TOKENS | COMPARISON_TOKENS | REVENUE_TOKENS):
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

    def _build_memory_summary(
        self,
        conversation_context: list[ConversationMessage] | None,
    ) -> str | None:
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
