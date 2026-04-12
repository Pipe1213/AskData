import pytest
from pydantic import ValidationError

from app.schemas.data_source import RuntimePostgresConnectionInput


def test_runtime_connection_input_defaults_schema_allowlist_to_public() -> None:
    payload = RuntimePostgresConnectionInput(
        host="localhost",
        port=5432,
        database="analytics",
        user="postgres",
        password="postgres",
        sslmode="prefer",
        schema_allowlist=[],
    )

    assert payload.schema_allowlist == ["public"]


def test_runtime_connection_input_rejects_invalid_port() -> None:
    with pytest.raises(ValidationError):
        RuntimePostgresConnectionInput(
            host="localhost",
            port=70000,
            database="analytics",
            user="postgres",
            password="postgres",
            sslmode="prefer",
        )
