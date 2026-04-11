from app.db.metadata_models import DatabaseSchema, TableMetadata
from app.services.dataset_adapters import resolve_dataset_adapter


def test_resolve_dataset_adapter_returns_generic_for_non_pagila_schema(sample_schema) -> None:
    adapter = resolve_dataset_adapter(sample_schema)

    assert adapter.name == "generic_postgres"


def test_resolve_dataset_adapter_returns_pagila_for_pagila_like_schema() -> None:
    schema = DatabaseSchema(
        tables=[
            TableMetadata(schema_name="public", table_name="payment", full_name="public.payment"),
            TableMetadata(schema_name="public", table_name="rental", full_name="public.rental"),
            TableMetadata(schema_name="public", table_name="inventory", full_name="public.inventory"),
            TableMetadata(schema_name="public", table_name="film_category", full_name="public.film_category"),
            TableMetadata(schema_name="public", table_name="category", full_name="public.category"),
            TableMetadata(schema_name="public", table_name="customer", full_name="public.customer"),
        ]
    )

    adapter = resolve_dataset_adapter(schema)

    assert adapter.name == "pagila"


def test_resolve_dataset_adapter_handles_plural_generic_tables() -> None:
    schema = DatabaseSchema(
        tables=[
            TableMetadata(schema_name="public", table_name="customers", full_name="public.customers"),
            TableMetadata(schema_name="public", table_name="orders", full_name="public.orders"),
            TableMetadata(schema_name="public", table_name="payments", full_name="public.payments"),
            TableMetadata(schema_name="public", table_name="shipments", full_name="public.shipments"),
        ]
    )

    adapter = resolve_dataset_adapter(schema)

    assert adapter.name == "generic_postgres"
