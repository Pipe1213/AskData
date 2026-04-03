from app.services.retrieval_service import RetrievalService
from app.db.metadata_models import ColumnMetadata, DatabaseSchema, TableMetadata


def test_retrieval_selects_relevant_tables_and_columns(sample_schema) -> None:
    service = RetrievalService()

    context = service.retrieve_schema_context(
        "What is the total payment amount by customer?",
        sample_schema,
    )

    assert context.tables
    assert context.tables[0].table_name == "payment"
    assert any(column.name == "amount" for column in context.tables[0].selected_columns)
    assert any(
        relationship.target_table == "public.customer"
        for relationship in context.relationships
    )


def test_retrieval_builds_prompt_context(sample_schema) -> None:
    service = RetrievalService()
    context = service.retrieve_schema_context(
        "Show payment amount by customer",
        sample_schema,
    )

    prompt_context = service.build_prompt_context(context)

    assert "Table: public.payment" in prompt_context
    assert "Relationships:" in prompt_context


def test_retrieval_boosts_payment_for_customer_spend_questions(sample_schema) -> None:
    service = RetrievalService()

    context = service.retrieve_schema_context(
        "Which customers spent the most in total?",
        sample_schema,
    )

    assert context.tables
    payment_table = next((table for table in context.tables if table.table_name == "payment"), None)
    assert payment_table is not None
    selected_column_names = {column.name for column in payment_table.selected_columns}
    assert "amount" in selected_column_names
    assert "customer_id" in selected_column_names


def test_retrieval_adds_intent_hints_for_revenue_questions(sample_schema) -> None:
    service = RetrievalService()

    context = service.retrieve_schema_context(
        "What are the top categories by revenue each month?",
        sample_schema,
    )

    assert "revenue" in context.intent_hints.intent_tags
    assert "time" in context.intent_hints.intent_tags
    assert "amount" in context.intent_hints.metric_hints


def test_retrieval_treats_partition_tables_as_payment_family() -> None:
    service = RetrievalService()
    schema = DatabaseSchema(
        tables=[
            TableMetadata(
                schema_name="public",
                table_name="payment_p2022_01",
                full_name="public.payment_p2022_01",
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
                ],
                primary_key=["payment_id"],
            ),
            TableMetadata(
                schema_name="public",
                table_name="customer",
                full_name="public.customer",
                columns=[
                    ColumnMetadata(
                        name="customer_id",
                        data_type="integer",
                        is_nullable=False,
                        has_default=False,
                        ordinal_position=1,
                    )
                ],
                primary_key=["customer_id"],
            ),
        ]
    )

    context = service.retrieve_schema_context(
        "Which customers spent the most in total?",
        schema,
    )

    assert any(table.table_name == "payment_p2022_01" for table in context.tables)
