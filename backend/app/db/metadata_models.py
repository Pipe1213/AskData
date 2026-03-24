from pydantic import BaseModel, Field


class ColumnMetadata(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    has_default: bool
    ordinal_position: int
    description: str | None = None


class ForeignKeyMetadata(BaseModel):
    name: str
    source_schema: str
    source_table: str
    source_columns: list[str] = Field(default_factory=list)
    target_schema: str
    target_table: str
    target_columns: list[str] = Field(default_factory=list)


class TableMetadata(BaseModel):
    schema_name: str
    table_name: str
    full_name: str
    description: str | None = None
    columns: list[ColumnMetadata] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyMetadata] = Field(default_factory=list)
    related_tables: list[str] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    tables: list[TableMetadata] = Field(default_factory=list)
