from collections import defaultdict

from app.core.config import Settings, get_settings
from app.db.introspection import (
    fetch_columns,
    fetch_foreign_keys,
    fetch_primary_keys,
    fetch_tables,
)
from app.db.metadata_models import (
    ColumnMetadata,
    DatabaseSchema,
    ForeignKeyMetadata,
    TableMetadata,
)


class SchemaService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def load_schema(self) -> DatabaseSchema:
        table_rows = fetch_tables(self.settings)
        column_rows = fetch_columns(self.settings)
        primary_key_rows = fetch_primary_keys(self.settings)
        foreign_key_rows = fetch_foreign_keys(self.settings)

        tables_by_key = self._build_table_map(table_rows)
        self._attach_columns(tables_by_key, column_rows)
        self._attach_primary_keys(tables_by_key, primary_key_rows)
        self._attach_foreign_keys(tables_by_key, foreign_key_rows)

        return DatabaseSchema(tables=list(tables_by_key.values()))

    def _build_table_map(self, table_rows: list[dict]) -> dict[tuple[str, str], TableMetadata]:
        tables: dict[tuple[str, str], TableMetadata] = {}

        for row in table_rows:
            key = (row["schema_name"], row["table_name"])
            tables[key] = TableMetadata(
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                full_name=f'{row["schema_name"]}.{row["table_name"]}',
                description=row["description"],
            )

        return tables

    def _attach_columns(
        self,
        tables_by_key: dict[tuple[str, str], TableMetadata],
        column_rows: list[dict],
    ) -> None:
        for row in column_rows:
            key = (row["schema_name"], row["table_name"])
            table = tables_by_key.get(key)

            if table is None:
                continue

            table.columns.append(
                ColumnMetadata(
                    name=row["column_name"],
                    data_type=row["data_type"],
                    is_nullable=bool(row["is_nullable"]),
                    has_default=bool(row["has_default"]),
                    ordinal_position=int(row["ordinal_position"]),
                    description=row["description"],
                )
            )

    def _attach_primary_keys(
        self,
        tables_by_key: dict[tuple[str, str], TableMetadata],
        primary_key_rows: list[dict],
    ) -> None:
        grouped_keys: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)

        for row in primary_key_rows:
            key = (row["schema_name"], row["table_name"])
            grouped_keys[key].append((int(row["ordinal_position"]), row["column_name"]))

        for key, columns in grouped_keys.items():
            table = tables_by_key.get(key)
            if table is None:
                continue

            table.primary_key = [column for _, column in sorted(columns)]

    def _attach_foreign_keys(
        self,
        tables_by_key: dict[tuple[str, str], TableMetadata],
        foreign_key_rows: list[dict],
    ) -> None:
        grouped_keys: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        adjacency_map: dict[tuple[str, str], set[str]] = defaultdict(set)

        for row in foreign_key_rows:
            key = (row["constraint_name"], row["source_schema"], row["source_table"])
            grouped_keys[key].append(row)

        for (_, source_schema, source_table), rows in grouped_keys.items():
            ordered_rows = sorted(rows, key=lambda row: int(row["ordinal_position"]))
            source_key = (source_schema, source_table)
            table = tables_by_key.get(source_key)

            if table is None:
                continue

            foreign_key = ForeignKeyMetadata(
                name=ordered_rows[0]["constraint_name"],
                source_schema=source_schema,
                source_table=source_table,
                source_columns=[row["source_column"] for row in ordered_rows],
                target_schema=ordered_rows[0]["target_schema"],
                target_table=ordered_rows[0]["target_table"],
                target_columns=[row["target_column"] for row in ordered_rows],
            )
            table.foreign_keys.append(foreign_key)
            adjacency_map[source_key].add(
                f"{foreign_key.target_schema}.{foreign_key.target_table}"
            )
            adjacency_map[
                (foreign_key.target_schema, foreign_key.target_table)
            ].add(f"{foreign_key.source_schema}.{foreign_key.source_table}")

        for table in tables_by_key.values():
            table.related_tables = sorted(
                adjacency_map.get((table.schema_name, table.table_name), set())
            )
