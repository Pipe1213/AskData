from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.metadata_models import (
    ColumnMetadata,
    DatabaseSchema,
    ForeignKeyMetadata,
    TableMetadata,
)
from app.main import create_app


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
def app():
    return create_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
