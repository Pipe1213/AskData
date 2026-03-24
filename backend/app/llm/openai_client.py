from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.llm.base import BaseLLMClient, LLMClientError
from app.llm.response_models import (
    LLMGenerationConfig,
    LLMMessage,
    LLMStructuredResponse,
    LLMTextResponse,
)

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class OpenAILLMClient(BaseLLMClient):
    provider_name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        if not self.settings.openai_api_key:
            raise LLMClientError("OPENAI_API_KEY is required to initialize the OpenAI client.")

        self.client = OpenAI(api_key=self.settings.openai_api_key)
        self.model = self.settings.openai_model

    def generate_text(
        self,
        messages: list[LLMMessage],
        config: LLMGenerationConfig | None = None,
    ) -> LLMTextResponse:
        generation_config = config or LLMGenerationConfig()

        try:
            response = self.client.responses.create(
                model=self.model,
                input=self._build_openai_input(messages),
                **self._build_generation_kwargs(generation_config),
            )
        except Exception as exc:
            raise LLMClientError(f"OpenAI text generation failed: {exc}") from exc

        text = self._extract_text(response)
        return LLMTextResponse(
            provider=self.provider_name,
            model=self.model,
            text=text,
        )

    def generate_structured(
        self,
        messages: list[LLMMessage],
        response_model: type[StructuredOutputT],
        config: LLMGenerationConfig | None = None,
    ) -> LLMStructuredResponse[StructuredOutputT]:
        generation_config = config or LLMGenerationConfig()

        try:
            response = self.client.responses.create(
                model=self.model,
                input=self._build_openai_input(messages),
                **self._build_generation_kwargs(generation_config),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": response_model.__name__,
                        "strict": True,
                        "schema": self._build_openai_json_schema(response_model),
                    }
                },
            )
        except Exception as exc:
            raise LLMClientError(f"OpenAI structured generation failed: {exc}") from exc

        text = self._extract_text(response)

        try:
            parsed_output = response_model.model_validate_json(text)
        except ValidationError as exc:
            raise LLMClientError(
                f"OpenAI structured output did not match {response_model.__name__}: {exc}"
            ) from exc

        return LLMStructuredResponse[StructuredOutputT](
            provider=self.provider_name,
            model=self.model,
            output=parsed_output,
        )

    def _build_openai_input(self, messages: list[LLMMessage]) -> list[dict]:
        return [
            {
                "role": message.role,
                "content": [{"type": "input_text", "text": message.content}],
            }
            for message in messages
        ]

    def _extract_text(self, response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output_items = getattr(response, "output", None)
        if isinstance(output_items, list):
            content_parts: list[str] = []
            for item in output_items:
                if getattr(item, "type", None) != "message":
                    continue

                for content_item in getattr(item, "content", []) or []:
                    if getattr(content_item, "type", None) != "output_text":
                        continue

                    text = getattr(content_item, "text", None)
                    if isinstance(text, str) and text.strip():
                        content_parts.append(text)

            if content_parts:
                return "".join(content_parts)

        if getattr(response, "status", None) == "incomplete":
            incomplete_details = getattr(response, "incomplete_details", None)
            reason = getattr(incomplete_details, "reason", "unknown")
            raise LLMClientError(f"OpenAI response was incomplete: {reason}.")

        raise LLMClientError("OpenAI response did not contain usable text output.")

    def _build_generation_kwargs(self, config: LLMGenerationConfig) -> dict:
        generation_kwargs: dict = {}

        if config.max_output_tokens is not None:
            generation_kwargs["max_output_tokens"] = config.max_output_tokens

        if config.temperature is not None:
            generation_kwargs["temperature"] = config.temperature

        return generation_kwargs

    def _build_openai_json_schema(
        self,
        response_model: type[StructuredOutputT],
    ) -> dict:
        return self._normalize_schema_for_openai(response_model.model_json_schema())

    def _normalize_schema_for_openai(self, schema: dict) -> dict:
        normalized_schema: dict = {}

        for key, value in schema.items():
            if isinstance(value, dict):
                normalized_schema[key] = self._normalize_schema_for_openai(value)
            elif isinstance(value, list):
                normalized_schema[key] = [
                    self._normalize_schema_for_openai(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                normalized_schema[key] = value

        if normalized_schema.get("type") == "object":
            normalized_schema.setdefault("additionalProperties", False)
            properties = normalized_schema.get("properties")
            if isinstance(properties, dict):
                normalized_schema["required"] = list(properties.keys())

        return normalized_schema
