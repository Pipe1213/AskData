from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.llm.usage import record_llm_usage
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import (
    ChartRecommendation,
    ConversationMessage,
    QueryPlan,
    QueryResponse,
    QueryTrace,
    SQLGenerationResult,
    SQLSemanticReviewResult,
)
from app.schemas.retrieval import RetrievedSchemaContext, RetrievedTable
from app.schemas.validation import SQLValidationResult
from app.services.query_pipeline_service import QueryPipelineService


class FakeRetrievalService:
    def __init__(self) -> None:
        self.last_question: str | None = None
        self.context = RetrievedSchemaContext(
            question="How much revenue by customer?",
            tables=[
                RetrievedTable(
                    schema_name="public",
                    table_name="payment",
                    full_name="public.payment",
                    score=10.0,
                )
            ],
            relationships=[],
            warnings=[],
        )

    def retrieve_schema_context(
        self,
        question: str,
        schema: DatabaseSchema,
        plan: QueryPlan | None = None,
        memory_context=None,
        dataset_adapter=None,
        max_tables: int = 5,
        max_columns_per_table: int = 8,
        broaden: bool = False,
    ) -> RetrievedSchemaContext:
        self.last_question = question
        return self.context


class FakeSQLGenerationService:
    def __init__(self) -> None:
        self.generated = [
            SQLGenerationResult(sql="SELECT FROM payment", used_tables=["public.payment"]),
            SQLGenerationResult(
                sql="SELECT customer_id, amount FROM payment",
                used_tables=["public.payment"],
                notes=[],
            ),
        ]
        self.generate_calls = 0
        self.repair_calls = 0
        self.review_calls = 0
        self.last_conversation_context = None

    def generate_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        conversation_context=None,
        plan: QueryPlan | None = None,
        memory_context=None,
        dataset_hints=None,
    ) -> SQLGenerationResult:
        self.generate_calls += 1
        self.last_conversation_context = conversation_context
        return self.generated[0]

    def repair_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        previous_sql: str,
        failure_message: str,
        conversation_context=None,
        plan: QueryPlan | None = None,
        memory_context=None,
        dataset_hints=None,
    ) -> SQLGenerationResult:
        self.repair_calls += 1
        self.last_conversation_context = conversation_context
        return self.generated[1]

    def review_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        generated_sql: str,
        conversation_context=None,
        plan: QueryPlan | None = None,
        memory_context=None,
        dataset_hints=None,
    ) -> SQLSemanticReviewResult:
        self.review_calls += 1
        self.last_conversation_context = conversation_context
        return SQLSemanticReviewResult(should_rewrite=False, issues=[])


class FakeSQLValidationService:
    def __init__(self) -> None:
        self.calls = 0

    def validate_sql(self, sql: str) -> SQLValidationResult:
        self.calls += 1
        if self.calls == 1:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=True,
                classification="repairable_failure",
                errors=["SQL could not be parsed."],
            )

        return SQLValidationResult(
            original_sql=sql,
            validated_sql=sql + " LIMIT 200",
            is_valid=True,
            can_repair=False,
            classification="valid",
            warnings=["Applied LIMIT 200 to constrain result size."],
            detected_tables=["payment"],
        )


class FakeSQLExecutionService:
    def execute_sql(
        self,
        validated_sql: str,
        connection_settings=None,
    ) -> SQLExecutionResult:
        del connection_settings
        return SQLExecutionResult(
            sql=validated_sql,
            success=True,
            columns=["customer_id", "amount"],
            rows=[[1, 10.0]],
            row_count=1,
            warnings=[],
        )


class FakeResponseFormatterService:
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
        assumptions: list[str] | None = None,
        data_coverage: list[str] | None = None,
    ) -> QueryResponse:
        self.last_data_coverage = data_coverage
        return QueryResponse(
            question=question,
            answer_summary="One repaired result row was returned.",
            assumptions=assumptions or [],
            generated_sql=generated_sql,
            columns=execution_result.columns,
            rows=execution_result.rows,
            row_count=execution_result.row_count,
            chart_recommendation=ChartRecommendation(type="table_only"),
            warnings=warnings or [],
            used_tables=used_tables,
            repaired=repaired,
            plan=plan,
            trace=trace,
        )


