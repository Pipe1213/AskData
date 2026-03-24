from app.services import schema_service as schema_service_module
from app.services.schema_service import SchemaService


def test_schema_service_normalizes_tables_columns_and_relationships(monkeypatch) -> None:
    monkeypatch.setattr(
        schema_service_module,
        "fetch_tables",
        lambda settings=None: [
            {
                "schema_name": "public",
                "table_name": "customer",
                "description": "Customer table",
            },
            {
                "schema_name": "public",
                "table_name": "payment",
                "description": "Payment table",
            },
        ],
    )
    monkeypatch.setattr(
        schema_service_module,
        "fetch_columns",
        lambda settings=None: [
            {
                "schema_name": "public",
                "table_name": "customer",
                "column_name": "customer_id",
                "data_type": "integer",
                "is_nullable": False,
                "has_default": True,
                "ordinal_position": 1,
                "description": None,
            },
            {
                "schema_name": "public",
                "table_name": "payment",
                "column_name": "payment_id",
                "data_type": "integer",
                "is_nullable": False,
                "has_default": True,
                "ordinal_position": 1,
                "description": None,
            },
            {
                "schema_name": "public",
                "table_name": "payment",
                "column_name": "customer_id",
                "data_type": "integer",
                "is_nullable": False,
                "has_default": False,
                "ordinal_position": 2,
                "description": None,
            },
        ],
    )
    monkeypatch.setattr(
        schema_service_module,
        "fetch_primary_keys",
        lambda settings=None: [
            {
                "schema_name": "public",
                "table_name": "customer",
                "column_name": "customer_id",
                "ordinal_position": 1,
            },
            {
                "schema_name": "public",
                "table_name": "payment",
                "column_name": "payment_id",
                "ordinal_position": 1,
            },
        ],
    )
    monkeypatch.setattr(
        schema_service_module,
        "fetch_foreign_keys",
        lambda settings=None: [
            {
                "constraint_name": "payment_customer_id_fkey",
                "source_schema": "public",
                "source_table": "payment",
                "source_column": "customer_id",
                "target_schema": "public",
                "target_table": "customer",
                "target_column": "customer_id",
                "ordinal_position": 1,
            }
        ],
    )

    service = SchemaService()
    schema = service.load_schema()

    assert len(schema.tables) == 2
    payment_table = next(table for table in schema.tables if table.table_name == "payment")
    customer_table = next(table for table in schema.tables if table.table_name == "customer")

    assert payment_table.primary_key == ["payment_id"]
    assert payment_table.foreign_keys[0].target_table == "customer"
    assert "public.customer" in payment_table.related_tables
    assert "public.payment" in customer_table.related_tables
