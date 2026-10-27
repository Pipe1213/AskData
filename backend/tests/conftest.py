import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from fastapi.testclient import TestClient

from app.db.metadata_models import (
    ColumnMetadata,
    DatabaseSchema,
    ForeignKeyMetadata,
    TableMetadata,
)
from app.db.connection import build_postgres_connection_kwargs
from app.main import create_app
from app.schemas.data_source import PostgresConnectionSettings


@pytest.fixture
def sample_schema() -> DatabaseSchema:
    customer_table = TableMetadata(
        schema_name="public",
        table_name="customer",
        full_name="public.customer",
        columns=[
            ColumnMetadata(
                name="customer_id",
                data_type="integer",
                is_nullable=False,
                has_default=True,
                ordinal_position=1,
            ),
            ColumnMetadata(
                name="first_name",
                data_type="text",
                is_nullable=False,
                has_default=False,
                ordinal_position=2,
            ),
        ],
        primary_key=["customer_id"],
        related_tables=["public.payment"],
    )
    payment_table = TableMetadata(
        schema_name="public",
        table_name="payment",
        full_name="public.payment",
        columns=[
            ColumnMetadata(
                name="payment_id",
                data_type="integer",
                is_nullable=False,
                has_default=True,
                ordinal_position=1,
            ),
            ColumnMetadata(
                name="customer_id",
                data_type="integer",
                is_nullable=False,
                has_default=False,
                ordinal_position=2,
            ),
            ColumnMetadata(
                name="amount",
                data_type="numeric",
                is_nullable=False,
                has_default=False,
                ordinal_position=3,
            ),
            ColumnMetadata(
                name="payment_date",
                data_type="timestamp",
                is_nullable=False,
                has_default=False,
                ordinal_position=4,
            ),
        ],
        primary_key=["payment_id"],
        foreign_keys=[
            ForeignKeyMetadata(
                name="payment_customer_id_fkey",
                source_schema="public",
                source_table="payment",
                source_columns=["customer_id"],
                target_schema="public",
                target_table="customer",
                target_columns=["customer_id"],
            )
        ],
        related_tables=["public.customer"],
    )

    return DatabaseSchema(tables=[customer_table, payment_table])


@pytest.fixture
def admin_connection_settings() -> PostgresConnectionSettings:
    """A user that can create schemas and roles, for tests against the local demo database.

    ASKDATA_TEST_ADMIN_URL overrides the local Docker default. Skips when it is not reachable.
    """
    url = os.environ.get("ASKDATA_TEST_ADMIN_URL", "postgresql://postgres:postgres@localhost:55432/pagila")
    parsed = conninfo_to_dict(url)
    settings = PostgresConnectionSettings(
        host=parsed.get("host", "localhost"),
        port=int(parsed.get("port", 5432)),
        database=parsed.get("dbname", "postgres"),
        user=parsed.get("user", "postgres"),
        password=parsed.get("password", ""),
        sslmode=parsed.get("sslmode", "prefer"),
    )
    try:
        psycopg.connect(**{**build_postgres_connection_kwargs(connection_settings=settings), "connect_timeout": 3}).close()
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc.__class__.__name__}")
    return settings


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