def test_query_pipeline_repairs_once_after_validation_failure(sample_schema) -> None:
    retrieval_service = FakeRetrievalService()
    generation_service = FakeSQLGenerationService()

    pipeline_service = QueryPipelineService(
        retrieval_service=retrieval_service,
        sql_generation_service=generation_service,
        sql_validation_service=FakeSQLValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query("How much revenue by customer?", sample_schema)

    assert generation_service.generate_calls == 1
    assert generation_service.review_calls == 1
    assert generation_service.repair_calls == 1
    assert "repaired once after a validation failure" in " ".join(response.warnings).lower()
    assert response.generated_sql.endswith("LIMIT 200")
    assert response.plan is not None
    assert response.trace is not None


def test_query_pipeline_rejects_hard_safety_failure(sample_schema) -> None:
    class HardFailValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=False,
                classification="hard_safety_failure",
                errors=["Unsafe SQL operation detected: Drop"],
            )

    retrieval_service = FakeRetrievalService()

    pipeline_service = QueryPipelineService(
        retrieval_service=retrieval_service,
        sql_generation_service=FakeSQLGenerationService(),
        sql_validation_service=HardFailValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    try:
        pipeline_service.run_query("How much revenue by customer?", sample_schema)
    except QueryPipelineError as exc:
        assert exc.code == "unsafe_sql"
        assert exc.retryable is False
    else:
        raise AssertionError("Expected QueryPipelineError for hard safety failure.")


def test_query_pipeline_canonicalizes_used_tables(sample_schema) -> None:
    class CanonicalGenerationService:
        def generate_sql(
            self,
            question: str,
            schema_context: RetrievedSchemaContext,
            conversation_context=None,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_hints=None,
        ) -> SQLGenerationResult:
            return SQLGenerationResult(
                sql="SELECT customer_id, amount FROM payment",
                used_tables=["payments", "public.customer", "all_payments"],
                notes=[],
            )

    class CanonicalValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                validated_sql=sql,
                is_valid=True,
                can_repair=False,
                classification="valid",
                warnings=[],
                detected_tables=["payment", "customer_counts"],
            )

    pipeline_service = QueryPipelineService(
        retrieval_service=FakeRetrievalService(),
        sql_generation_service=CanonicalGenerationService(),
        sql_validation_service=CanonicalValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query("How much revenue by customer?", sample_schema)

    assert response.used_tables == ["public.payment", "public.customer"]


def test_query_pipeline_uses_recent_context_for_referential_follow_up(sample_schema) -> None:
    retrieval_service = FakeRetrievalService()
    generation_service = FakeSQLGenerationService()

    class ValidatingSQLValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                validated_sql=sql,
                is_valid=True,
                can_repair=False,
                classification="valid",
                warnings=[],
                detected_tables=["payment"],
            )

    pipeline_service = QueryPipelineService(
        retrieval_service=retrieval_service,
        sql_generation_service=generation_service,
        sql_validation_service=ValidatingSQLValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    context = [
        ConversationMessage(
            role="user",
            content="Which customers spent the most in total?",
        ),
        ConversationMessage(
            role="assistant",
            content="The top customers by total payment amount were customer 1 and customer 2.",
        ),
    ]

    pipeline_service.run_query(
        "Now show only the top 5",
        sample_schema,
        conversation_context=context,
    )

    assert retrieval_service.last_question is not None
    assert "Context hints" in retrieval_service.last_question
    assert generation_service.last_conversation_context == context


def test_query_pipeline_rewrites_once_after_semantic_review(sample_schema) -> None:
    retrieval_service = FakeRetrievalService()

    class SemanticReviewGenerationService(FakeSQLGenerationService):
        def review_sql(
            self,
            question: str,
            schema_context: RetrievedSchemaContext,
            generated_sql: str,
            conversation_context=None,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_hints=None,
        ) -> SQLSemanticReviewResult:
            self.review_calls += 1
            return SQLSemanticReviewResult(
                should_rewrite=True,
                issues=["The SQL uses a count metric instead of spend."],
                suggested_focus="Use payment.amount as the primary metric.",
            )

    class ValidatingSQLValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                validated_sql=sql,
                is_valid=True,
                can_repair=False,
                classification="valid",
                warnings=[],
                detected_tables=["payment"],
            )

    generation_service = SemanticReviewGenerationService()
    pipeline_service = QueryPipelineService(
        retrieval_service=retrieval_service,
        sql_generation_service=generation_service,
        sql_validation_service=ValidatingSQLValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query("Which customers spent the most in total?", sample_schema)

    assert generation_service.generate_calls == 1
    assert generation_service.review_calls == 1
    assert generation_service.repair_calls == 1
    assert any("semantic review" in warning.lower() for warning in response.warnings)


def test_query_pipeline_retries_once_with_broader_retrieval_after_no_rows(sample_schema) -> None:
    class RetryAwareRetrievalService(FakeRetrievalService):
        def __init__(self) -> None:
            super().__init__()
            self.broaden_calls: list[bool] = []

        def retrieve_schema_context(
            self,
            question: str,
            schema: DatabaseSchema,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_adapter=None,
            max_tables: int = 5,
            max_columns_per_table: int = 8,
            broaden: bool = False,
        ) -> RetrievedSchemaContext:
            self.broaden_calls.append(broaden)
            return self.context

    class ValidSQLGenerationService(FakeSQLGenerationService):
        def generate_sql(
            self,
            question: str,
            schema_context: RetrievedSchemaContext,
            conversation_context=None,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_hints=None,
        ) -> SQLGenerationResult:
            self.generate_calls += 1
            return SQLGenerationResult(
                sql="SELECT customer_id, amount FROM payment",
                used_tables=["public.payment"],
                notes=[],
            )

    class ValidatingSQLValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                validated_sql=sql,
                is_valid=True,
                can_repair=False,
                classification="valid",
                warnings=[],
                detected_tables=["payment"],
            )

    class NoRowsThenRowsExecutionService:
        def __init__(self) -> None:
            self.calls = 0

        def execute_sql(
            self,
            validated_sql: str,
            connection_settings=None,
        ) -> SQLExecutionResult:
            del connection_settings
            self.calls += 1
            if self.calls == 1:
                return SQLExecutionResult(
                    sql=validated_sql,
                    success=True,
                    columns=["customer_id", "amount"],
                    rows=[],
                    row_count=0,
                    warnings=[],
                )
            return SQLExecutionResult(
                sql=validated_sql,
                success=True,
                columns=["customer_id", "amount"],
                rows=[[1, 10.0]],
                row_count=1,
                warnings=[],
            )

    retrieval_service = RetryAwareRetrievalService()
    pipeline_service = QueryPipelineService(
        retrieval_service=retrieval_service,
        sql_generation_service=ValidSQLGenerationService(),
        sql_validation_service=ValidatingSQLValidationService(),
        sql_execution_service=NoRowsThenRowsExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query(
        "Now show only the top 5",
        sample_schema,
        conversation_context=[
            ConversationMessage(role="user", content="Which customers spent the most in total?"),
            ConversationMessage(role="assistant", content="MARION led the ranking."),
        ],
    )

    assert retrieval_service.broaden_calls == [False, True]
    assert response.row_count == 1
    assert any("broader schema focus" in warning.lower() for warning in response.warnings)


def test_query_pipeline_rewrites_after_relative_time_no_rows(sample_schema) -> None:
    class StableRetrievalService(FakeRetrievalService):
        pass

    class RelativeTimeGenerationService(FakeSQLGenerationService):
        def generate_sql(
            self,
            question: str,
            schema_context: RetrievedSchemaContext,
            conversation_context=None,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_hints=None,
        ) -> SQLGenerationResult:
            self.generate_calls += 1
            return SQLGenerationResult(
                sql="SELECT rental_month, rental_count FROM rental WHERE EXTRACT(YEAR FROM rental_date) = EXTRACT(YEAR FROM CURRENT_DATE)",
                used_tables=["public.rental"],
                notes=[],
            )

        def repair_sql(
            self,
            question: str,
            schema_context: RetrievedSchemaContext,
            previous_sql: str,
            failure_message: str,
            conversation_context=None,
            plan: QueryPlan | None = None,
            memory_context=None,
            dataset_hints=None,
        ) -> SQLGenerationResult:
            self.repair_calls += 1
            return SQLGenerationResult(
                sql="SELECT rental_month, rental_count FROM rental WHERE EXTRACT(YEAR FROM rental_date) = 2022",
                used_tables=["public.rental"],
                notes=[],
            )

    class ValidatingSQLValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                validated_sql=sql,
                is_valid=True,
                can_repair=False,
                classification="valid",
                warnings=[],
                detected_tables=["rental"],
            )

    class NoRowsUntilRepairExecutionService:
        def execute_sql(
            self,
            validated_sql: str,
            connection_settings=None,
        ) -> SQLExecutionResult:
            del connection_settings
            if "2022" not in validated_sql:
                return SQLExecutionResult(
                    sql=validated_sql,
                    success=True,
                    columns=["rental_month", "rental_count"],
                    rows=[],
                    row_count=0,
                    warnings=[],
                )
            return SQLExecutionResult(
                sql=validated_sql,
                success=True,
                columns=["rental_month", "rental_count"],
                rows=[["2022-01-01", 120], ["2022-02-01", 182]],
                row_count=2,
                warnings=[],
            )

    generation_service = RelativeTimeGenerationService()
    pipeline_service = QueryPipelineService(
        retrieval_service=StableRetrievalService(),
        sql_generation_service=generation_service,
        sql_validation_service=ValidatingSQLValidationService(),
        sql_execution_service=NoRowsUntilRepairExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query(
        "What is the monthly trend of rentals this year?",
        sample_schema,
    )

    assert generation_service.repair_calls >= 1
    assert response.row_count == 2
    assert any("relative time period" in warning.lower() for warning in response.warnings)


class UsageRecordingSQLGenerationService(FakeSQLGenerationService):
    def generate_sql(self, *args, **kwargs) -> SQLGenerationResult:
        record_llm_usage("gpt-5.1", _openai_usage(input_tokens=700, output_tokens=160))
        return super().generate_sql(*args, **kwargs)

    def review_sql(self, *args, **kwargs) -> SQLSemanticReviewResult:
        record_llm_usage("gpt-5.1", _openai_usage(input_tokens=750, output_tokens=30))
        return super().review_sql(*args, **kwargs)


def _openai_usage(input_tokens: int, output_tokens: int):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


def test_query_pipeline_reports_llm_usage_for_the_request(sample_schema) -> None:
    pipeline_service = QueryPipelineService(
        retrieval_service=FakeRetrievalService(),
        sql_generation_service=UsageRecordingSQLGenerationService(),
        sql_validation_service=FakeSQLValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    response = pipeline_service.run_query("How much revenue by customer?", sample_schema)

    assert response.usage is not None
    assert response.usage.llm_calls == 2
    assert response.usage.input_tokens == 1_450
    assert response.usage.output_tokens == 190
    assert response.usage.cost_usd == round((1_450 * 1.25 + 190 * 10.00) / 1_000_000, 6)


def test_query_pipeline_attaches_usage_to_pipeline_errors(sample_schema) -> None:
    class HardFailValidationService:
        def validate_sql(self, sql: str) -> SQLValidationResult:
            return SQLValidationResult(
                original_sql=sql,
                is_valid=False,
                can_repair=False,
                classification="hard_safety_failure",
                errors=["Unsafe SQL operation detected: Drop"],
            )

    pipeline_service = QueryPipelineService(
        retrieval_service=FakeRetrievalService(),
        sql_generation_service=UsageRecordingSQLGenerationService(),
        sql_validation_service=HardFailValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )

    with pytest.raises(QueryPipelineError) as exc_info:
        pipeline_service.run_query("How much revenue by customer?", sample_schema)

    assert exc_info.value.usage is not None
    assert exc_info.value.usage.llm_calls >= 1


def _attempt_with_rows(rows: list[list]) -> dict:
    return {
        "pipeline_result": {
            "execution_result": SQLExecutionResult(
                sql="SELECT 1",
                success=True,
                columns=["month", "signups"],
                rows=rows,
                row_count=len(rows),
                warnings=[],
            )
        }
    }


def test_relative_time_retry_also_fires_on_a_zero_filled_result() -> None:
    pipeline_service = QueryPipelineService(sql_generation_service=FakeSQLGenerationService())
    zero_filled = [["2026-01-01", 0], ["2026-02-01", Decimal("0")], ["2026-03-01", None]]

    assert pipeline_service._should_retry_after_relative_time_no_rows(
        question="Show signups per month this year",
        attempt=_attempt_with_rows(zero_filled),
        recovery_actions=[],
    )


def test_relative_time_retry_does_not_fire_when_any_measure_has_a_value() -> None:
    pipeline_service = QueryPipelineService(sql_generation_service=FakeSQLGenerationService())

    assert not pipeline_service._should_retry_after_relative_time_no_rows(
        question="Show signups per month this year",
        attempt=_attempt_with_rows([["2026-01-01", 0], ["2026-02-01", 3]]),
        recovery_actions=[],
    )
    assert not pipeline_service._should_retry_after_relative_time_no_rows(
        question="Show signups per month",
        attempt=_attempt_with_rows([["2026-01-01", 0]]),
        recovery_actions=[],
    )


def test_query_pipeline_passes_final_sql_assumptions_and_empty_result_coverage(sample_schema) -> None:
    class AssumingGenerationService(FakeSQLGenerationService):
        def __init__(self) -> None:
            super().__init__()
            self.generated = [
                SQLGenerationResult(
                    sql="SELECT customer_id, amount FROM payment WHERE false",
                    used_tables=["public.payment"],
                    assumptions=["“paid” = total of all payments"],
                )
            ] * 2

    class EmptyThenCoverageExecutionService:
        def __init__(self) -> None:
            self.executed: list[str] = []

        def execute_sql(self, validated_sql: str, connection_settings=None) -> SQLExecutionResult:
            self.executed.append(validated_sql)
            if validated_sql.startswith("SELECT MIN("):
                return SQLExecutionResult(
                    sql=validated_sql,
                    success=True,
                    columns=["min", "max"],
                    rows=[["2022-01-23", "2022-07-27"]],
                    row_count=1,
                )
            return SQLExecutionResult(
                sql=validated_sql, success=True, columns=["customer_id", "amount"], rows=[], row_count=0
            )

    formatter = FakeResponseFormatterService()
    execution_service = EmptyThenCoverageExecutionService()
    pipeline_service = QueryPipelineService(
        retrieval_service=FakeRetrievalService(),
        sql_generation_service=AssumingGenerationService(),
        sql_validation_service=FakeSQLValidationService(),
        sql_execution_service=execution_service,
        response_formatter_service=formatter,
    )

    response = pipeline_service.run_query("How much did customers pay?", sample_schema)

    assert response.assumptions == ["“paid” = total of all payments"]
    assert formatter.last_data_coverage == ["payment payment date from 2022-01-23 to 2022-07-27"]
    assert any(
        sql == 'SELECT MIN("payment_date")::date::text AS earliest_0, '
        'MAX("payment_date")::date::text AS latest_0 FROM "public"."payment"'
        for sql in execution_service.executed
    )


class _ConstantThenTableGeneration(FakeSQLGenerationService):
    """Writes a constant-only "explanation" query until the schema search is broadened."""

    def __init__(self, constant_every_time: bool = False, constant_sql: str | None = None) -> None:
        super().__init__()
        self.constant_every_time = constant_every_time
        self.constant_sql = constant_sql or (
            "SELECT CAST('Customer spending cannot be ranked because the schema has no payment amounts.' AS TEXT) AS explanation"
        )

    def generate_sql(self, question, schema_context, conversation_context=None, plan=None, memory_context=None, dataset_hints=None):
        self.generate_calls += 1
        if self.constant_every_time or self.generate_calls == 1:
            return SQLGenerationResult(sql=self.constant_sql, used_tables=[])
        return SQLGenerationResult(sql="SELECT customer_id, amount FROM payment", used_tables=["public.payment"])


class _TableAwareValidation:
    def validate_sql(self, sql: str) -> SQLValidationResult:
        reads_table = " FROM " in sql.upper()
        return SQLValidationResult(
            original_sql=sql,
            validated_sql=sql,
            is_valid=True,
            can_repair=False,
            classification="valid",
            detected_tables=["payment"] if reads_table else [],
        )


class _EchoExecution:
    def execute_sql(self, validated_sql: str, connection_settings=None) -> SQLExecutionResult:
        if " FROM " not in validated_sql.upper():
            text = validated_sql.split("'")[1]
            return SQLExecutionResult(sql=validated_sql, success=True, columns=["explanation"], rows=[[text]], row_count=1)
        return SQLExecutionResult(sql=validated_sql, success=True, columns=["customer_id", "amount"], rows=[[1, 10.0]], row_count=1)


def _constant_pipeline(generation) -> tuple[QueryPipelineService, list[bool]]:
    broaden_calls: list[bool] = []

    class Retrieval(FakeRetrievalService):
        def retrieve_schema_context(self, question, schema, plan=None, memory_context=None, dataset_adapter=None,
                                    max_tables=5, max_columns_per_table=8, broaden=False):
            broaden_calls.append(broaden)
            return self.context

    service = QueryPipelineService(
        retrieval_service=Retrieval(),
        sql_generation_service=generation,
        sql_validation_service=_TableAwareValidation(),
        sql_execution_service=_EchoExecution(),
        response_formatter_service=FakeResponseFormatterService(),
    )
    return service, broaden_calls


def test_query_that_reads_no_table_is_retried_with_broader_retrieval(sample_schema) -> None:
    service, broaden_calls = _constant_pipeline(_ConstantThenTableGeneration())

    response = service.run_query("Who are our customers with the highest total spending?", sample_schema)

    assert broaden_calls == [False, True]
    assert response.response_type == "answer"
    assert response.rows == [[1, 10.0]]


def test_query_that_still_reads_no_table_becomes_cannot_answer(sample_schema) -> None:
    service, _ = _constant_pipeline(_ConstantThenTableGeneration(constant_every_time=True))

    response = service.run_query("Who are our customers with the highest total spending?", sample_schema)

    assert response.response_type == "cannot_answer"
    assert response.cannot_answer.reason.startswith("Customer spending cannot be ranked")
    assert response.rows == []
    assert response.generated_sql == ""


def test_constant_answer_that_names_tables_is_kept(sample_schema) -> None:
    generation = _ConstantThenTableGeneration(
        constant_every_time=True,
        constant_sql="SELECT CAST('public.payment' AS TEXT) AS table_name",
    )
    service, broaden_calls = _constant_pipeline(generation)

    response = service.run_query("Where are payments kept?", sample_schema)

    assert broaden_calls == [False]
    assert response.response_type == "answer"
    assert response.rows == [["public.payment"]]
