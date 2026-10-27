from typing import Any, Literal

from psycopg.conninfo import conninfo_to_dict
from pydantic import BaseModel, Field, field_validator, model_validator


SslMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
TargetType = Literal["demo_pagila", "demo_retail_ops", "runtime_postgres"]


class PostgresConnectionSettings(BaseModel):
    host: str
    port: int
    database: str
    user: str
    password: str = Field(repr=False)
    sslmode: SslMode = "prefer"


class RuntimePostgresConnectionInput(BaseModel):
    """A database to connect: separate fields, or `connection_url` (fields given explicitly win)."""

    connection_url: str | None = Field(default=None, repr=False, exclude=True)
    host: str
    port: int = 5432
    database: str
    user: str
    password: str = Field(repr=False)
    sslmode: SslMode = "prefer"
    schema_allowlist: list[str] = Field(default_factory=lambda: ["public"])

    @model_validator(mode="before")
    @classmethod
    def fill_from_connection_url(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not data.get("connection_url"):
            return data

        url = str(data["connection_url"]).strip()
        if not url.startswith(("postgresql://", "postgres://")):
            raise ValueError("Connection URL must start with postgresql://")
        try:
            parsed = conninfo_to_dict(url)
        except Exception:
            # The parser's message can quote parts of the URL, including the password.
            raise ValueError("Connection URL could not be read.") from None

        from_url = {
            "host": parsed.get("host"),
            "port": parsed.get("port"),
            "database": parsed.get("dbname"),
            "user": parsed.get("user"),
            "password": parsed.get("password"),
            "sslmode": parsed.get("sslmode"),
        }
        merged = dict(data)
        for key, value in from_url.items():
            if value not in (None, "") and merged.get(key) in (None, ""):
                merged[key] = value
        return merged

    @field_validator("host", "database", "user", "password")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty.")
        return normalized

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("Port must be between 1 and 65535.")
        return value

    @field_validator("schema_allowlist")
    @classmethod
    def validate_schema_allowlist(cls, value: list[str]) -> list[str]:
        normalized = [schema.strip() for schema in value if schema.strip()]
        if not normalized:
            return ["public"]
        unique = list(dict.fromkeys(normalized))
        return unique

    def to_connection_settings(self) -> PostgresConnectionSettings:
        return PostgresConnectionSettings(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode,
        )


class DataSourceSummary(BaseModel):
    target_id: str
    target_type: TargetType
    display_name: str
    persistence_allowed: bool
    is_active: bool = False
    database_name: str | None = None
    host: str | None = None
    schema_allowlist: list[str] = Field(default_factory=list)


class DataSourcesResponse(BaseModel):
    custom_db_allowed: bool = True
    active_target: DataSourceSummary
    demo_targets: list[DataSourceSummary] = Field(default_factory=list)
    runtime_target: DataSourceSummary | None = None


class DemoTargetActivateRequest(BaseModel):
    target_id: Literal["demo_pagila", "demo_retail_ops"]


class RuntimeConnectionTestResponse(BaseModel):
    ok: bool = True
    database_version: str
    visible_schemas: list[str] = Field(default_factory=list)
    table_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class RuntimeTargetActivationResponse(BaseModel):
    active_target: DataSourceSummary
    database_version: str
    visible_schemas: list[str] = Field(default_factory=list)
    table_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class DataSourceActivationResponse(BaseModel):
    active_target: DataSourceSummary
    table_count: int = 0
