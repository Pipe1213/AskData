from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from app.llm.response_models import (
    LLMGenerationConfig,
    LLMMessage,
    LLMStructuredResponse,
    LLMTextResponse,
)

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class LLMClientError(Exception):
    """Raised when the LLM provider request fails or returns unusable output."""


class BaseLLMClient(ABC):
    provider_name: str

    @abstractmethod
    def generate_text(
        self,
        messages: list[LLMMessage],
        config: LLMGenerationConfig | None = None,
    ) -> LLMTextResponse:
        raise NotImplementedError

    @abstractmethod
    def generate_structured(
        self,
        messages: list[LLMMessage],
        response_model: type[StructuredOutputT],
        config: LLMGenerationConfig | None = None,
    ) -> LLMStructuredResponse[StructuredOutputT]:
        raise NotImplementedError
