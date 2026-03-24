from pydantic import BaseModel, ConfigDict, Field


class SchemaColumnResponse(BaseModel):
    name: str
    data_type: str
    nullable: bool
    description: str | None = None


class SchemaForeignKeyResponse(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    references_schema: str
    references_table: str
    references_columns: list[str] = Field(default_factory=list)


class SchemaTableResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    schema_name: str = Field(alias="schema")
    description: str | None = None
    columns: list[SchemaColumnResponse] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[SchemaForeignKeyResponse] = Field(default_factory=list)


class SchemaOverviewResponse(BaseModel):
    tables: list[SchemaTableResponse] = Field(default_factory=list)
