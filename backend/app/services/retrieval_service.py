from collections import defaultdict

from app.db.metadata_models import DatabaseSchema, TableMetadata
from app.schemas.query import MemoryContext, QueryPlan
from app.schemas.retrieval import (
    RetrievedColumn,
    RetrievalIntentHints,
    RetrievedRelationship,
    RetrievedSchemaContext,
    RetrievedTable,
)
from app.services.business_vocabulary import (
    AVERAGE_NAME_WORDS,
    AVERAGE_WORDS,
    COMPARISON_WORDS,
    CONCEPTS,
    COUNT_WORDS,
    TOPK_WORDS,
    concepts_in,
    expand_question_tokens,
    has_money_intent,
    has_time_intent,
    head_word,
    is_business_date_column,
    is_key_column,
    is_label_column,
    is_numeric_type,
    name_words,
)
from app.utils.text import significant_tokens

MAX_JOIN_PATH_EDGES = 4
MAX_BRIDGE_TABLES = 3


class RetrievalService:
    def retrieve_schema_context(
        self,
        question: str,
        schema: DatabaseSchema,
        plan: QueryPlan | None = None,
        memory_context: MemoryContext | None = None,
        max_tables: int = 5,
        max_columns_per_table: int = 8,
        broaden: bool = False,
    ) -> RetrievedSchemaContext:
        question_tokens = significant_tokens(question)
        synonym_tokens = expand_question_tokens(question_tokens) - question_tokens
        time_intent = has_time_intent(question_tokens)
        table_scores: dict[str, float] = defaultdict(float)
        column_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for table in schema.tables:
            table_tokens = name_words(table.table_name)
            description_tokens = significant_tokens(table.description or "")

            exact_table_match = table.table_name.lower() in question.lower()
            if exact_table_match:
                table_scores[table.full_name] += 5.0

            matched_table_tokens = question_tokens & table_tokens
            table_scores[table.full_name] += len(matched_table_tokens) * 3.0

            matched_description_tokens = question_tokens & description_tokens
            table_scores[table.full_name] += len(matched_description_tokens) * 1.0
            table_head = head_word(table.table_name)
            if table_head in synonym_tokens and table_head not in matched_table_tokens:
                table_scores[table.full_name] += 2.2

            for column in table.columns:
                column_tokens = name_words(column.name) | significant_tokens(column.description or "")
                direct_column_boost = len(question_tokens & column_tokens) * 1.5
                semantic_column_boost = 0.0
                if not is_key_column(column.name):
                    semantic_column_boost = len(synonym_tokens & column_tokens) * 1.8
                total_column_boost = direct_column_boost + semantic_column_boost

                if total_column_boost > 0:
                    column_scores[table.full_name][column.name] += total_column_boost
                    table_scores[table.full_name] += total_column_boost * (1.0 if direct_column_boost else 0.8)

                # Dates matter for time questions, but they don't say which table: no table score.
                if time_intent and is_business_date_column(column.name, column.data_type):
                    column_scores[table.full_name][column.name] += 2.5

        if plan is not None:
            self._apply_plan_boosts(schema, plan, table_scores, column_scores)
        if memory_context is not None:
            self._apply_memory_boosts(
                schema=schema,
                plan=plan,
                memory_context=memory_context,
                question_tokens=question_tokens,
                table_scores=table_scores,
                column_scores=column_scores,
            )

        if broaden and plan is not None:
            self._apply_broader_retrieval_boosts(schema, plan, table_scores)

        expanded_scores = self._expand_scores_with_relationships(schema, table_scores)
        ranked_tables = self._rank_tables(
            schema,
            expanded_scores,
            column_scores,
            question_tokens,
            max_tables,
            max_columns_per_table,
        )
        join_paths = self._complete_join_paths(
            schema,
            ranked_tables,
            anchor_names={name for name, score in table_scores.items() if score > 0},
            column_scores=column_scores,
            question_tokens=question_tokens,
            max_columns_per_table=max_columns_per_table,
        )
        relationships = self._collect_relationships(schema, ranked_tables)
        warnings = self._build_warnings(question_tokens, ranked_tables)
        if plan is not None:
            warnings.extend(note for note in plan.ambiguity_notes if note not in warnings)
        intent_hints = self._build_intent_hints(question_tokens, ranked_tables)

        return RetrievedSchemaContext(
            question=question,
            tables=ranked_tables,
            relationships=relationships,
            warnings=warnings,
            intent_hints=intent_hints,
            join_paths=join_paths,
        )

    def build_prompt_context(self, context: RetrievedSchemaContext) -> str:
        sections: list[str] = []

        for table in context.tables:
            column_parts = [
                f"{column.name} ({column.data_type})"
                for column in table.selected_columns
            ]
            sections.append(
                f"Table: {table.full_name}\nColumns: {', '.join(column_parts)}"
            )

        if context.relationships:
            relationship_lines = [
                (
                    f"- {relationship.source_table}.{', '.join(relationship.source_columns)} "
                    f"-> {relationship.target_table}.{', '.join(relationship.target_columns)}"
                )
                for relationship in context.relationships
            ]
            sections.append("Relationships:\n" + "\n".join(relationship_lines))

        return "\n\n".join(sections)

    def _expand_scores_with_relationships(
        self,
        schema: DatabaseSchema,
        table_scores: dict[str, float],
    ) -> dict[str, float]:
        expanded_scores = dict(table_scores)
        table_map = {table.full_name: table for table in schema.tables}

        for full_name, base_score in table_scores.items():
            if base_score <= 0:
                continue

            table = table_map.get(full_name)
            if table is None:
                continue

            for related_table in table.related_tables:
                expanded_scores[related_table] = expanded_scores.get(related_table, 0.0) + (
                    base_score * 0.35
                )

        return expanded_scores

    def _rank_tables(
        self,
        schema: DatabaseSchema,
        table_scores: dict[str, float],
        column_scores: dict[str, dict[str, float]],
        question_tokens: set[str],
        max_tables: int,
        max_columns_per_table: int,
    ) -> list[RetrievedTable]:
        ranked = sorted(
            (
                table
                for table in schema.tables
                if table_scores.get(table.full_name, 0.0) > 0
            ),
            key=lambda table: (-table_scores[table.full_name], table.full_name),
        )
        top_tables = ranked[:max_tables]

        return [
            RetrievedTable(
                schema_name=table.schema_name,
                table_name=table.table_name,
                full_name=table.full_name,
                description=table.description,
                score=round(table_scores[table.full_name], 3),
                selected_columns=self._select_columns(
                    table,
                    column_scores.get(table.full_name, {}),
                    question_tokens,
                    max_columns_per_table,
                ),
                related_tables=table.related_tables,
            )
            for table in top_tables
        ]

    def _select_columns(
        self,
        table: TableMetadata,
        per_column_scores: dict[str, float],
        question_tokens: set[str],
        max_columns_per_table: int,
    ) -> list[RetrievedColumn]:
        scored_columns = sorted(
            table.columns,
            key=lambda column: (
                -per_column_scores.get(column.name, 0.0),
                column.ordinal_position,
            ),
        )

        selected: list[RetrievedColumn] = []
        selected_names: set[str] = set()
        for column in scored_columns:
            column_score = per_column_scores.get(column.name, 0.0)

            if column_score <= 0 and len(selected) >= min(3, len(scored_columns)):
                break

            selected.append(
                RetrievedColumn(
                    name=column.name,
                    data_type=column.data_type,
                    description=column.description,
                    score=round(column_score, 3),
                )
            )
            selected_names.add(column.name)

            if len(selected) >= max_columns_per_table:
                break

        for column_name in self._required_support_columns(table):
            if len(selected) >= max_columns_per_table or column_name in selected_names:
                continue

            column = next((candidate for candidate in table.columns if candidate.name == column_name), None)
            if column is None:
                continue

            selected.append(
                RetrievedColumn(
                    name=column.name,
                    data_type=column.data_type,
                    description=column.description,
                    score=round(per_column_scores.get(column.name, 0.0), 3),
                )
            )
            selected_names.add(column.name)

        for column_name in self._preferred_intent_columns(table, question_tokens):
            if len(selected) >= max_columns_per_table or column_name in selected_names:
                continue

            column = next((candidate for candidate in table.columns if candidate.name == column_name), None)
            if column is None:
                continue

            selected.append(
                RetrievedColumn(
                    name=column.name,
                    data_type=column.data_type,
                    description=column.description,
                    score=round(per_column_scores.get(column.name, 0.0), 3),
                )
            )
            selected_names.add(column.name)

        # A table's measures are what questions add up or compare; without them the model can only
        # conclude the data is missing. Fill the remaining room with numeric non-key columns.
        for column in table.columns:
            if len(selected) >= max_columns_per_table:
                break
            if column.name in selected_names or is_key_column(column.name) or not is_numeric_type(column.data_type):
                continue

            selected.append(
                RetrievedColumn(
                    name=column.name,
                    data_type=column.data_type,
                    description=column.description,
                    score=round(per_column_scores.get(column.name, 0.0), 3),
                )
            )
            selected_names.add(column.name)

        return selected

    def _collect_relationships(
        self,
        schema: DatabaseSchema,
        tables: list[RetrievedTable],
    ) -> list[RetrievedRelationship]:
        selected_table_names = {table.full_name for table in tables}
        relationships: list[RetrievedRelationship] = []
        seen_relationships: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()

        for table in schema.tables:
            if table.full_name not in selected_table_names:
                continue

            for foreign_key in table.foreign_keys:
                target_full_name = f"{foreign_key.target_schema}.{foreign_key.target_table}"
                relationship_key = (
                    table.full_name,
                    tuple(foreign_key.source_columns),
                    target_full_name,
                    tuple(foreign_key.target_columns),
                )

                if target_full_name not in selected_table_names:
                    continue
                if relationship_key in seen_relationships:
                    continue

                relationships.append(
                    RetrievedRelationship(
                        source_table=table.full_name,
                        source_columns=foreign_key.source_columns,
                        target_table=target_full_name,
                        target_columns=foreign_key.target_columns,
                    )
                )
                seen_relationships.add(relationship_key)

        return relationships

    def _build_warnings(
        self,
        question_tokens: set[str],
        tables: list[RetrievedTable],
    ) -> list[str]:
        warnings: list[str] = []

        if not question_tokens:
            warnings.append("The question contains too little specific business vocabulary.")
            return warnings

        if not tables:
            warnings.append("No strong schema matches were found for the question.")
            return warnings

        if len(tables) > 1 and abs(tables[0].score - tables[1].score) < 1.0:
            warnings.append("The schema match is somewhat ambiguous across multiple tables.")

        return warnings

    def _complete_join_paths(
        self,
        schema: DatabaseSchema,
        ranked_tables: list[RetrievedTable],
        anchor_names: set[str],
        column_scores: dict[str, dict[str, float]],
        question_tokens: set[str],
        max_columns_per_table: int,
    ) -> list[list[str]]:
        """Add the tables that connect the retrieved ones through foreign keys.

        A question about two tables that are linked only through others (for example sales by
        category when sales reference an order line that references a product) needs those
        in-between tables to be joined. For every question-matched table that the retrieved set
        does not connect to the top table, the shortest foreign-key path is added (up to
        MAX_BRIDGE_TABLES new tables) and returned so the prompt can show it.
        """
        table_map = {table.full_name: table for table in schema.tables}
        anchors = [table.full_name for table in ranked_tables if table.full_name in anchor_names]
        if len(anchors) < 2:
            return []

        join_paths: list[list[str]] = []
        added = 0
        start = anchors[0]
        for target in anchors[1:]:
            selected = {table.full_name for table in ranked_tables}
            if self._shortest_path(table_map, start, target, allowed=selected) is not None:
                continue
            path = self._shortest_path(table_map, start, target, allowed=None)
            if path is None:
                continue
            bridges = [name for name in path[1:-1] if name not in selected]
            if added + len(bridges) > MAX_BRIDGE_TABLES:
                continue
            for name in bridges:
                table = table_map[name]
                ranked_tables.append(
                    RetrievedTable(
                        schema_name=table.schema_name,
                        table_name=table.table_name,
                        full_name=table.full_name,
                        description=table.description,
                        score=0.0,
                        selected_columns=self._select_columns(
                            table,
                            column_scores.get(table.full_name, {}),
                            question_tokens,
                            max_columns_per_table,
                        ),
                        related_tables=table.related_tables,
                    )
                )
            added += len(bridges)
            join_paths.append(path)

        return join_paths

    def _shortest_path(
        self,
        table_map: dict[str, TableMetadata],
        start: str,
        target: str,
        allowed: set[str] | None,
    ) -> list[str] | None:
        previous: dict[str, str | None] = {start: None}
        frontier = [start]
        for _ in range(MAX_JOIN_PATH_EDGES):
            next_frontier: list[str] = []
            for name in frontier:
                table = table_map.get(name)
                if table is None:
                    continue
                for neighbour in sorted(table.related_tables):
                    if neighbour in previous or neighbour not in table_map:
                        continue
                    if allowed is not None and neighbour not in allowed:
                        continue
                    previous[neighbour] = name
                    if neighbour == target:
                        path = [target]
                        while previous[path[-1]] is not None:
                            path.append(previous[path[-1]])
                        return list(reversed(path))
                    next_frontier.append(neighbour)
            frontier = next_frontier
        return None

    def _apply_plan_boosts(
        self,
        schema: DatabaseSchema,
        plan: QueryPlan,
        table_scores: dict[str, float],
        column_scores: dict[str, dict[str, float]],
    ) -> None:
        if plan.candidate_table_families:
            self._boost_tables(
                schema,
                table_scores,
                plan.candidate_table_families,
                amount=6.0,
            )

        for table in schema.tables:
            if plan.candidate_table_families and not self._table_matches(table, plan.candidate_table_families):
                continue

            for metric_hint in plan.metric_targets:
                for column in table.columns:
                    if metric_hint in column.name.lower():
                        column_scores[table.full_name][column.name] += 4.5
                        table_scores[table.full_name] += 2.5

            for dimension_hint in plan.dimension_targets:
                for column in table.columns:
                    if dimension_hint in column.name.lower():
                        column_scores[table.full_name][column.name] += 3.0
                        table_scores[table.full_name] += 1.8

            if plan.time_targets:
                for column in table.columns:
                    if column.name in plan.time_targets or is_business_date_column(column.name, column.data_type):
                        column_scores[table.full_name][column.name] += 3.0
                        table_scores[table.full_name] += 1.6

    def _apply_broader_retrieval_boosts(
        self,
        schema: DatabaseSchema,
        plan: QueryPlan,
        table_scores: dict[str, float],
    ) -> None:
        if plan.candidate_table_families:
            self._boost_tables(
                schema,
                table_scores,
                plan.candidate_table_families,
                amount=2.5,
            )

        for table in schema.tables:
            if table_scores.get(table.full_name, 0.0) <= 0:
                continue
            for related_table in table.related_tables:
                table_scores[related_table] += 1.8

    def _apply_memory_boosts(
        self,
        schema: DatabaseSchema,
        plan: QueryPlan | None,
        memory_context: MemoryContext,
        question_tokens: set[str],
        table_scores: dict[str, float],
        column_scores: dict[str, dict[str, float]],
    ) -> None:
        if plan is not None and plan.task_type != "follow_up_refinement" and len(question_tokens) > 4:
            return

        if memory_context.suggested_table_families:
            self._boost_tables(
                schema,
                table_scores,
                memory_context.suggested_table_families,
                amount=4.8,
            )

        for table in schema.tables:
            for column in table.columns:
                if column.name in memory_context.suggested_metric_targets:
                    column_scores[table.full_name][column.name] += 3.8
                    table_scores[table.full_name] += 2.0
                if column.name in memory_context.suggested_dimension_targets:
                    column_scores[table.full_name][column.name] += 3.0
                    table_scores[table.full_name] += 1.6
                if column.name in memory_context.suggested_time_targets:
                    column_scores[table.full_name][column.name] += 2.8
                    table_scores[table.full_name] += 1.4

    def _boost_tables(
        self,
        schema: DatabaseSchema,
        table_scores: dict[str, float],
        table_families: list[str],
        amount: float,
    ) -> None:
        for table in schema.tables:
            if self._table_matches(table, table_families):
                table_scores[table.full_name] += amount

    def _table_matches(self, table: TableMetadata, table_families: list[str]) -> bool:
        """True when the table's name, or its last word (what the table is about), is among the words."""
        families = set(table_families)
        return (
            self._canonical_table_family(table.table_name) in families
            or head_word(table.table_name) in families
        )

    def _required_support_columns(self, table: TableMetadata) -> list[str]:
        required_columns: list[str] = []

        for column_name in table.primary_key:
            if column_name not in required_columns:
                required_columns.append(column_name)

        for foreign_key in table.foreign_keys:
            for column_name in foreign_key.source_columns:
                if column_name not in required_columns:
                    required_columns.append(column_name)

        for column in table.columns:
            if is_label_column(column.name, column.data_type) and column.name not in required_columns:
                required_columns.append(column.name)

        return required_columns

    def _preferred_intent_columns(
        self,
        table: TableMetadata,
        question_tokens: set[str],
    ) -> list[str]:
        money_words = CONCEPTS["money"].name_words
        wants_money = has_money_intent(question_tokens)
        wants_count = bool(question_tokens & COUNT_WORDS)
        wants_average = bool(question_tokens & AVERAGE_WORDS)
        wants_time = has_time_intent(question_tokens)
        wants_labels = any(not concept.is_measure for concept in concepts_in(question_tokens))

        preferred: list[str] = []
        for column in table.columns:
            words = name_words(column.name)
            if is_key_column(column.name):
                continue
            if (
                (wants_money and is_numeric_type(column.data_type) and words & money_words)
                or (wants_count and "count" in words)
                or (wants_average and words & AVERAGE_NAME_WORDS)
                or (wants_time and is_business_date_column(column.name, column.data_type))
                or (wants_labels and is_label_column(column.name, column.data_type))
            ):
                preferred.append(column.name)

        return preferred

    def _build_intent_hints(
        self,
        question_tokens: set[str],
        tables: list[RetrievedTable],
    ) -> RetrievalIntentHints:
        intent_tags: list[str] = []
        if has_money_intent(question_tokens):
            intent_tags.append("revenue")
        if question_tokens & COUNT_WORDS:
            intent_tags.append("count")
        if question_tokens & AVERAGE_WORDS:
            intent_tags.append("average")
        if has_time_intent(question_tokens):
            intent_tags.append("time")
        if question_tokens & COMPARISON_WORDS:
            intent_tags.append("comparison")
        if question_tokens & TOPK_WORDS:
            intent_tags.append("ranking")

        # The hints point at retrieved columns that fit the intent, never at fixed column names.
        money_words = CONCEPTS["money"].name_words
        metric_hints: list[str] = []
        time_hints: list[str] = []
        for table in tables:
            for column in table.selected_columns:
                if is_key_column(column.name):
                    continue
                qualified = f"{table.table_name}.{column.name}"
                words = name_words(column.name)
                if (
                    ("revenue" in intent_tags and is_numeric_type(column.data_type) and words & money_words)
                    or ("count" in intent_tags and "count" in words)
                    or ("average" in intent_tags and words & AVERAGE_NAME_WORDS)
                ):
                    metric_hints.append(qualified)
                if "time" in intent_tags and is_business_date_column(column.name, column.data_type):
                    time_hints.append(qualified)

        table_family_hints = list(
            dict.fromkeys(
                self._canonical_table_family(table.table_name)
                for table in tables
            )
        )

        return RetrievalIntentHints(
            intent_tags=intent_tags,
            metric_hints=list(dict.fromkeys(metric_hints)),
            time_hints=list(dict.fromkeys(time_hints)),
            table_family_hints=table_family_hints,
        )

    def _canonical_table_family(self, table_name: str) -> str:
        normalized_name = table_name.lower()
        if normalized_name.endswith("_list"):
            normalized_name = normalized_name[: -len("_list")]
        if normalized_name.endswith("ies") and len(normalized_name) > 3:
            return normalized_name[:-3] + "y"
        if normalized_name.endswith("s") and not normalized_name.endswith("ss"):
            return normalized_name[:-1]
        return normalized_name
