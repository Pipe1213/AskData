from collections import defaultdict

from app.db.metadata_models import DatabaseSchema, TableMetadata
from app.schemas.retrieval import (
    RetrievedColumn,
    RetrievedRelationship,
    RetrievedSchemaContext,
    RetrievedTable,
)
from app.utils.text import significant_tokens


class RetrievalService:
    def retrieve_schema_context(
        self,
        question: str,
        schema: DatabaseSchema,
        max_tables: int = 5,
        max_columns_per_table: int = 8,
    ) -> RetrievedSchemaContext:
        question_tokens = significant_tokens(question)
        table_scores: dict[str, float] = defaultdict(float)
        column_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for table in schema.tables:
            table_tokens = significant_tokens(table.table_name.replace("_", " "))
            description_tokens = significant_tokens(table.description or "")

            exact_table_match = table.table_name.lower() in question.lower()
            if exact_table_match:
                table_scores[table.full_name] += 5.0

            matched_table_tokens = question_tokens & table_tokens
            table_scores[table.full_name] += len(matched_table_tokens) * 3.0

            matched_description_tokens = question_tokens & description_tokens
            table_scores[table.full_name] += len(matched_description_tokens) * 1.0

            for column in table.columns:
                column_tokens = significant_tokens(column.name.replace("_", " "))
                matched_column_tokens = question_tokens & column_tokens

                if not matched_column_tokens:
                    continue

                column_scores[table.full_name][column.name] += len(matched_column_tokens) * 1.5
                table_scores[table.full_name] += len(matched_column_tokens) * 1.5

        expanded_scores = self._expand_scores_with_relationships(schema, table_scores)
        ranked_tables = self._rank_tables(schema, expanded_scores, column_scores, max_tables, max_columns_per_table)
        relationships = self._collect_relationships(schema, ranked_tables)
        warnings = self._build_warnings(question_tokens, ranked_tables)

        return RetrievedSchemaContext(
            question=question,
            tables=ranked_tables,
            relationships=relationships,
            warnings=warnings,
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
                score=round(table_scores[table.full_name], 3),
                selected_columns=self._select_columns(
                    table,
                    column_scores.get(table.full_name, {}),
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
        for column in scored_columns:
            column_score = per_column_scores.get(column.name, 0.0)

            if column_score <= 0 and len(selected) >= min(3, len(scored_columns)):
                break

            selected.append(
                RetrievedColumn(
                    name=column.name,
                    data_type=column.data_type,
                    score=round(column_score, 3),
                )
            )

            if len(selected) >= max_columns_per_table:
                break

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
