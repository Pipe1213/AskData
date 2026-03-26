from functools import lru_cache

from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    query_timeout_seconds: int = Field(default=10, alias="QUERY_TIMEOUT_SECONDS")
    max_result_rows: int = Field(default=200, alias="MAX_RESULT_ROWS")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="pagila", alias="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")

    cors_allowed_origins: list[str] = Field(
        default=["http://127.0.0.1:3000", "http://localhost:3000"],
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "ASKDATA_CORS_ALLOWED_ORIGINS"),
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
