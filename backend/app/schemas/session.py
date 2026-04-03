from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.query import QueryErrorResponse, QueryResponse


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    turn_count: int = 0
    last_question: str | None = None
    last_status: Literal["success", "error"] | None = None


class SessionTurn(BaseModel):
    id: str
    question: str
    status: Literal["success", "error"]
    created_at: str
    response: QueryResponse | None = None
    error: QueryErrorResponse | None = None


class SessionDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    turns: list[SessionTurn] = Field(default_factory=list)


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    session: SessionDetail


class SessionRenameRequest(BaseModel):
    title: str

