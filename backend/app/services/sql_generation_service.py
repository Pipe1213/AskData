from app.core.config import Settings, get_settings
from app.llm.base import BaseLLMClient
from app.llm.openai_client import OpenAILLMClient
from app.llm.prompt_builders import build_sql_generation_messages, build_sql_repair_messages
from app.llm.response_models import LLMGenerationConfig, LLMMessage
from app.schemas.query import SQLGenerationResult
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
    ) -> SQLGenerationResult:
        messages = build_sql_generation_messages(
            question=question,
            schema_context=schema_context,
            max_result_rows=self.settings.max_result_rows,
        )
        return self._run_structured_generation(messages)

    def repair_sql(
        self,
        question: str,
        schema_context: RetrievedSchemaContext,
        previous_sql: str,
        failure_message: str,
    ) -> SQLGenerationResult:
        messages = build_sql_repair_messages(
            question=question,
            schema_context=schema_context,
            previous_sql=previous_sql,
            failure_message=failure_message,
            max_result_rows=self.settings.max_result_rows,
        )
        return self._run_structured_generation(messages)

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

        self.llm_client = OpenAILLMClient(self.settings)
        return self.llm_client
