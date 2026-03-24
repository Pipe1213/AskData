from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import ChartRecommendation, QueryResponse, SQLGenerationResult
from app.schemas.retrieval import RetrievedSchemaContext, RetrievedTable
from app.schemas.validation import SQLValidationResult
from app.services.query_pipeline_service import QueryPipelineService


class FakeRetrievalService:
    def __init__(self) -> None:
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

    def retrieve_schema_context(self, question: str, schema: DatabaseSchema) -> RetrievedSchemaContext:
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

    def generate_sql(self, question: str, schema_context: RetrievedSchemaContext) -> SQLGenerationResult:
        self.generate_calls += 1
        return self.generated[0]

    def repair_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        previous_sql: str,
        failure_message: str,
    ) -> SQLGenerationResult:
        self.repair_calls += 1
        return self.generated[1]


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
    def execute_sql(self, validated_sql: str) -> SQLExecutionResult:
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
    ) -> QueryResponse:
        return QueryResponse(
            question=question,
            answer_summary="One repaired result row was returned.",
            generated_sql=generated_sql,
            columns=execution_result.columns,
            rows=execution_result.rows,
            chart_recommendation=ChartRecommendation(type="table_only"),
            warnings=warnings or [],
            used_tables=used_tables,
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
    assert generation_service.repair_calls == 1
    assert "repaired once after a validation failure" in " ".join(response.warnings).lower()
    assert response.generated_sql.endswith("LIMIT 200")


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
        def generate_sql(self, question: str, schema_context: RetrievedSchemaContext) -> SQLGenerationResult:
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
