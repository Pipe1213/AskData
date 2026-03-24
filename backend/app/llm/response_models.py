from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMTextResponse(BaseModel):
    provider: str
    model: str
    text: str


class LLMStructuredResponse(BaseModel, Generic[StructuredOutputT]):
    provider: str
    model: str
    output: StructuredOutputT


class LLMGenerationConfig(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None


class StructuredOutputSchema(BaseModel):
    name: str
    description: str | None = None
    json_schema: dict = Field(default_factory=dict, alias="schema")
