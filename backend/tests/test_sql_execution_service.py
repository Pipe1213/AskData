from contextlib import contextmanager

from app.core.config import Settings
from app.services import sql_execution_service as execution_module
from app.services.sql_execution_service import SQLExecutionService


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.description = [
            type("Description", (), {"name": "customer_id"})(),
            type("Description", (), {"name": "amount"})(),
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executed.append((sql, params))

    def fetchmany(self, size: int):
        return [
            {"customer_id": 1, "amount": 10.0},
            {"customer_id": 2, "amount": 12.5},
        ]


class FakeConnection:
    def __init__(self) -> None:
        self.read_only = False
        self.cursor_instance = FakeCursor()

    @contextmanager
    def transaction(self):
        yield self

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_execute_sql_sets_local_timeout_via_set_config(monkeypatch) -> None:
    fake_connection = FakeConnection()

    @contextmanager
    def fake_get_db_connection(_settings):
        yield fake_connection

    monkeypatch.setattr(execution_module, "get_db_connection", fake_get_db_connection)

    service = SQLExecutionService(
        Settings(
            QUERY_TIMEOUT_SECONDS=10,
            MAX_RESULT_ROWS=200,
        )
    )

    result = service.execute_sql("SELECT customer_id, amount FROM payment")

    assert result.success is True
    assert fake_connection.read_only is True
    assert fake_connection.cursor_instance.executed[0] == (
        "SELECT set_config('statement_timeout', %s, true)",
        ("10000ms",),
    )
    assert fake_connection.cursor_instance.executed[1] == (
        "SELECT customer_id, amount FROM payment",
        None,
    )
