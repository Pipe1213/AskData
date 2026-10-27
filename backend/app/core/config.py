from functools import lru_cache

from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# USD per 1M tokens: (input, cached input, output), Standard tier, inputs up to 272K tokens.
# Source: https://developers.openai.com/api/docs/pricing, checked 2026-10-25.
# Models missing here are still counted in usage, with cost_usd reported as null.
OPENAI_PRICES_PER_MILLION_TOKENS: dict[str, tuple[float, float, float]] = {
    "gpt-5.1": (1.25, 0.125, 10.00),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = Field(default="AskData Backend", alias="ASKDATA_APP_NAME")
    app_env: str = Field(default="development", alias="ASKDATA_ENV")
    app_version: str = Field(default="0.1.0", alias="ASKDATA_APP_VERSION")
    log_level: str = Field(default="INFO", alias="ASKDATA_LOG_LEVEL")
    debug_mode: bool = Field(default=False, alias="ASKDATA_DEBUG_MODE")

    query_timeout_seconds: int = Field(default=10, alias="QUERY_TIMEOUT_SECONDS")
    max_result_rows: int = Field(default=200, alias="MAX_RESULT_ROWS")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="pagila", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD", repr=False)
    # Alternative to the POSTGRES_* fields: postgresql://user:password@host:port/database
    database_url: str | None = Field(default=None, alias="DATABASE_URL", repr=False)
    postgres_connect_timeout_seconds: int = Field(default=10, alias="POSTGRES_CONNECT_TIMEOUT_SECONDS")
    # False for hosted demos: the API refuses runtime connections and the UI hides "Connect".
    allow_custom_db: bool = Field(default=True, alias="ASKDATA_ALLOW_CUSTOM_DB")

    cors_allowed_origins: list[str] = Field(
        default=["http://127.0.0.1:3000", "http://localhost:3000"],
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "ASKDATA_CORS_ALLOWED_ORIGINS"),
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY", repr=False)
    openai_model: str | None = Field(default=None, alias="OPENAI_MODEL")
    openai_sql_model: str | None = Field(default=None, alias="OPENAI_SQL_MODEL")
    openai_summary_model: str | None = Field(default=None, alias="OPENAI_SUMMARY_MODEL")
    # Sent as `reasoning.effort` (none, low, medium, ...); an empty value uses the model's default.
    # gpt-6.1-sol supports low and up; gpt-6-luna also supports none.
    openai_sql_reasoning_effort: str | None = Field(default="low", alias="OPENAI_SQL_REASONING_EFFORT")
    openai_summary_reasoning_effort: str | None = Field(
        default="none",
        alias="OPENAI_SUMMARY_REASONING_EFFORT",
    )

    @property
    def resolved_sql_model(self) -> str:
        return self.openai_sql_model or self.openai_model or "gpt-6.1-sol"

    @property
    def resolved_summary_model(self) -> str:
        return self.openai_summary_model or self.openai_model or "gpt-6-luna"


@lru_cache
def get_settings() -> Settings:
    return Settings()
