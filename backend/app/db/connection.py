from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.schemas.data_source import PostgresConnectionSettings


def build_postgres_connection_kwargs(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
) -> dict[str, str | int]:
    if connection_settings is not None:
        return {
            "host": connection_settings.host,
            "port": connection_settings.port,
            "dbname": connection_settings.database,
            "user": connection_settings.user,
            "password": connection_settings.password,
            "sslmode": connection_settings.sslmode,
        }

    active_settings = settings or get_settings()
    return {
        "host": active_settings.postgres_host,
        "port": active_settings.postgres_port,
        "dbname": active_settings.postgres_db,
        "user": active_settings.postgres_user,
        "password": active_settings.postgres_password,
    }


@contextmanager
def get_db_connection(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
) -> Generator[psycopg.Connection[dict], None, None]:
    with psycopg.connect(
        **build_postgres_connection_kwargs(
            settings=settings,
            connection_settings=connection_settings,
        ),
        row_factory=dict_row,
    ) as connection:
        yield connection


def run_connection_smoke_check(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
) -> dict[str, int]:
    with get_db_connection(settings, connection_settings=connection_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Database smoke check returned no row.")

    return {"ok": int(row["ok"])}
