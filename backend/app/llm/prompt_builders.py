import json
from decimal import Decimal

from app.db.metadata_models import DatabaseSchema
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
- `assumptions`: up to 3 short statements, in plain words for a reader who cannot read SQL, of the
  choices behind the numbers: what a measure means (e.g. which amounts are added up), the time period
  covered, filters applied, how ties or missing values are handled. Name business concepts, not
  tables or columns. Leave empty when the question leaves nothing to choose.
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_question_triage_messages(
    question: str,
    schema_context: RetrievedSchemaContext,
    schema: DatabaseSchema,
    conversation_context: list[ConversationMessage] | None = None,
) -> list[dict[str, str]]:
    system_prompt = """
You check a user's question against a PostgreSQL database before any SQL is written.
The users cannot read SQL, so a confident answer to a question they did not mean, or an answer
built on data the database does not have, is the worst outcome. Pick exactly one decision.

"answerable" (the usual case):
- The database records the data the question needs, and the question has one clear reading,
  or one reading that most people asking it would mean.
- Small choices are not a reason to ask: which of several date columns to use, ties, a sensible
  default number of rows, rounding, whether to include rows with missing values. The answer will
  state those choices as assumptions.
- Relative or uncovered time periods ("this year", "last month", a year with no data) are
  answerable: the answer will use the period the data covers and say so.
- Follow-ups that refine an earlier answered question (a smaller limit, a different grouping,
  a filter) are answerable when the earlier question was.
- If the assistant just asked the user to choose between readings, and the user's message picks
  one or restates the question with one reading, it is answerable. Never ask twice about the
  same choice.

"ambiguous":
- The question supports two or more reasonable readings with this database that would give
  materially different answers (a different measure, a different entity the measure is
  attributed to, or a different population), and nothing in the question or the conversation
  picks one, and no reading is clearly the one most people would mean.

"unanswerable":
- The question needs facts that no table or column records and that cannot be derived from
  what is recorded. Judge from the full column lists below; if a column could reasonably hold
  the fact, the question is answerable.
- Do not decline because a join path is long or because a time period is missing.

Writing rules for the text fields: plain words for a non-technical reader; name business
concepts, never table or column names; no SQL.
- reason: one sentence. Ambiguous: what is unclear. Unanswerable: what data is missing and what
  the database records instead. Answerable: empty.
- clarification_question: ambiguous only; one short question. Otherwise empty.
- options: ambiguous only; 2 to 4 options, each a complete, self-contained question that this
  database can answer as written (it will be sent back as the user's next question). Otherwise empty.
- alternatives: unanswerable only; 1 or 2 complete questions this database can answer that come
  closest to what the user wanted. Otherwise empty.
Return structured JSON matching the required schema.
""".strip()

    user_prompt = f"""
User question:
{question}

Recent conversation context:
{_format_conversation_context(conversation_context)}

Database tables most relevant to the question (all columns):
{_format_triage_schema(schema_context, schema)}
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _format_triage_schema(
    schema_context: RetrievedSchemaContext,
    schema: DatabaseSchema,
    max_other_tables: int = 200,
) -> str:
    tables_by_name = {table.full_name: table for table in schema.tables}
    retrieved_names = [table.full_name for table in schema_context.tables]
    sections: list[str] = []

    for full_name in retrieved_names:
        table = tables_by_name.get(full_name)
        if table is None:
            continue
        column_parts = []
        for column in table.columns:
            part = f"{column.name} ({column.data_type})"
            if column.description:
                part += f" - {column.description}"
            column_parts.append(part)
        header = f"Table: {table.full_name}"
        if table.description:
            header += f" - {table.description}"
        sections.append(f"{header}\nColumns: {', '.join(column_parts)}")

    if schema_context.relationships:
        relationship_lines = [
            (
                f"- {relationship.source_table}.{', '.join(relationship.source_columns)} "
                f"-> {relationship.target_table}.{', '.join(relationship.target_columns)}"
            )
            for relationship in schema_context.relationships
        ]
        sections.append("Relationships:\n" + "\n".join(relationship_lines))

    other_tables = [name for name in tables_by_name if name not in set(retrieved_names)]
    if other_tables:
        listed = other_tables[:max_other_tables]
        line = "Other tables in the database (columns not shown): " + ", ".join(listed)
        if len(other_tables) > len(listed):
            line += f", and {len(other_tables) - len(listed)} more"
        sections.append(line)

    return "\n\n".join(sections)


def _format_schema_context(schema_context: RetrievedSchemaContext) -> str:
    sections: list[str] = []

    for table in schema_context.tables:
        column_parts = [
            f"{column.name} ({column.data_type})" + (f" - {column.description}" if column.description else "")
            for column in table.selected_columns
        ]
        header = f"Table: {table.full_name}"
        if table.description:
            header += f" - {table.description}"
        sections.append(f"{header}\nColumns: {', '.join(column_parts)}")

    if schema_context.relationships:
        relationship_lines = [
            (
                f"- {relationship.source_table}.{', '.join(relationship.source_columns)} "
                f"-> {relationship.target_table}.{', '.join(relationship.target_columns)}"
            )
            for relationship in schema_context.relationships
        ]
        sections.append("Relationships:\n" + "\n".join(relationship_lines))

    if schema_context.join_paths:
        path_lines = [f"- {' -> '.join(path)}" for path in schema_context.join_paths]
        sections.append(
            "Join paths (these tables connect only through the tables in between):\n" + "\n".join(path_lines)
        )

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


SUMMARY_SAMPLE_ROWS = 20


def build_answer_summary_messages(
    question: str,
    generated_sql: str,
    columns: list[str],
    rows: list[list[object]],
    row_count: int | None = None,
    assumptions: list[str] | None = None,
    data_coverage: list[str] | None = None,
) -> list[dict[str, str]]:
    total_rows = len(rows) if row_count is None else row_count
    sample_rows = rows[:SUMMARY_SAMPLE_ROWS]
    shown_note = (
        f"all {total_rows} rows"
        if len(sample_rows) == total_rows
        else f"the first {len(sample_rows)} of {total_rows} rows"
    )
    system_prompt = """
