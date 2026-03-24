from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings


def build_postgres_dsn(settings: Settings) -> str:
    return (
        f"host={settings.postgres_host} "
        f"port={settings.postgres_port} "
        f"dbname={settings.postgres_db} "
        f"user={settings.postgres_user} "
        f"password={settings.postgres_password}"
    )


@contextmanager
def get_db_connection(
    settings: Settings | None = None,
) -> Generator[psycopg.Connection[dict], None, None]:
    active_settings = settings or get_settings()

    with psycopg.connect(
        conninfo=build_postgres_dsn(active_settings),
        row_factory=dict_row,
    ) as connection:
        yield connection


def run_connection_smoke_check(settings: Settings | None = None) -> dict[str, int]:
    with get_db_connection(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Database smoke check returned no row.")

    return {"ok": int(row["ok"])}
