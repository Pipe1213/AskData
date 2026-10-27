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
    assert context.intent_hints.metric_hints == ["payment.amount"]
    assert context.intent_hints.time_hints == ["payment.payment_date"]


def _table(name: str, columns: list[tuple[str, str]], keys: list[tuple[str, str]] = (), description=None):
    from app.db.metadata_models import ColumnMetadata, ForeignKeyMetadata, TableMetadata

    return TableMetadata(
        schema_name="public",
        table_name=name,
        full_name=f"public.{name}",
        description=description,
        columns=[
            ColumnMetadata(
                name=column_name,
                data_type=data_type,
                is_nullable=True,
                has_default=False,
                ordinal_position=position,
                description=column_description,
            )
            for position, (column_name, data_type, *rest) in enumerate(columns, start=1)
            for column_description in [rest[0] if rest else None]
        ],
        primary_key=[columns[0][0]],
        foreign_keys=[
            ForeignKeyMetadata(
                name=f"{name}_{column}_fkey",
                source_schema="public",
                source_table=name,
                source_columns=[column],
                target_schema="public",
                target_table=target,
                target_columns=[column],
            )
            for column, target in keys
        ],
    )


def _linked_schema():
    """A shop whose sales reach a category only through order lines and products."""
    from app.db.metadata_models import DatabaseSchema

    tables = [
        _table("genre", [("genre_id", "integer"), ("label", "text", "Display name of the genre")]),
        _table("product", [("product_id", "integer"), ("genre_id", "integer"), ("title", "text")], [("genre_id", "genre")]),
        _table(
            "order_line",
            [("line_id", "integer"), ("sale_id", "integer"), ("product_id", "integer")],
            [("sale_id", "sale"), ("product_id", "product")],
        ),
        _table(
            "sale",
            [("sale_id", "integer"), ("amount", "numeric"), ("sold_on", "date"), ("last_update", "timestamp")],
        ),
        _table("warehouse", [("warehouse_id", "integer"), ("city", "text")]),
    ]
    related: dict[str, set[str]] = {table.full_name: set() for table in tables}
    for table in tables:
        for key in table.foreign_keys:
            related[table.full_name].add(f"public.{key.target_table}")
            related[f"public.{key.target_table}"].add(table.full_name)
    for table in tables:
        table.related_tables = sorted(related[table.full_name])
    return DatabaseSchema(tables=tables)


def _retrieve(question: str, **kwargs):
    from app.services.planner_service import PlannerService

    plan = PlannerService().build_plan(question)
    return RetrievalService().retrieve_schema_context(question, _linked_schema(), plan=plan, **kwargs)


def test_retrieval_adds_the_tables_that_join_distant_tables() -> None:
    context = _retrieve("Revenue by genre", max_tables=2)

    names = [table.table_name for table in context.tables]
    assert set(names[:2]) == {"sale", "genre"}
    assert set(names[2:]) == {"order_line", "product"}
    assert context.join_paths == [["public.genre", "public.product", "public.order_line", "public.sale"]]
    assert {(r.source_table, r.target_table) for r in context.relationships} >= {
        ("public.order_line", "public.sale"),
        ("public.order_line", "public.product"),
        ("public.product", "public.genre"),
    }


def test_retrieval_prefers_business_dates_over_bookkeeping_dates() -> None:
    context = _retrieve("Monthly revenue trend")

    sale = next(table for table in context.tables if table.table_name == "sale")
    assert [column.name for column in sale.selected_columns][:2] == ["amount", "sold_on"]
    assert context.intent_hints.time_hints == ["sale.sold_on"]


def test_sql_prompt_shows_column_comments_and_join_paths() -> None:
    from app.llm.prompt_builders import build_sql_generation_messages

    context = _retrieve("Revenue by genre", max_tables=2)
    messages = build_sql_generation_messages("Revenue by genre", context, max_result_rows=100)
    user_prompt = messages[1]["content"]

    assert "label (text) - Display name of the genre" in user_prompt
    assert "public.genre -> public.product -> public.order_line -> public.sale" in user_prompt


def test_word_forms_match_business_concepts() -> None:
    from app.services.business_vocabulary import has_money_intent, word_forms

    assert "spend" in word_forms("spending")
    assert "ship" in word_forms("shipped")
    assert has_money_intent({"highest", "total", "spending"})
    assert not has_money_intent({"highest", "rating"})


def test_retrieval_keeps_a_tables_measures_when_no_word_points_at_them() -> None:
    from app.db.metadata_models import ColumnMetadata, DatabaseSchema, TableMetadata

    def column(name: str, data_type: str, position: int) -> ColumnMetadata:
        return ColumnMetadata(name=name, data_type=data_type, is_nullable=False, has_default=False, ordinal_position=position)

    payment = TableMetadata(
        schema_name="public",
        table_name="payment",
        full_name="public.payment",
        columns=[
            column("payment_id", "integer", 1),
            column("customer_id", "integer", 2),
            column("staff_id", "integer", 3),
            column("rental_id", "integer", 4),
            column("payment_date", "timestamp", 5),
            column("amount", "numeric", 6),
        ],
        primary_key=["payment_id"],
    )

    context = RetrievalService().retrieve_schema_context(
        "Which customers rank highest by payments?", DatabaseSchema(tables=[payment])
    )

    selected = {column.name for column in context.tables[0].selected_columns}
    assert "amount" in selected
