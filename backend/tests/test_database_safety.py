import logging
from collections.abc import Iterator
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import QueryPipelineError
from app.core.masking import MaskSecretsFilter, mask_secrets
from app.db.connection import build_postgres_connection_kwargs
from app.schemas.data_source import PostgresConnectionSettings, RuntimePostgresConnectionInput
from app.services.database_target_service import DatabaseTargetService

TEST_SCHEMA = "askdata_test_roles"
TEST_PASSWORD = "role-test-pw-4821"
TEST_ROLES = ("askdata_test_ro", "askdata_test_writer", "askdata_test_creator", "askdata_test_files")


# --- masking -------------------------------------------------------------------------------


def test_mask_secrets_hides_passwords_in_urls_pairs_json_and_known_values() -> None:
    assert mask_secrets("postgresql://ro:S3cret!@db:5432/shop") == "postgresql://ro:***@db:5432/shop"
    assert mask_secrets("host=db password=hunter22 user=ro") == "host=db password=*** user=ro"
    assert mask_secrets('{"password": "hunter22"}') == '{"password": "***"}'
    assert mask_secrets("value hunter22 leaked", ["hunter22"]) == "value *** leaked"
    # Messages that only mention passwords stay readable.
    assert mask_secrets('password authentication failed for user "ro"') == (
        'password authentication failed for user "ro"'
    )


def test_log_filter_masks_message_arguments() -> None:
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, "connecting to %s", ("postgresql://u:pw99@h/d",), None)

    MaskSecretsFilter().filter(record)

    assert record.getMessage() == "connecting to postgresql://u:***@h/d"


def test_pipeline_error_payload_masks_details() -> None:
    error = QueryPipelineError(
        code="connection_test_failed",
        message="failed for postgresql://u:pw99@h/d",
        stage="target",
        retryable=False,
        details={"error": "dsn password=pw99", "nested": ["postgresql://u:pw99@h/d"]},
    )

    payload = error.to_error_payload()

    assert "pw99" not in str(payload)


# --- connection input ----------------------------------------------------------------------


def test_connection_url_fills_fields_and_explicit_fields_win() -> None:
    parsed = RuntimePostgresConnectionInput.model_validate(
        {
            "connection_url": "postgresql://ro:p%40ss-word@db.example.com:6543/shop?sslmode=require",
            "schema_allowlist": ["sales"],
            "port": 7000,
        }
    )

    assert (parsed.host, parsed.port, parsed.database, parsed.user) == ("db.example.com", 7000, "shop", "ro")
    assert parsed.password == "p@ss-word"
    assert parsed.sslmode == "require"
    assert parsed.schema_allowlist == ["sales"]
    assert "p@ss-word" not in repr(parsed)
    assert "connection_url" not in parsed.model_dump()


def test_connection_url_must_be_postgres() -> None:
    with pytest.raises(ValueError, match="postgresql://"):
        RuntimePostgresConnectionInput.model_validate({"connection_url": "mysql://ro:pw@db/shop"})


def test_validation_errors_do_not_echo_the_submitted_password(client: TestClient) -> None:
    response = client.post(
        "/data-sources/runtime/test",
        headers={"X-AskData-Client-Token": "token"},
        json={"connection_url": "postgresql://ro:Very-Secret-77@db.example.com/"},
    )

    assert response.status_code == 422
    assert "Very-Secret-77" not in response.text


def test_database_url_is_used_for_the_default_connection() -> None:
    settings = SimpleNamespace(database_url="postgresql://ro:pw@db.example.com:6543/shop", postgres_connect_timeout_seconds=5)

    kwargs = build_postgres_connection_kwargs(settings)

    assert kwargs["host"] == "db.example.com"
    assert kwargs["port"] == "6543"
    assert kwargs["dbname"] == "shop"
    assert kwargs["connect_timeout"] == 5


# --- ASKDATA_ALLOW_CUSTOM_DB ---------------------------------------------------------------


def _runtime_input(user: str = "ro", password: str = "pw") -> RuntimePostgresConnectionInput:
    return RuntimePostgresConnectionInput(host="localhost", port=55432, database="pagila", user=user, password=password)


