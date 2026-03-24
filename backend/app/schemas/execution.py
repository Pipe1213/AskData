from typing import Any

from pydantic import BaseModel, Field


class SQLExecutionError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SQLExecutionResult(BaseModel):
    sql: str
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: SQLExecutionError | None = None
