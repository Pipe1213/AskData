from app.core.config import Settings, get_settings
from app.llm.base import BaseLLMClient, LLMClientError
from app.llm.openai_client import OpenAILLMClient
from app.llm.prompt_builders import build_answer_summary_messages
from app.llm.response_models import LLMGenerationConfig, LLMMessage
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import ChartRecommendation, QueryResponse


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
    ) -> QueryResponse:
        if not execution_result.success:
            raise ValueError("Execution result must be successful before formatting a query response.")

        merged_warnings = list(warnings or [])
        merged_warnings.extend(execution_result.warnings)

        return QueryResponse(
            question=question,
            answer_summary=self._build_answer_summary(
                question=question,
                generated_sql=generated_sql,
                execution_result=execution_result,
            ),
            generated_sql=generated_sql,
            columns=execution_result.columns,
            rows=execution_result.rows,
            chart_recommendation=self._recommend_chart(execution_result),
            warnings=merged_warnings,
            used_tables=sorted(set(used_tables)),
        )

    def _build_answer_summary(
        self,
        question: str,
        generated_sql: str,
        execution_result: SQLExecutionResult,
    ) -> str:
        llm_client = self._get_llm_client()
        if llm_client is None:
            return self._fallback_summary(execution_result)

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
            if response.text.strip():
                return response.text.strip()
        except LLMClientError:
            pass

        return self._fallback_summary(execution_result)

    def _get_llm_client(self) -> BaseLLMClient | None:
        if self.llm_client is not None:
            return self.llm_client

        if not self.settings.openai_api_key:
            return None

        self.llm_client = OpenAILLMClient(self.settings)
        return self.llm_client

    def _fallback_summary(self, execution_result: SQLExecutionResult) -> str:
        if execution_result.row_count == 0:
            return "The query returned no rows."

        if execution_result.row_count == 1 and execution_result.columns:
            value_parts = [
                f"{column}={value}"
                for column, value in zip(
                    execution_result.columns,
                    execution_result.rows[0],
                    strict=False,
                )
            ]
            return "The query returned one row: " + ", ".join(value_parts) + "."

        return (
            f"The query returned {execution_result.row_count} rows "
            f"across {len(execution_result.columns)} columns."
        )

    def _recommend_chart(
        self,
        execution_result: SQLExecutionResult,
    ) -> ChartRecommendation:
        columns = execution_result.columns
        rows = execution_result.rows

        if len(columns) < 2 or not rows:
            return ChartRecommendation(type="table_only")

        x_index = 0
        y_index = self._find_numeric_column_index(rows)
        if y_index is None or y_index == x_index:
            return ChartRecommendation(type="table_only")

        x_column = columns[x_index]
        y_column = columns[y_index]

        if self._looks_like_time_column(x_column):
            return ChartRecommendation(type="line", x=x_column, y=y_column)

        return ChartRecommendation(type="bar", x=x_column, y=y_column)

    def _find_numeric_column_index(self, rows: list[list[object]]) -> int | None:
        if not rows:
            return None

        first_row = rows[0]
        for index, value in enumerate(first_row):
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return index

        return None

    def _looks_like_time_column(self, column_name: str) -> bool:
        normalized_name = column_name.lower()
        return any(token in normalized_name for token in ("date", "time", "month", "year", "day"))
