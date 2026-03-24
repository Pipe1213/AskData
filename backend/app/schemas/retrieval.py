from pydantic import BaseModel, Field


class RetrievedColumn(BaseModel):
    name: str
    data_type: str
    score: float


class RetrievedTable(BaseModel):
    schema_name: str
    table_name: str
    full_name: str
    score: float
    selected_columns: list[RetrievedColumn] = Field(default_factory=list)
    related_tables: list[str] = Field(default_factory=list)


class RetrievedRelationship(BaseModel):
    source_table: str
    source_columns: list[str] = Field(default_factory=list)
    target_table: str
    target_columns: list[str] = Field(default_factory=list)


class RetrievedSchemaContext(BaseModel):
    question: str
    tables: list[RetrievedTable] = Field(default_factory=list)
    relationships: list[RetrievedRelationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