You answer a business user's question from the result of a database query, in 1 or 2 sentences.
The reader cannot check the query, so every name and number you write must come from the result rows.

- Lead with the answer: name the top or main result and its value.
- For rankings: if other rows share the top value, say it is a tie and name them. When it helps,
  give the range of the returned values (e.g. "the top 10 range from X to Y").
- For trends: name the highest and lowest periods shown, with their values.
- Copy numbers as they appear in the rows (money with 2 decimals). Do not compute new numbers
  such as sums, differences or percentages that are not in the rows.
- The result has exactly the stated number of rows. Never say it has fewer or more.
- If only some rows are shown, describe the whole result only through the "over all rows" facts;
  never present a pattern seen in the shown rows as true for the whole result.
- If the result has no rows, say plainly that nothing matched, and if the data coverage is given,
  say what period or range the data does cover.
- Do not repeat the assumptions (they are shown separately), and do not mention SQL, tables or columns.
- Plain text only, no markdown. Write people's and places' names in normal capitalization.
""".strip()

    user_prompt = f"""
User question:
{question}

Generated SQL:
{generated_sql}

Assumptions already shown to the user:
{_format_bullets(assumptions)}

Data coverage:
{_format_bullets(data_coverage)}

Result: {total_rows} rows. Columns:
{json.dumps(columns)}

Result rows ({shown_note}):
{json.dumps(sample_rows, default=str)}

Over all {total_rows} rows:
{_format_bullets(_column_extremes(columns, rows) if len(sample_rows) < total_rows else None)}
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _column_extremes(columns: list[str], rows: list[list[object]]) -> list[str]:
    """Highest and lowest value of each numeric column over all rows, with that row's labels."""
    facts: list[str] = []
    for index, column in enumerate(columns):
        if column.lower() == "id" or column.lower().endswith("_id"):
            continue
        numeric_rows = [
            row for row in rows
            if index < len(row) and isinstance(row[index], (int, float, Decimal)) and not isinstance(row[index], bool)
        ]
        if not numeric_rows:
            continue
        for word, pick in (("highest", max), ("lowest", min)):
            row = pick(numeric_rows, key=lambda candidate: candidate[index])
            labels = [
                str(value)
                for position, value in enumerate(row)
                if position != index and not isinstance(value, (int, float, Decimal)) and value is not None
            ]
            facts.append(f"{column} {word}: {row[index]} ({', '.join(labels) or 'no label'})")
    return facts


def _format_bullets(items: list[str] | None) -> str:
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)


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
- `assumptions`: up to 3 short statements, in plain words for a reader who cannot read SQL, of the
  choices behind the numbers: what a measure means (e.g. which amounts are added up), the time period
  covered, filters applied, how ties or missing values are handled. Name business concepts, not
  tables or columns. Leave empty when the question leaves nothing to choose.
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
    return "Hints:\n" + "\n".join(hints)


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
        "- For a current-relative period like 'this year' or 'this month', anchor the period on the latest date "
        "in the data (for example the year of MAX of the relevant date column), not on CURRENT_DATE: the data may "
        "be historical.\n"
        "- Do not build a zero-filled calendar (generate_series) for such a period; return the periods that have data."
    )
