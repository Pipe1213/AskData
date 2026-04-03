from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import (
    ChartRecommendation,
    ConversationMessage,
    QueryResponse,
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

    def retrieve_schema_context(self, question: str, schema: DatabaseSchema) -> RetrievedSchemaContext:
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
        repaired: bool = False,
    ) -> QueryResponse:
        return QueryResponse(
            question=question,
            answer_summary="One repaired result row was returned.",
            generated_sql=generated_sql,
            columns=execution_result.columns,
            rows=execution_result.rows,
            row_count=execution_result.row_count,
            chart_recommendation=ChartRecommendation(type="table_only"),
            warnings=warnings or [],
            used_tables=used_tables,
            repaired=repaired,
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
