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
from app.services.dataset_adapters import DatasetAdapter
from app.utils.text import significant_tokens

REVENUE_TOKENS = {"revenue", "sale", "sales", "spend", "spent", "earning", "earnings"}
CATEGORY_TOKENS = {"category", "genre"}
CUSTOMER_TOKENS = {"customer", "customers"}
STAFF_TOKENS = {"staff", "employee", "employees"}
RENTAL_TOKENS = {"rental", "rentals", "rented", "rent"}
PRODUCT_TOKENS = {"product", "products", "item", "items", "sku"}
BRAND_TOKENS = {"brand", "brands"}
REGION_TOKENS = {"region", "regions", "market", "markets", "country", "countries"}
ORDER_TOKENS = {"order", "orders", "ordered", "purchase", "purchases"}
RETURN_TOKENS = {"return", "returns", "refund", "refunds"}
SHIPMENT_TOKENS = {"shipment", "shipments", "delivery", "deliveries", "carrier"}
TIME_TOKENS = {"date", "dates", "trend", "monthly", "month", "daily", "yearly", "time", "year", "day"}
COUNT_TOKENS = {"count", "counts", "number", "many"}
AVERAGE_TOKENS = {"average", "avg", "mean"}
COMPARISON_TOKENS = {"compare", "comparison", "versus", "vs"}
TOPK_TOKENS = {"top", "highest", "most", "best"}

SEMANTIC_TABLE_HINTS: dict[str, set[str]] = {
    "payment": REVENUE_TOKENS | {"amount", "total", "totals", "sales"},
    "customer": CUSTOMER_TOKENS | {"buyer", "buyers"},
    "staff": STAFF_TOKENS,
    "rental": RENTAL_TOKENS | TIME_TOKENS,
    "inventory": {"inventory", "stock"} | CATEGORY_TOKENS,
    "category": CATEGORY_TOKENS,
    "order": ORDER_TOKENS | REVENUE_TOKENS | TIME_TOKENS,
    "product": PRODUCT_TOKENS | CATEGORY_TOKENS | BRAND_TOKENS,
    "brand": BRAND_TOKENS,
    "region": REGION_TOKENS,
    "shipment": SHIPMENT_TOKENS | TIME_TOKENS,
    "return": RETURN_TOKENS,
    "sales_rep": STAFF_TOKENS | {"rep", "representative", "seller"},
}

SEMANTIC_COLUMN_HINTS: dict[str, set[str]] = {
    "amount": REVENUE_TOKENS | {"amount", "total", "totals"},
    "payment_date": TIME_TOKENS | REVENUE_TOKENS,
    "rental_date": TIME_TOKENS | RENTAL_TOKENS,
    "customer_id": CUSTOMER_TOKENS,
    "staff_id": STAFF_TOKENS,
    "name": CATEGORY_TOKENS | {"customer", "staff"},
    "full_name": CUSTOMER_TOKENS | STAFF_TOKENS,
    "category_name": CATEGORY_TOKENS,
    "brand_name": BRAND_TOKENS,
    "region_name": REGION_TOKENS,
    "ordered_at": TIME_TOKENS | ORDER_TOKENS,
    "paid_at": TIME_TOKENS | REVENUE_TOKENS,
    "requested_at": TIME_TOKENS | RETURN_TOKENS,
    "shipped_at": TIME_TOKENS | SHIPMENT_TOKENS,
    "refund_amount": RETURN_TOKENS,
    "shipping_cost": SHIPMENT_TOKENS,
    "order_status": ORDER_TOKENS,
    "order_channel": ORDER_TOKENS,
}


