from typing import Any, Literal

from pydantic import BaseModel, Field


class SQLGenerationResult(BaseModel):
    sql: str
    used_tables: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None
    conversation_context: list["ConversationMessage"] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChartRecommendation(BaseModel):
    type: Literal["bar", "line", "table_only"]
    x: str | None = None
    y: str | None = None


class DebugPayload(BaseModel):
    stage: str | None = None
    retrieval_tables: list[str] = Field(default_factory=list)
    validation_classification: str | None = None
    detected_tables: list[str] = Field(default_factory=list)
    repair_attempted: bool = False


class QueryResponse(BaseModel):
    question: str
    answer_summary: str
    generated_sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    chart_recommendation: ChartRecommendation
    warnings: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)
    session_id: str | None = None
    turn_id: str | None = None
    persisted: bool = False
    created_at: str | None = None
    repaired: bool = False
    debug: DebugPayload | None = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class QueryErrorResponse(BaseModel):
    error: ErrorPayload
    warnings: list[str] = Field(default_factory=list)
    session_id: str | None = None
    turn_id: str | None = None
    persisted: bool = False
    created_at: str | None = None
    debug: DebugPayload | None = None
