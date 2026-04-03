from app.core.config import Settings, get_settings
from app.llm.base import BaseLLMClient
from app.llm.openai_client import OpenAILLMClient
from app.llm.prompt_builders import (
    build_sql_generation_messages,
    build_sql_repair_messages,
    build_sql_semantic_review_messages,
)
from app.llm.response_models import LLMGenerationConfig, LLMMessage
from app.schemas.query import (
    ConversationMessage,
    SQLGenerationResult,
    SQLSemanticReviewResult,
)
from app.schemas.retrieval import RetrievedSchemaContext


class SQLGenerationService:
    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    def generate_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        conversation_context: list[ConversationMessage] | None = None,
    ) -> SQLGenerationResult:
        messages = build_sql_generation_messages(
            question=question,
            schema_context=schema_context,
            max_result_rows=self.settings.max_result_rows,
            conversation_context=conversation_context,
        )
        return self._run_structured_generation(messages)

    def repair_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        previous_sql: str,
        failure_message: str,
        conversation_context: list[ConversationMessage] | None = None,
    ) -> SQLGenerationResult:
        messages = build_sql_repair_messages(
            question=question,
            schema_context=schema_context,
            previous_sql=previous_sql,
            failure_message=failure_message,
            max_result_rows=self.settings.max_result_rows,
            conversation_context=conversation_context,
        )
        return self._run_structured_generation(messages)

    def review_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        generated_sql: str,
        conversation_context: list[ConversationMessage] | None = None,
    ) -> SQLSemanticReviewResult:
        messages = build_sql_semantic_review_messages(
            question=question,
            schema_context=schema_context,
            generated_sql=generated_sql,
            conversation_context=conversation_context,
        )
        llm_messages = [LLMMessage.model_validate(message) for message in messages]

        llm_client = self._get_llm_client()
        response = llm_client.generate_structured(
            messages=llm_messages,
            response_model=SQLSemanticReviewResult,
            config=LLMGenerationConfig(
                max_output_tokens=500,
            ),
        )
        return response.output

    def _run_structured_generation(
        self,
        messages: list[dict[str, str]],
    ) -> SQLGenerationResult:
        llm_messages = [LLMMessage.model_validate(message) for message in messages]

        llm_client = self._get_llm_client()
        response = llm_client.generate_structured(
            messages=llm_messages,
            response_model=SQLGenerationResult,
            config=LLMGenerationConfig(
                max_output_tokens=2500,
            ),
        )
        return response.output

    def _get_llm_client(self) -> BaseLLMClient:
        if self.llm_client is not None:
            return self.llm_client

        self.llm_client = OpenAILLMClient(
            self.settings,
            model=self.settings.resolved_sql_model,
        )
        return self.llm_client