def test_flag_off_refuses_runtime_connections_and_reports_it() -> None:
    settings = Settings(ASKDATA_ALLOW_CUSTOM_DB=False)
    service = DatabaseTargetService(settings=settings)

    with pytest.raises(QueryPipelineError) as exc_info:
        service.test_runtime_postgres_connection("token", _runtime_input())
    assert exc_info.value.code == "custom_db_disabled"

    with pytest.raises(QueryPipelineError):
        service.activate_runtime_postgres_target("token", _runtime_input())


def test_flag_off_route_returns_403_and_data_sources_says_so(client: TestClient) -> None:
    client.app.state.database_target_service = DatabaseTargetService(settings=Settings(ASKDATA_ALLOW_CUSTOM_DB=False))

    response = client.post(
        "/data-sources/runtime/test",
        headers={"X-AskData-Client-Token": "token"},
        json={"host": "localhost", "database": "pagila", "user": "ro", "password": "pw"},
    )
    sources = client.get("/data-sources")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "custom_db_disabled"
    assert sources.json()["custom_db_allowed"] is False


# --- role check against the real database --------------------------------------------------


@pytest.fixture
def test_roles(admin_connection_settings: PostgresConnectionSettings) -> Iterator[PostgresConnectionSettings]:
    """Throwaway schema and roles: read-only, can insert, can create, can read server files."""
    statements = [
        f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE",
        *[f"DROP ROLE IF EXISTS {role}" for role in TEST_ROLES],
        f"CREATE SCHEMA {TEST_SCHEMA}",
        f"CREATE TABLE {TEST_SCHEMA}.orders (order_id integer PRIMARY KEY)",
        *[f"CREATE ROLE {role} LOGIN PASSWORD '{TEST_PASSWORD}'" for role in TEST_ROLES],
        *[f"GRANT USAGE ON SCHEMA {TEST_SCHEMA} TO {role}" for role in TEST_ROLES],
        *[f"GRANT SELECT ON {TEST_SCHEMA}.orders TO {role}" for role in TEST_ROLES],
        f"GRANT INSERT ON {TEST_SCHEMA}.orders TO askdata_test_writer",
        f"GRANT CREATE ON SCHEMA {TEST_SCHEMA} TO askdata_test_creator",
        "GRANT pg_read_server_files TO askdata_test_files",
    ]
    cleanup = [f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE", *[f"DROP ROLE IF EXISTS {role}" for role in TEST_ROLES]]
    connection = psycopg.connect(
        **build_postgres_connection_kwargs(connection_settings=admin_connection_settings),
        autocommit=True,
    )
    with connection:
        for statement in statements:
            connection.execute(statement)
        try:
            yield admin_connection_settings
        finally:
            for statement in cleanup:
                connection.execute(statement)


def _check(admin: PostgresConnectionSettings, user: str, password: str):
    service = DatabaseTargetService(settings=Settings(ASKDATA_ALLOW_CUSTOM_DB=True))
    payload = RuntimePostgresConnectionInput(
        host=admin.host,
        port=admin.port,
        database=admin.database,
        user=user,
        password=password,
        sslmode=admin.sslmode,
        schema_allowlist=[TEST_SCHEMA],
    )
    return service.test_runtime_postgres_connection("token", payload)


def test_read_only_user_is_accepted(test_roles) -> None:
    result = _check(test_roles, "askdata_test_ro", TEST_PASSWORD)

    assert result.ok is True
    assert result.visible_schemas == [TEST_SCHEMA]


@pytest.mark.parametrize(
    ("user", "expected_problem"),
    [
        ("askdata_test_writer", "can change data in 1 table(s), e.g. askdata_test_roles.orders (INSERT)"),
        ("askdata_test_creator", "can create objects in schema askdata_test_roles"),
        ("askdata_test_files", "is a member of pg_read_server_files"),
    ],
)
def test_users_that_can_write_or_read_server_files_are_refused(test_roles, user: str, expected_problem: str) -> None:
    with pytest.raises(QueryPipelineError) as exc_info:
        _check(test_roles, user, TEST_PASSWORD)

    assert exc_info.value.code == "unsafe_database_role"
    assert any(expected_problem in problem for problem in exc_info.value.details["problems"])
    assert TEST_PASSWORD not in str(exc_info.value.to_error_payload())


def test_superuser_is_refused(test_roles) -> None:
    with pytest.raises(QueryPipelineError) as exc_info:
        _check(test_roles, test_roles.user, test_roles.password)

    assert exc_info.value.code == "unsafe_database_role"
    assert "is a superuser" in exc_info.value.details["problems"]
