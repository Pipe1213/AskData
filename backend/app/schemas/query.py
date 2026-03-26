from typing import Any, Literal

from pydantic import BaseModel, Field


class SQLGenerationResult(BaseModel):
    sql: str
    used_tables: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str
    conversation_context: list["ConversationMessage"] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChartRecommendation(BaseModel):
    type: Literal["bar", "line", "table_only"]
    x: str | None = None
    y: str | None = None


class QueryResponse(BaseModel):
    question: str
    answer_summary: str
    generated_sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    chart_recommendation: ChartRecommendation
    warnings: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class QueryErrorResponse(BaseModel):
    error: ErrorPayload
    warnings: list[str] = Field(default_factory=list)
