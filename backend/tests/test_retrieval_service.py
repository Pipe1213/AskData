from app.services.retrieval_service import RetrievalService


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
