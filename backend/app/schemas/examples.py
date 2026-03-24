from pydantic import BaseModel, Field


class ExamplesResponse(BaseModel):
    examples: list[str] = Field(default_factory=list)
