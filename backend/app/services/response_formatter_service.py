from datetime import date, datetime
from numbers import Number

from app.core.config import Settings, get_settings
from app.llm.base import BaseLLMClient, LLMClientError
from app.llm.openai_client import OpenAILLMClient
from app.llm.prompt_builders import build_answer_summary_messages
from app.llm.response_models import LLMGenerationConfig, LLMMessage
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import (
    ChartRecommendation,
    PrimaryArtifact,
    QueryPlan,
    QueryResponse,
    QueryTrace,
    TurnMemory,
)
from app.utils.text import significant_tokens


class ResponseFormatterService:
    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    def format_query_response(
        self,
        question: str,
        generated_sql: str,
        execution_result: SQLExecutionResult,
        used_tables: list[str],
        warnings: list[str] | None = None,
        repaired: bool = False,
        plan: QueryPlan | None = None,
        trace: QueryTrace | None = None,
    ) -> QueryResponse:
        if not execution_result.success:
            raise ValueError("Execution result must be successful before formatting a query response.")

        merged_warnings = list(warnings or [])
        merged_warnings.extend(execution_result.warnings)
        answer_summary = self._build_answer_summary(
            question=question,
            generated_sql=generated_sql,
            execution_result=execution_result,
        )
        chart_recommendation = self._recommend_chart(question, execution_result)
        primary_artifact = self._primary_artifact(
            question=question,
            execution_result=execution_result,
            chart_recommendation=chart_recommendation,
            plan=plan,
        )
        turn_memory = self._build_turn_memory(
            question=question,
            generated_sql=generated_sql,
            execution_result=execution_result,
            used_tables=used_tables,
            answer_summary=answer_summary,
            plan=plan,
        )

        return QueryResponse(
            question=question,
            answer_summary=answer_summary,
            generated_sql=generated_sql,
            columns=execution_result.columns,
            rows=execution_result.rows,
            row_count=execution_result.row_count,
            chart_recommendation=chart_recommendation,
            warnings=merged_warnings,
            used_tables=sorted(set(used_tables)),
            repaired=repaired,
            primary_artifact=primary_artifact,
            memory=turn_memory,
            plan=plan,
            trace=trace,
        )

    def _build_answer_summary(
        self,
        question: str,
        generated_sql: str,
        execution_result: SQLExecutionResult,
    ) -> str:
        llm_client = self._get_llm_client()
        if llm_client is None:
            return self._fallback_summary(question, execution_result)

        try:
            messages = build_answer_summary_messages(
                question=question,
                generated_sql=generated_sql,
                columns=execution_result.columns,
                rows=execution_result.rows,
            )
            llm_messages = [LLMMessage.model_validate(message) for message in messages]
            response = llm_client.generate_text(
                messages=llm_messages,
                config=LLMGenerationConfig(
                    max_output_tokens=160,
                ),
            )
            summary = response.text.strip()
            if self._is_usable_summary(summary):
                return summary
        except LLMClientError:
            pass

        return self._fallback_summary(question, execution_result)

    def _get_llm_client(self) -> BaseLLMClient | None:
        if self.llm_client is not None:
            return self.llm_client

        if not self.settings.openai_api_key:
            return None

        self.llm_client = OpenAILLMClient(
            self.settings,
            model=self.settings.resolved_summary_model,
        )
        return self.llm_client

    def _fallback_summary(
        self,
        question: str,
        execution_result: SQLExecutionResult,
    ) -> str:
        question_tokens = significant_tokens(question)

        if execution_result.row_count == 0:
            return "The query ran successfully but returned no matching rows."

        if execution_result.row_count == 1 and len(execution_result.columns) == 1:
            value = self._format_value(
                execution_result.rows[0][0],
                execution_result.columns[0],
            )
            return f"The result is {value}."

        if execution_result.row_count == 1 and execution_result.columns:
            first_row = execution_result.rows[0]
            label_index = self._find_label_column_index(execution_result.columns, first_row)
            metric_index = self._find_numeric_column_index(
                rows=execution_result.rows,
                columns=execution_result.columns,
                preferred_after_index=label_index,
                question=question,
            )
            if label_index is not None and metric_index is not None:
                label = self._format_value(first_row[label_index], execution_result.columns[label_index])
                metric_label = self._humanize_column_name(execution_result.columns[metric_index])
                metric_value = self._format_value(first_row[metric_index], execution_result.columns[metric_index])
                return f"{label} has {metric_label} of {metric_value}."

        if execution_result.columns and execution_result.rows:
            first_row = execution_result.rows[0]
            label_index = self._find_label_column_index(
                execution_result.columns,
                first_row,
            )
            metric_index = self._find_numeric_column_index(
                rows=execution_result.rows,
                columns=execution_result.columns,
                preferred_after_index=label_index,
                question=question,
            )

            if (
                label_index is not None
                and metric_index is not None
                and label_index < len(first_row)
                and metric_index < len(first_row)
            ):
                if self._looks_like_time_column(execution_result.columns[label_index]):
                    peak_row = max(
                        execution_result.rows,
                        key=lambda row: self._numeric_sort_value(row[metric_index]),
                    )
                    peak_label = self._format_value(
                        peak_row[label_index],
                        execution_result.columns[label_index],
                    )
                    peak_value = self._format_value(
                        peak_row[metric_index],
                        execution_result.columns[metric_index],
                    )
                    metric_label = self._humanize_column_name(execution_result.columns[metric_index])
                    return f"The highest {metric_label} in the returned period was {peak_value} in {peak_label}."

                label = self._format_value(
                    first_row[label_index],
                    execution_result.columns[label_index],
                )
                metric_label = self._humanize_column_name(execution_result.columns[metric_index])
                metric_value = self._format_value(
                    first_row[metric_index],
                    execution_result.columns[metric_index],
                )

                if (
                    isinstance(first_row[label_index], Number)
                    and execution_result.columns[metric_index].lower().endswith("_id")
                ):
                    numeric_label = self._humanize_column_name(execution_result.columns[label_index])
                    return f"The highest {numeric_label} returned was {label}."

                if question_tokens & {"top", "highest", "most", "best"}:
                    return f"{label} is the top result with {metric_label} of {metric_value}."

                return f"{label} has {metric_label} of {metric_value}."

        return (
            f"The answer includes {execution_result.row_count} rows "
            f"across {len(execution_result.columns)} columns."
        )

    def _is_usable_summary(self, summary: str) -> bool:
        if len(summary) < 16:
            return False

        if len(summary.split()) < 4:
            return False

        normalized_summary = summary.lower()
        if normalized_summary.startswith("the query returned"):
            return False
        if "leading result was" in normalized_summary:
            return False

        return True

    def _recommend_chart(
        self,
        question: str,
        execution_result: SQLExecutionResult,
    ) -> ChartRecommendation:
        columns = execution_result.columns
        rows = execution_result.rows

        if len(columns) < 2 or not rows:
            return ChartRecommendation(type="table_only")

        if len(rows) < 2 or len(rows) > 24:
            return ChartRecommendation(type="table_only")

        x_index = self._find_label_column_index(columns, rows[0])
        if x_index is None:
            x_index = 0

        y_index = self._find_numeric_column_index(
            rows=rows,
            columns=columns,
            preferred_after_index=x_index,
            question=question,
        )
        if y_index is None or y_index == x_index:
            return ChartRecommendation(type="table_only")

        x_column = columns[x_index]
        y_column = columns[y_index]

        if self._looks_like_time_column(x_column):
            return ChartRecommendation(type="line", x=x_column, y=y_column)

        return ChartRecommendation(type="bar", x=x_column, y=y_column)

    def _find_numeric_column_index(
        self,
        rows: list[list[object]],
        columns: list[str] | None = None,
        preferred_after_index: int | None = None,
        question: str | None = None,
    ) -> int | None:
        if not rows:
            return None

        first_row = rows[0]
        candidate_indices = list(range(len(first_row)))
        question_tokens = significant_tokens(question or "")

        if preferred_after_index is not None:
            candidate_indices = [
                index for index in candidate_indices
                if index != preferred_after_index
            ]

        scored_candidates: list[tuple[float, int]] = []
        for index in candidate_indices:
            value = first_row[index]
            if isinstance(value, bool):
                continue
            if isinstance(value, Number):
                score = 0.0
                if columns is not None:
                    score += self._metric_column_score(columns[index], question_tokens)
                    if not columns[index].lower().endswith("_id"):
                        score += 1.0
                scored_candidates.append((score, index))

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda item: (-item[0], item[1]))
        return scored_candidates[0][1]

    def _find_label_column_index(
        self,
        columns: list[str],
        first_row: list[object],
    ) -> int | None:
        for index, value in enumerate(first_row):
            if isinstance(value, str) and value.strip():
                return index

        for index, column_name in enumerate(columns):
            if not column_name.lower().endswith("_id"):
                return index

        return None

    def _looks_like_time_column(self, column_name: str) -> bool:
        normalized_name = column_name.lower()
        return any(token in normalized_name for token in ("date", "time", "month", "year", "day"))

    def _metric_column_score(self, column_name: str, question_tokens: set[str]) -> float:
        normalized_name = column_name.lower()
        score = 0.0

        if normalized_name.endswith("_id"):
            score -= 8.0

        revenue_tokens = {"revenue", "sale", "sales", "spend", "spent", "earning", "earnings"}
        count_tokens = {"count", "counts", "number", "many"}
        average_tokens = {"average", "avg", "mean"}

        if question_tokens & revenue_tokens:
            if any(token in normalized_name for token in ("revenue", "spent", "amount", "total", "sales")):
                score += 9.0
            if "count" in normalized_name:
                score += 1.5

        if question_tokens & count_tokens:
            if "count" in normalized_name:
                score += 8.0
            if any(token in normalized_name for token in ("total", "amount", "revenue")):
                score += 1.0

        if question_tokens & average_tokens:
            if any(token in normalized_name for token in ("avg", "average", "mean")):
                score += 8.0

        if question_tokens & {"rental", "rentals", "rented"} and "count" in normalized_name:
            score += 4.0

        if any(
            token in normalized_name
            for token in ("total", "revenue", "spent", "amount", "count", "avg", "average")
        ):
            score += 2.5

        return score

    def _primary_artifact(
        self,
        question: str,
        execution_result: SQLExecutionResult,
        chart_recommendation: ChartRecommendation,
        plan: QueryPlan | None,
    ) -> PrimaryArtifact:
        if execution_result.row_count == 0:
            return "summary"

        question_tokens = significant_tokens(question)
        chart_possible = (
            chart_recommendation.type != "table_only"
            and execution_result.row_count > 0
            and len(execution_result.rows) > 1
        )
        wants_table = bool(
            question_tokens
            & {"table", "list", "rows", "top", "show", "which", "customer", "customers", "category", "categories"}
        )
        wants_chart = bool(
            question_tokens
            & {"trend", "compare", "comparison", "monthly", "month", "yearly", "chart", "plot", "graph"}
        )

        if plan is not None and plan.task_type == "trend" and chart_possible:
            return "chart"
        if plan is not None and plan.task_type == "comparison" and chart_possible:
            return "chart_and_table"
        if wants_table and chart_possible and wants_chart:
            return "chart_and_table"
        if wants_table:
            return "table"
        if wants_chart and chart_possible:
            return "chart"
        if chart_possible and execution_result.row_count <= 12:
            return "chart_and_table"
        return "summary"

    def _build_turn_memory(
        self,
        question: str,
        generated_sql: str,
        execution_result: SQLExecutionResult,
        used_tables: list[str],
        answer_summary: str,
        plan: QueryPlan | None,
    ) -> TurnMemory:
        result_focus = self._fallback_summary(question, execution_result)
        memory_tags = set(significant_tokens(question))
        memory_tags.update(significant_tokens(answer_summary))
        memory_tags.update(significant_tokens(result_focus))
        if plan is not None:
            memory_tags.update(plan.metric_targets)
            memory_tags.update(plan.dimension_targets)
            memory_tags.update(plan.time_targets)
            memory_tags.update(plan.candidate_table_families)
        memory_tags.update(table.split(".")[-1] for table in used_tables)

        return TurnMemory(
            question=question,
            task_type=plan.task_type if plan is not None else "lookup",
            interpreted_goal=plan.interpreted_goal if plan is not None else answer_summary,
            metric_targets=list(plan.metric_targets if plan is not None else []),
            dimension_targets=list(plan.dimension_targets if plan is not None else []),
            time_targets=list(plan.time_targets if plan is not None else []),
            candidate_table_families=list(plan.candidate_table_families if plan is not None else []),
            used_tables=sorted(set(used_tables)),
            generated_sql=generated_sql,
            answer_summary=answer_summary,
            row_count=execution_result.row_count,
            result_focus=result_focus,
            memory_tags=sorted(tag for tag in memory_tags if tag),
        )

    def _numeric_sort_value(self, value: object) -> float:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, Number):
            return float(value)
        if isinstance(value, str):
            normalized = value.replace(",", "").strip()
            try:
                return float(normalized)
            except ValueError:
                return 0.0
        return 0.0

    def _format_value(self, value: object, column_name: str) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, Number):
            numeric_value = float(value)
            if numeric_value.is_integer():
                return f"{int(numeric_value):,}"
            return f"{numeric_value:,.2f}".rstrip("0").rstrip(".")
        if isinstance(value, (datetime, date)):
            return self._format_date_like(value.isoformat(), column_name)
        if isinstance(value, str):
            return self._format_date_like(value, column_name)
        return str(value)

    def _format_date_like(self, value: str, column_name: str) -> str:
        if not self._looks_like_time_column(column_name):
            return value

        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return value

        normalized_name = column_name.lower()
        if "month" in normalized_name:
            return parsed.strftime("%B %Y")
        if "year" in normalized_name and parsed.month == 1 and parsed.day == 1:
            return parsed.strftime("%Y")
        return parsed.strftime("%b %d, %Y")

    def _humanize_column_name(self, column_name: str) -> str:
        return column_name.replace("_", " ")
