import json

from app.schemas.retrieval import RetrievedSchemaContext


def build_sql_generation_messages(
    question: str,
    schema_context: RetrievedSchemaContext,
    max_result_rows: int,
) -> list[dict[str, str]]:
    system_prompt = f"""
You are an expert PostgreSQL analytics assistant.
Generate a single read-only PostgreSQL query that answers the user's question.

Rules:
- Return only one query.
- The query must be a SELECT statement or a WITH clause that ends in SELECT.
- Do not generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, or transaction statements.
- Prefer explicit joins using the provided schema relationships.
- Use only tables and columns supported by the schema context below.
- If the question implies a row-level result set that could be large, include a practical LIMIT no greater than {max_result_rows}.
- Aggregate queries without LIMIT are acceptable when the output is naturally small.
- Use PostgreSQL syntax only.
- Do not invent columns or tables.
- Return structured JSON matching the required schema.
""".strip()

    user_prompt = f"""
User question:
{question}

Retrieved schema context:
{_format_schema_context(schema_context)}

Return:
- `sql`: the generated PostgreSQL query
- `used_tables`: the tables used by the query
- `notes`: brief caveats only if needed
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _format_schema_context(schema_context: RetrievedSchemaContext) -> str:
    sections: list[str] = []

    for table in schema_context.tables:
        column_parts = [
            f"{column.name} ({column.data_type})"
            for column in table.selected_columns
        ]
        sections.append(f"Table: {table.full_name}\nColumns: {', '.join(column_parts)}")

    if schema_context.relationships:
        relationship_lines = [
            (
                f"- {relationship.source_table}.{', '.join(relationship.source_columns)} "
                f"-> {relationship.target_table}.{', '.join(relationship.target_columns)}"
            )
            for relationship in schema_context.relationships
        ]
        sections.append("Relationships:\n" + "\n".join(relationship_lines))

    if schema_context.warnings:
        warning_lines = [f"- {warning}" for warning in schema_context.warnings]
        sections.append("Retrieval warnings:\n" + "\n".join(warning_lines))

    return "\n\n".join(sections)


def build_answer_summary_messages(
    question: str,
    generated_sql: str,
    columns: list[str],
    rows: list[list[object]],
) -> list[dict[str, str]]:
    sample_rows = rows[:5]
    system_prompt = """
You summarize SQL query results for a business user.
Write a short, factual answer grounded only in the user question, the SQL, the result columns, and the returned rows.
Do not invent trends, causes, or values that are not present in the results.
Keep the answer concise.
""".strip()

    user_prompt = f"""
User question:
{question}

Generated SQL:
{generated_sql}

Result columns:
{json.dumps(columns)}

Result rows:
{json.dumps(sample_rows, default=str)}
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_sql_repair_messages(
    question: str,
    schema_context: RetrievedSchemaContext,
    previous_sql: str,
    failure_message: str,
    max_result_rows: int,
) -> list[dict[str, str]]:
    system_prompt = f"""
You are repairing a PostgreSQL analytics query.
Produce one corrected read-only PostgreSQL query that answers the original question.

Rules:
- Return only one query.
- The query must be a SELECT statement or a WITH clause that ends in SELECT.
- Do not generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, or transaction statements.
- Use only tables and columns supported by the schema context below.
- Correct the previous failure without changing the user intent.
- If the question implies a row-level result set that could be large, include a practical LIMIT no greater than {max_result_rows}.
- Aggregate queries without LIMIT are acceptable when the output is naturally small.
- Use PostgreSQL syntax only.
- Return structured JSON matching the required schema.
""".strip()

    user_prompt = f"""
Original user question:
{question}

Retrieved schema context:
{_format_schema_context(schema_context)}

Previous SQL:
{previous_sql}

Failure to correct:
{failure_message}

Return:
- `sql`: the corrected PostgreSQL query
- `used_tables`: the tables used by the corrected query
- `notes`: brief caveats only if needed
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
