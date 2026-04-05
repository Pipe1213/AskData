from app.schemas.query import MemoryContext, QueryResponse, TurnMemory
from app.schemas.session import SessionTurn
from app.utils.text import significant_tokens

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


class MemoryService:
    def build_turn_memory(
        self,
        response: QueryResponse,
        turn_id: str | None = None,
    ) -> TurnMemory:
        if response.memory is not None:
            return response.memory.model_copy(
                update={
                    "source_turn_id": turn_id or response.memory.source_turn_id,
                }
            )

        result_focus = self._build_result_focus(response)
        memory_tags = self._build_memory_tags(response, result_focus)

        return TurnMemory(
            source_turn_id=turn_id,
            question=response.question,
            task_type=response.plan.task_type if response.plan is not None else "lookup",
            interpreted_goal=(
                response.plan.interpreted_goal
                if response.plan is not None
                else response.answer_summary
            ),
            metric_targets=list(response.plan.metric_targets if response.plan is not None else []),
            dimension_targets=list(response.plan.dimension_targets if response.plan is not None else []),
            time_targets=list(response.plan.time_targets if response.plan is not None else []),
            candidate_table_families=list(
                response.plan.candidate_table_families if response.plan is not None else []
            ),
            used_tables=list(response.used_tables),
            generated_sql=response.generated_sql,
            answer_summary=response.answer_summary,
            row_count=response.row_count,
            result_focus=result_focus,
            memory_tags=memory_tags,
        )

    def build_memory_context(
        self,
        question: str,
        successful_turns: list[SessionTurn],
    ) -> MemoryContext | None:
        if not successful_turns:
            return None

        question_tokens = significant_tokens(question)
        referential = self._is_referential_follow_up(question, question_tokens)

        ranked_memories: list[tuple[float, TurnMemory]] = []
        for index, turn in enumerate(successful_turns):
            if turn.response is None:
                continue

            memory = self.build_turn_memory(turn.response, turn_id=turn.id)
            score = self._score_memory_match(
                memory=memory,
                question_tokens=question_tokens,
                is_latest=index == len(successful_turns) - 1,
                referential=referential,
            )
            ranked_memories.append((score, memory))

        ranked_memories.sort(
            key=lambda item: (
                -item[0],
                item[1].source_turn_id or "",
            )
        )
        selected = [memory for score, memory in ranked_memories if score > 0][:3]

        if not selected and referential:
            latest_successful = successful_turns[-1]
            if latest_successful.response is not None:
                selected = [
                    self.build_turn_memory(latest_successful.response, turn_id=latest_successful.id)
                ]

        if not selected:
            return None

        return MemoryContext(
            relevant_turn_memories=selected,
            memory_summary=" | ".join(
                memory.result_focus or memory.answer_summary[:120]
                for memory in selected
            )[:500],
            suggested_metric_targets=self._collect_unique(selected, "metric_targets"),
            suggested_dimension_targets=self._collect_unique(selected, "dimension_targets"),
            suggested_time_targets=self._collect_unique(selected, "time_targets"),
            suggested_table_families=self._collect_unique(selected, "candidate_table_families"),
            inherited_from_turn_ids=[
                memory.source_turn_id
                for memory in selected
                if memory.source_turn_id is not None
            ],
        )

    def _score_memory_match(
        self,
        memory: TurnMemory,
        question_tokens: set[str],
        is_latest: bool,
        referential: bool,
    ) -> float:
        overlap_score = 0.0
        memory_tokens = set(memory.memory_tags) | significant_tokens(memory.question)
        overlap_score += len(question_tokens & memory_tokens) * 3.0

        if question_tokens & set(memory.metric_targets):
            overlap_score += 4.0
        if question_tokens & set(memory.dimension_targets):
            overlap_score += 3.5
        if question_tokens & set(memory.time_targets):
            overlap_score += 3.0
        if question_tokens & set(memory.candidate_table_families):
            overlap_score += 3.0

        score = overlap_score
        if referential and is_latest:
            score += 6.0
        elif is_latest and overlap_score > 0:
            score += 1.5

        return score

    def _build_result_focus(self, response: QueryResponse) -> str | None:
        if response.row_count == 0:
            return "Previous query returned no matching rows."

        if response.rows and response.columns:
            first_row = response.rows[0]
            parts = [
                f"{column}={value}"
                for column, value in zip(response.columns[:3], first_row[:3], strict=False)
            ]
            if parts:
                return f"Previous result focus: {', '.join(parts)}."

        return response.answer_summary[:160]

    def _build_memory_tags(
        self,
        response: QueryResponse,
        result_focus: str | None,
    ) -> list[str]:
        tags = set()
        tags.update(significant_tokens(response.question))
        tags.update(response.plan.metric_targets if response.plan is not None else [])
        tags.update(response.plan.dimension_targets if response.plan is not None else [])
        tags.update(response.plan.time_targets if response.plan is not None else [])
        tags.update(response.plan.candidate_table_families if response.plan is not None else [])
        tags.update(table.split(".")[-1] for table in response.used_tables)
        if result_focus:
            tags.update(significant_tokens(result_focus))
        return sorted(tag for tag in tags if tag)

    def _collect_unique(self, memories: list[TurnMemory], field_name: str) -> list[str]:
        collected: list[str] = []
        for memory in memories:
            for value in getattr(memory, field_name):
                if value not in collected:
                    collected.append(value)
        return collected

    def _is_referential_follow_up(self, question: str, question_tokens: set[str]) -> bool:
        if len(question_tokens) <= 3:
            return True
        return any(token in question.lower().split() for token in REFERENTIAL_TOKENS)
