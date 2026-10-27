from app.llm.base import LLMClientError
from app.llm.prompt_builders import build_question_triage_messages
from app.schemas.query import (
    ConversationMessage,
    QuestionTriageResult,
)
from app.schemas.retrieval import RetrievedSchemaContext, RetrievedTable
from app.services.query_pipeline_service import QueryPipelineService
from test_query_pipeline_service import (
    FakeResponseFormatterService,
    FakeRetrievalService,
    FakeSQLExecutionService,
    FakeSQLGenerationService,
    FakeSQLValidationService,
)


class TriagingSQLGenerationService(FakeSQLGenerationService):
    def __init__(self, result: QuestionTriageResult | Exception) -> None:
        super().__init__()
        self.result = result
        self.triage_calls = 0
        self.triage_conversation_context = None
        # The fake generator's first SQL is invalid on purpose; start with the valid one.
        self.generated = [self.generated[1], self.generated[1]]

    def triage_question(self, question, schema_context, schema, conversation_context=None):
        self.triage_calls += 1
        self.triage_conversation_context = conversation_context
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _pipeline(generation_service: TriagingSQLGenerationService) -> QueryPipelineService:
    return QueryPipelineService(
        retrieval_service=FakeRetrievalService(),
        sql_generation_service=generation_service,
        sql_validation_service=FakeSQLValidationService(),
        sql_execution_service=FakeSQLExecutionService(),
        response_formatter_service=FakeResponseFormatterService(),
    )


def test_ambiguous_question_returns_clarification_without_running_sql(sample_schema) -> None:
    generation_service = TriagingSQLGenerationService(
        QuestionTriageResult(
            decision="ambiguous",
            reason="It is not clear which measure decides the ranking.",
            clarification_question="Which measure should decide the ranking?",
            options=["Which customers paid the most in total?", "Which customers made the most payments?"],
        )
    )

    response = _pipeline(generation_service).run_query("Rank the customers", sample_schema)

    assert response.response_type == "clarification"
    assert response.clarification is not None
    assert response.clarification.question == "Which measure should decide the ranking?"
    assert response.clarification.options == [
        "Which customers paid the most in total?",
        "Which customers made the most payments?",
    ]
    assert response.cannot_answer is None
    assert response.columns == [] and response.rows == [] and response.generated_sql == ""
    assert "(1) Which customers paid the most in total?" in response.answer_summary
    assert generation_service.generate_calls == 0
    assert response.usage is not None


def test_unanswerable_question_returns_cannot_answer_without_running_sql(sample_schema) -> None:
    generation_service = TriagingSQLGenerationService(
        QuestionTriageResult(
            decision="unanswerable",
            reason="The database records payments but not how customers rated anything.",
            alternatives=["Which customers paid the most in total?", "", "a", "b"],
        )
    )

    response = _pipeline(generation_service).run_query("How satisfied are customers?", sample_schema)

    assert response.response_type == "cannot_answer"
    assert response.cannot_answer is not None
    assert response.cannot_answer.reason.startswith("The database records payments")
    assert response.cannot_answer.alternatives == ["Which customers paid the most in total?", "a"]
    assert response.clarification is None
    assert response.rows == [] and response.generated_sql == ""
    assert generation_service.generate_calls == 0


def test_answerable_question_runs_the_sql_pipeline(sample_schema) -> None:
    generation_service = TriagingSQLGenerationService(QuestionTriageResult(decision="answerable"))

    response = _pipeline(generation_service).run_query("How much revenue by customer?", sample_schema)

    assert response.response_type == "answer"
    assert response.clarification is None and response.cannot_answer is None
    assert generation_service.triage_calls == 1
    assert generation_service.generate_calls == 1
    assert response.generated_sql
    assert any(step.stage == "triage" for step in response.trace.stages)


def test_follow_up_that_picks_an_option_reaches_triage_with_the_clarification_and_is_answered(
    sample_schema,
) -> None:
    generation_service = TriagingSQLGenerationService(QuestionTriageResult(decision="answerable"))
    conversation = [
        ConversationMessage(role="user", content="Rank the customers"),
        ConversationMessage(
            role="assistant",
            content="Which measure should decide the ranking? (1) Which customers paid the most in total? "
            "(2) Which customers made the most payments?",
        ),
    ]

    response = _pipeline(generation_service).run_query(
        "Which customers paid the most in total?",
        sample_schema,
        conversation_context=conversation,
    )

    assert response.response_type == "answer"
    assert generation_service.generate_calls == 1
    assert [message.role for message in generation_service.triage_conversation_context] == ["user", "assistant"]


def test_ambiguous_without_two_options_is_answered_instead(sample_schema) -> None:
    generation_service = TriagingSQLGenerationService(
        QuestionTriageResult(
            decision="ambiguous",
            reason="Unclear.",
            clarification_question="Which one?",
            options=["Which customers paid the most in total?"],
        )
    )

    response = _pipeline(generation_service).run_query("Rank the customers", sample_schema)

    assert response.response_type == "answer"
    assert generation_service.generate_calls == 1


def test_triage_failure_falls_back_to_answering(sample_schema) -> None:
    generation_service = TriagingSQLGenerationService(LLMClientError("timeout"))

    response = _pipeline(generation_service).run_query("How much revenue by customer?", sample_schema)

    assert response.response_type == "answer"
    assert generation_service.generate_calls == 1


def test_triage_prompt_lists_all_columns_of_relevant_tables_and_names_the_others(sample_schema) -> None:
    schema_context = RetrievedSchemaContext(
        question="How much did customers pay?",
        tables=[
            RetrievedTable(schema_name="public", table_name="payment", full_name="public.payment", score=5.0),
        ],
    )

    messages = build_question_triage_messages(
        question="How much did customers pay?",
        schema_context=schema_context,
        schema=sample_schema,
        conversation_context=[ConversationMessage(role="user", content="Earlier question")],
    )
    user_prompt = messages[1]["content"]

    # Full column list even though retrieval selected no columns.
    assert "payment_date (timestamp)" in user_prompt
    assert "amount (numeric)" in user_prompt
    assert "Other tables in the database (columns not shown): public.customer" in user_prompt
    assert "- user: Earlier question" in user_prompt
