from typing import Literal

from pydantic import BaseModel, Field


ValidationClassification = Literal["valid", "repairable_failure", "hard_safety_failure"]


class SQLValidationResult(BaseModel):
    original_sql: str
    validated_sql: str | None = None
    is_valid: bool
    can_repair: bool
    classification: ValidationClassification
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    detected_tables: list[str] = Field(default_factory=list)