class RetrievalService:
    def retrieve_schema_context(
        self,
        question: str,
        schema: DatabaseSchema,
        plan: QueryPlan | None = None,
        memory_context: MemoryContext | None = None,
        dataset_adapter: DatasetAdapter | None = None,
        max_tables: int = 5,
        max_columns_per_table: int = 8,
        broaden: bool = False,
    ) -> RetrievedSchemaContext:
        question_tokens = significant_tokens(question)
        table_scores: dict[str, float] = defaultdict(float)
        column_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for table in schema.tables:
            table_family = self._canonical_table_family(table.table_name)
            table_tokens = significant_tokens(
                f"{table.table_name.replace('_', ' ')} {table_family.replace('_', ' ')}"
            )
            description_tokens = significant_tokens(table.description or "")

            exact_table_match = table.table_name.lower() in question.lower()
            if exact_table_match:
                table_scores[table.full_name] += 5.0

            matched_table_tokens = question_tokens & table_tokens
            table_scores[table.full_name] += len(matched_table_tokens) * 3.0

            matched_description_tokens = question_tokens & description_tokens
            table_scores[table.full_name] += len(matched_description_tokens) * 1.0
            table_scores[table.full_name] += self._semantic_table_boost(table, question_tokens)

            for column in table.columns:
                column_tokens = significant_tokens(column.name.replace("_", " "))
                matched_column_tokens = question_tokens & column_tokens

                if not matched_column_tokens:
                    semantic_column_boost = self._semantic_column_boost(column.name, question_tokens)
                    if semantic_column_boost <= 0:
                        continue

                    column_scores[table.full_name][column.name] += semantic_column_boost
                    table_scores[table.full_name] += semantic_column_boost * 0.8
                    continue

                direct_column_boost = len(matched_column_tokens) * 1.5
                semantic_column_boost = self._semantic_column_boost(column.name, question_tokens)
                total_column_boost = direct_column_boost + semantic_column_boost

                column_scores[table.full_name][column.name] += total_column_boost
                table_scores[table.full_name] += total_column_boost

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

        if dataset_adapter is not None:
            self._apply_adapter_boosts(
                schema=schema,
                question_tokens=question_tokens,
                dataset_adapter=dataset_adapter,
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

    def _semantic_table_boost(
        self,
        table: TableMetadata,
        question_tokens: set[str],
    ) -> float:
        hint_tokens = SEMANTIC_TABLE_HINTS.get(
            self._canonical_table_family(table.table_name),
            set(),
        )
        return len(question_tokens & hint_tokens) * 2.2

    def _semantic_column_boost(
        self,
        column_name: str,
        question_tokens: set[str],
    ) -> float:
        hint_tokens = SEMANTIC_COLUMN_HINTS.get(column_name, set())
        return len(question_tokens & hint_tokens) * 1.8

    def _apply_adapter_boosts(
        self,
        schema: DatabaseSchema,
        question_tokens: set[str],
        dataset_adapter: DatasetAdapter,
        table_scores: dict[str, float],
        column_scores: dict[str, dict[str, float]],
    ) -> None:
        boosts = dataset_adapter.retrieval_boosts(question_tokens)

        for table_families, amount in boosts.table_boosts:
            self._boost_tables(schema, table_scores, table_families, amount=amount)

        for column_boost in boosts.column_boosts:
            self._boost_columns(
                schema,
                column_scores,
                column_boost.table_family,
                column_boost.column_names,
                amount=column_boost.amount,
            )

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
            if plan.candidate_table_families and self._canonical_table_family(table.table_name) not in plan.candidate_table_families:
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

            for time_hint in plan.time_targets:
                for column in table.columns:
                    if time_hint in column.name.lower():
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
            if self._canonical_table_family(table.table_name) in table_families:
                table_scores[table.full_name] += amount

    def _boost_columns(
        self,
        schema: DatabaseSchema,
        column_scores: dict[str, dict[str, float]],
        table_family: str,
        column_names: list[str],
        amount: float,
    ) -> None:
        for table in schema.tables:
            if self._canonical_table_family(table.table_name) != table_family:
                continue
            for column_name in column_names:
                if any(column.name == column_name for column in table.columns):
                    column_scores[table.full_name][column_name] += amount

    def _required_support_columns(self, table: TableMetadata) -> list[str]:
        required_columns: list[str] = []

        for column_name in table.primary_key:
            if column_name not in required_columns:
                required_columns.append(column_name)

        for foreign_key in table.foreign_keys:
            for column_name in foreign_key.source_columns:
                if column_name not in required_columns:
                    required_columns.append(column_name)

        for preferred_column in ("amount", "payment_date", "rental_date", "name"):
            if any(column.name == preferred_column for column in table.columns) and preferred_column not in required_columns:
                required_columns.append(preferred_column)

        return required_columns

    def _preferred_intent_columns(
        self,
        table: TableMetadata,
        question_tokens: set[str],
    ) -> list[str]:
        preferred: list[str] = []
        available_names = {column.name for column in table.columns}

        if question_tokens & REVENUE_TOKENS:
            for column_name in ("amount", "total_revenue", "total_spent", "revenue"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & COUNT_TOKENS:
            for column_name in ("rental_count", "payment_count", "count"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & AVERAGE_TOKENS:
            for column_name in ("avg_amount", "average_amount", "avg_rental_duration"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & TIME_TOKENS:
            for column_name in ("payment_date", "paid_at", "ordered_at", "rental_date", "shipped_at", "requested_at", "last_update"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & CUSTOMER_TOKENS:
            for column_name in ("customer_id", "first_name", "last_name"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & STAFF_TOKENS:
            for column_name in ("staff_id", "sales_rep_id", "full_name", "first_name", "last_name"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & CATEGORY_TOKENS:
            for column_name in ("category_name", "name", "category_id"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & PRODUCT_TOKENS:
            for column_name in ("product_name", "product_id", "sku"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & BRAND_TOKENS:
            for column_name in ("brand_name", "brand_id"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & REGION_TOKENS:
            for column_name in ("region_name", "region_id"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & RETURN_TOKENS:
            for column_name in ("refund_amount", "return_status", "return_reason"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & SHIPMENT_TOKENS:
            for column_name in ("shipment_status", "carrier", "shipping_cost"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        if question_tokens & ORDER_TOKENS:
            for column_name in ("order_id", "order_status", "order_channel"):
                if column_name in available_names and column_name not in preferred:
                    preferred.append(column_name)

        return preferred

    def _build_intent_hints(
        self,
        question_tokens: set[str],
        tables: list[RetrievedTable],
    ) -> RetrievalIntentHints:
        intent_tags: list[str] = []
        if question_tokens & REVENUE_TOKENS:
            intent_tags.append("revenue")
        if question_tokens & COUNT_TOKENS:
            intent_tags.append("count")
        if question_tokens & AVERAGE_TOKENS:
            intent_tags.append("average")
        if question_tokens & TIME_TOKENS:
            intent_tags.append("time")
        if question_tokens & COMPARISON_TOKENS:
            intent_tags.append("comparison")
        if question_tokens & TOPK_TOKENS:
            intent_tags.append("ranking")

        metric_hints: list[str] = []
        if "revenue" in intent_tags:
            metric_hints.extend(["amount", "total_spent", "total_revenue", "revenue"])
        if "count" in intent_tags:
            metric_hints.extend(["count", "rental_count", "payment_count"])
        if "average" in intent_tags:
            metric_hints.extend(["avg_amount", "average_amount"])

        dimension_hints: list[str] = []
        if question_tokens & CUSTOMER_TOKENS:
            dimension_hints.extend(["customer_id", "first_name", "last_name"])
        if question_tokens & STAFF_TOKENS:
            dimension_hints.extend(["staff_id", "first_name", "last_name"])
        if question_tokens & CATEGORY_TOKENS:
            dimension_hints.extend(["name", "category_id"])

        time_hints = []
        if question_tokens & TIME_TOKENS:
            time_hints.extend(["payment_date", "paid_at", "ordered_at", "rental_date", "shipped_at", "requested_at"])

        table_family_hints = list(
            dict.fromkeys(
                self._canonical_table_family(table.table_name)
                for table in tables
            )
        )

        return RetrievalIntentHints(
            intent_tags=intent_tags,
            metric_hints=metric_hints,
            dimension_hints=dimension_hints,
            time_hints=time_hints,
            table_family_hints=table_family_hints,
        )

    def _canonical_table_family(self, table_name: str) -> str:
        normalized_name = table_name.lower()
        if normalized_name.startswith("payment_p"):
            return "payment"
        if normalized_name.endswith("_list"):
            normalized_name = normalized_name[: -len("_list")]
        if normalized_name.endswith("ies") and len(normalized_name) > 3:
            return normalized_name[:-3] + "y"
        if normalized_name.endswith("s") and not normalized_name.endswith("ss"):
            return normalized_name[:-1]
        return normalized_name
