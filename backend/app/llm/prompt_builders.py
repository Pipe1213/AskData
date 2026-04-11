import json

from app.schemas.query import ConversationMessage, MemoryContext, QueryPlan
from app.schemas.retrieval import RetrievedSchemaContext


def build_sql_generation_messages(
    question: str,
    schema_context: RetrievedSchemaContext,
    max_result_rows: int,
    conversation_context: list[ConversationMessage] | None = None,
    plan: QueryPlan | None = None,
    memory_context: MemoryContext | None = None,
    dataset_hints: list[str] | None = None,
) -> list[dict[str, str]]:
    dataset_hint_section = _format_dataset_hints(dataset_hints)
    relative_time_hint_section = _format_relative_time_hint(question)
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
{dataset_hint_section}
{relative_time_hint_section}
""".strip()

    user_prompt = f"""
User question:
{question}

Recent conversation context:
{_format_conversation_context(conversation_context)}

Retrieved schema context:
{_format_schema_context(schema_context)}

Intent hints:
{_format_intent_hints(schema_context)}

Planner output:
{_format_query_plan(plan)}

Structured memory context:
{_format_memory_context(memory_context)}

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


def _format_intent_hints(schema_context: RetrievedSchemaContext) -> str:
    hints = schema_context.intent_hints
    sections: list[str] = []

    if hints.intent_tags:
        sections.append("Intent tags: " + ", ".join(hints.intent_tags))
    if hints.metric_hints:
        sections.append("Metric hints: " + ", ".join(hints.metric_hints))
    if hints.dimension_hints:
        sections.append("Dimension hints: " + ", ".join(hints.dimension_hints))
    if hints.time_hints:
        sections.append("Time hints: " + ", ".join(hints.time_hints))
    if hints.table_family_hints:
        sections.append("Table families: " + ", ".join(hints.table_family_hints))

    return "\n".join(sections) if sections else "None"


def _format_conversation_context(
    conversation_context: list[ConversationMessage] | None,
) -> str:
    if not conversation_context:
        return "None"

    return "\n".join(
        f"- {message.role}: {message.content}"
        for message in conversation_context
    )


def _format_query_plan(plan: QueryPlan | None) -> str:
    if plan is None:
        return "None"

    sections = [
        f"Task type: {plan.task_type}",
        f"Execution strategy: {plan.execution_strategy}",
        f"Interpreted goal: {plan.interpreted_goal}",
        f"Confidence: {plan.confidence}",
    ]
    if plan.metric_targets:
        sections.append("Metric targets: " + ", ".join(plan.metric_targets))
    if plan.dimension_targets:
        sections.append("Dimension targets: " + ", ".join(plan.dimension_targets))
    if plan.time_targets:
        sections.append("Time targets: " + ", ".join(plan.time_targets))
    if plan.candidate_table_families:
        sections.append("Candidate table families: " + ", ".join(plan.candidate_table_families))
    if plan.ambiguity_notes:
        sections.append("Ambiguity notes: " + "; ".join(plan.ambiguity_notes))
    if plan.memory_summary:
        sections.append("Session memory: " + plan.memory_summary)

    return "\n".join(sections)


def _format_memory_context(memory_context: MemoryContext | None) -> str:
    if memory_context is None:
        return "None"

    sections: list[str] = []
    if memory_context.memory_summary:
        sections.append("Memory summary: " + memory_context.memory_summary)
    if memory_context.suggested_metric_targets:
        sections.append("Inherited metric targets: " + ", ".join(memory_context.suggested_metric_targets))
    if memory_context.suggested_dimension_targets:
        sections.append("Inherited dimension targets: " + ", ".join(memory_context.suggested_dimension_targets))
    if memory_context.suggested_time_targets:
        sections.append("Inherited time targets: " + ", ".join(memory_context.suggested_time_targets))
    if memory_context.suggested_table_families:
        sections.append("Inherited table families: " + ", ".join(memory_context.suggested_table_families))
    if memory_context.inherited_from_turn_ids:
        sections.append("Inherited from turn ids: " + ", ".join(memory_context.inherited_from_turn_ids))

    return "\n".join(sections) if sections else "None"


