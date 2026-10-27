"""Introspection against a real PostgreSQL (the local demo container).

Builds a throwaway schema with partitioned tables and checks that the schema the app
sees has the partitioned parents (with columns, keys and joins) and none of the
partitions. Runs as the admin user from the `admin_connection_settings` fixture (the app's own
user is read-only and cannot create schemas). Skipped when no database is reachable.
"""

from collections.abc import Iterator

import psycopg
import pytest

from app.db.connection import build_postgres_connection_kwargs
from app.schemas.data_source import PostgresConnectionSettings
from app.services.schema_service import SchemaService

TEST_SCHEMA = "askdata_test_partitions"

SETUP_SQL = f"""
DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE;
CREATE SCHEMA {TEST_SCHEMA};

CREATE TABLE {TEST_SCHEMA}.customer (customer_id integer PRIMARY KEY);

-- Foreign key declared on each partition only (how Pagila declares payment).
CREATE TABLE {TEST_SCHEMA}.ledger (
    ledger_id integer,
    customer_id integer,
    paid_on date,
    PRIMARY KEY (ledger_id, paid_on)
) PARTITION BY RANGE (paid_on);
CREATE TABLE {TEST_SCHEMA}.ledger_2022 PARTITION OF {TEST_SCHEMA}.ledger
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE {TEST_SCHEMA}.ledger_2023 PARTITION OF {TEST_SCHEMA}.ledger
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
ALTER TABLE {TEST_SCHEMA}.ledger_2022 ADD CONSTRAINT ledger_2022_customer_fk
    FOREIGN KEY (customer_id) REFERENCES {TEST_SCHEMA}.customer;
ALTER TABLE {TEST_SCHEMA}.ledger_2023 ADD CONSTRAINT ledger_2023_customer_fk
    FOREIGN KEY (customer_id) REFERENCES {TEST_SCHEMA}.customer;

-- Foreign key declared on the parent (PostgreSQL clones it onto the partitions).
CREATE TABLE {TEST_SCHEMA}.invoice (
    invoice_id integer,
    customer_id integer REFERENCES {TEST_SCHEMA}.customer,
    issued_on date,
    PRIMARY KEY (invoice_id, issued_on)
) PARTITION BY RANGE (issued_on);
CREATE TABLE {TEST_SCHEMA}.invoice_2022 PARTITION OF {TEST_SCHEMA}.invoice
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
COMMENT ON COLUMN {TEST_SCHEMA}.invoice.customer_id IS 'Billed customer';
"""


@pytest.fixture
def partitioned_schema(admin_connection_settings: PostgresConnectionSettings) -> Iterator[str]:
    connection = psycopg.connect(
        **build_postgres_connection_kwargs(connection_settings=admin_connection_settings),
        autocommit=True,
    )
    with connection:
        connection.execute(SETUP_SQL)
        try:
            yield TEST_SCHEMA
        finally:
            connection.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")


def _load(admin_connection_settings: PostgresConnectionSettings, schema_name: str):
    return SchemaService().load_schema(connection_settings=admin_connection_settings, schema_allowlist=[schema_name])


def test_introspection_shows_partitioned_parents_and_hides_partitions(
    partitioned_schema, admin_connection_settings
) -> None:
    schema = _load(admin_connection_settings, partitioned_schema)
    tables = {table.table_name: table for table in schema.tables}

    assert set(tables) == {"customer", "ledger", "invoice"}

    ledger = tables["ledger"]
    assert [column.name for column in ledger.columns] == ["ledger_id", "customer_id", "paid_on"]
    assert ledger.primary_key == ["ledger_id", "paid_on"]


def test_introspection_reports_partition_foreign_keys_once_on_the_parent(
    partitioned_schema, admin_connection_settings
) -> None:
    schema = _load(admin_connection_settings, partitioned_schema)
    tables = {table.table_name: table for table in schema.tables}

    ledger_keys = tables["ledger"].foreign_keys
    assert len(ledger_keys) == 1
    assert ledger_keys[0].name == "ledger_customer_id_fkey"
    assert ledger_keys[0].source_columns == ["customer_id"]
    assert ledger_keys[0].target_table == "customer"
    assert ledger_keys[0].target_columns == ["customer_id"]

    invoice_keys = tables["invoice"].foreign_keys
    assert len(invoice_keys) == 1
    assert invoice_keys[0].name == "invoice_customer_id_fkey"
    assert invoice_keys[0].target_table == "customer"

    assert tables["customer"].related_tables == [
        f"{partitioned_schema}.invoice",
        f"{partitioned_schema}.ledger",
    ]


def test_introspection_reads_column_comments_on_partitioned_tables(
    partitioned_schema, admin_connection_settings
) -> None:
    schema = _load(admin_connection_settings, partitioned_schema)
    invoice = next(table for table in schema.tables if table.table_name == "invoice")
    customer_id = next(column for column in invoice.columns if column.name == "customer_id")

    assert customer_id.description == "Billed customer"