def build_answer_summary_messages(
    question: str,
    generated_sql: str,
    columns: list[str],
    rows: list[list[object]],
) -> list[dict[str, str]]:
    sample_rows = rows[:5]
    system_prompt = """
You summarize SQL query results for a business user.
Write a short, factual answer that answers the user's question directly.
Lead with the business answer, not the query mechanics.
Prefer clean business phrasing and readable date/number labels.
For rankings, name the top result directly.
For trends, mention the most visible pattern or peak shown in the returned rows.
Avoid phrases like "The query returned..." or "The leading result was..." unless there is no better direct answer.
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
    conversation_context: list[ConversationMessage] | None = None,
    plan: QueryPlan | None = None,
    memory_context: MemoryContext | None = None,
    dataset_hints: list[str] | None = None,
) -> list[dict[str, str]]:
    dataset_hint_section = _format_dataset_hints(dataset_hints)
    relative_time_hint_section = _format_relative_time_hint(question)
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
{dataset_hint_section}
{relative_time_hint_section}
""".strip()

    user_prompt = f"""
Original user question:
{question}

Recent conversation context:
{_format_conversation_context(conversation_context)}

Retrieved schema context:
{_format_schema_context(schema_context)}

Intent hints:
{_format_intent_hints(schema_context)}

Planner output:
{_format_query_plan(plan)}

Structured memory context:
{_format_memory_context(memory_context)}

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


def build_sql_semantic_review_messages(
    question: str,
    schema_context: RetrievedSchemaContext,
    generated_sql: str,
    conversation_context: list[ConversationMessage] | None = None,
    plan: QueryPlan | None = None,
    memory_context: MemoryContext | None = None,
    dataset_hints: list[str] | None = None,
) -> list[dict[str, str]]:
    dataset_hint_section = _format_dataset_hints(dataset_hints)
    system_prompt = """
You review a generated PostgreSQL analytics query before execution.
Decide whether the SQL appears to answer the user's business question correctly enough to continue.

Rules:
- Focus on business intent alignment, not syntax.
- Check whether the likely metric, grouping, and time/filter logic match the question.
- Be strict about obviously wrong interpretations.
- Do not suggest destructive SQL.
- Return structured JSON matching the required schema.
""".strip()
    if dataset_hint_section:
        system_prompt += "\n\n" + dataset_hint_section

    user_prompt = f"""
User question:
{question}

Recent conversation context:
{_format_conversation_context(conversation_context)}

Retrieved schema context:
{_format_schema_context(schema_context)}

Intent hints:
{_format_intent_hints(schema_context)}

Planner output:
{_format_query_plan(plan)}

Structured memory context:
{_format_memory_context(memory_context)}

Candidate SQL:
{generated_sql}

Return:
- `should_rewrite`: true if the SQL likely answers the wrong business question or uses the wrong metric/grouping/time logic
- `issues`: short concrete reasons
- `suggested_focus`: one short instruction for what the corrected SQL should focus on
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _format_dataset_hints(dataset_hints: list[str] | None) -> str:
    base_hint = "- Use only the retrieved schema context. If the question cannot be answered safely from it, be conservative."
    hints = [base_hint, *(dataset_hints or [])]
    return "Dataset-specific hints:\n" + "\n".join(hints)


def _format_relative_time_hint(question: str) -> str:
    normalized_question = question.lower()
    relative_phrases = (
        "this year",
        "this month",
        "this quarter",
        "current year",
        "current month",
        "current quarter",
    )
    if not any(phrase in normalized_question for phrase in relative_phrases):
        return ""

    return (
        "Relative time hint:\n"
        "- If the question uses a current-relative period like 'this year' or 'this month' and the dataset is historical, "
        "prefer the latest available period in the data over the wall-clock current date when that is the only way to avoid an empty answer."
    )
