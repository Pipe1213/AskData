from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.db.connection import get_db_connection
from app.schemas.data_source import PostgresConnectionSettings

TABLES_QUERY = """
SELECT
    ns.nspname AS schema_name,
    cls.relname AS table_name,
    obj_description(cls.oid) AS description
FROM pg_class AS cls
JOIN pg_namespace AS ns
    ON ns.oid = cls.relnamespace
WHERE cls.relkind IN ('r', 'p')
  AND NOT cls.relispartition
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema', 'askdata_app')
  AND (%(schema_allowlist)s::text[] IS NULL OR ns.nspname = ANY(%(schema_allowlist)s))
ORDER BY ns.nspname, cls.relname
"""

COLUMNS_QUERY = """
SELECT
    cols.table_schema AS schema_name,
    cols.table_name,
    cols.column_name,
    cols.data_type,
    cols.is_nullable = 'YES' AS is_nullable,
    cols.column_default IS NOT NULL AS has_default,
    cols.ordinal_position,
    pgd.description
FROM information_schema.columns AS cols
JOIN pg_catalog.pg_namespace AS ns
    ON ns.nspname = cols.table_schema
JOIN pg_catalog.pg_class AS cls
    ON cls.relnamespace = ns.oid
   AND cls.relname = cols.table_name
LEFT JOIN pg_catalog.pg_description AS pgd
    ON pgd.objoid = cls.oid
   AND pgd.objsubid = cols.ordinal_position
WHERE NOT cls.relispartition
  AND cols.table_schema NOT IN ('pg_catalog', 'information_schema', 'askdata_app')
  AND (%(schema_allowlist)s::text[] IS NULL OR cols.table_schema = ANY(%(schema_allowlist)s))
ORDER BY cols.table_schema, cols.table_name, cols.ordinal_position
"""

PRIMARY_KEYS_QUERY = """
SELECT
    tc.table_schema AS schema_name,
    tc.table_name,
    kcu.column_name,
    kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
   AND tc.table_name = kcu.table_name
JOIN pg_catalog.pg_namespace AS ns
    ON ns.nspname = tc.table_schema
JOIN pg_catalog.pg_class AS cls
    ON cls.relnamespace = ns.oid
   AND cls.relname = tc.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND NOT cls.relispartition
  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema', 'askdata_app')
  AND (%(schema_allowlist)s::text[] IS NULL OR tc.table_schema = ANY(%(schema_allowlist)s))
ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
"""

# Foreign keys declared on partitions are reported on the partitioned root table,
# once per distinct key: some schemas (e.g. Pagila) declare them only on the partitions.
# Constraints cloned from a parent's foreign key (conparentid <> 0) are skipped.
FOREIGN_KEYS_QUERY = """
WITH constraint_columns AS (
    SELECT
        con.conname,
        con.conrelid,
        COALESCE(pg_partition_root(con.conrelid), con.conrelid) AS source_relid,
        COALESCE(pg_partition_root(con.confrelid), con.confrelid) AS target_relid,
        ARRAY(
            SELECT att.attname::text
            FROM unnest(con.conkey) WITH ORDINALITY AS key_cols(attnum, position)
            JOIN pg_catalog.pg_attribute AS att
                ON att.attrelid = con.conrelid
               AND att.attnum = key_cols.attnum
            ORDER BY key_cols.position
        ) AS source_columns,
        ARRAY(
            SELECT att.attname::text
            FROM unnest(con.confkey) WITH ORDINALITY AS key_cols(attnum, position)
            JOIN pg_catalog.pg_attribute AS att
                ON att.attrelid = con.confrelid
               AND att.attnum = key_cols.attnum
            ORDER BY key_cols.position
        ) AS target_columns
    FROM pg_catalog.pg_constraint AS con
    WHERE con.contype = 'f'
      AND con.conparentid = 0
),
distinct_keys AS (
    SELECT DISTINCT ON (cc.source_relid, cc.source_columns, cc.target_relid, cc.target_columns)
        CASE
            WHEN cc.conrelid = cc.source_relid THEN cc.conname::text
            ELSE source_cls.relname || '_' || array_to_string(cc.source_columns, '_') || '_fkey'
        END AS constraint_name,
        source_ns.nspname AS source_schema,
        source_cls.relname AS source_table,
        target_ns.nspname AS target_schema,
        target_cls.relname AS target_table,
        cc.source_columns,
        cc.target_columns
    FROM constraint_columns AS cc
    JOIN pg_catalog.pg_class AS source_cls
        ON source_cls.oid = cc.source_relid
    JOIN pg_catalog.pg_namespace AS source_ns
        ON source_ns.oid = source_cls.relnamespace
    JOIN pg_catalog.pg_class AS target_cls
        ON target_cls.oid = cc.target_relid
    JOIN pg_catalog.pg_namespace AS target_ns
        ON target_ns.oid = target_cls.relnamespace
    WHERE source_ns.nspname NOT IN ('pg_catalog', 'information_schema', 'askdata_app')
      AND (%(schema_allowlist)s::text[] IS NULL OR source_ns.nspname = ANY(%(schema_allowlist)s))
    ORDER BY
        cc.source_relid,
        cc.source_columns,
        cc.target_relid,
        cc.target_columns,
        cc.conrelid = cc.source_relid DESC,
        cc.conname
)
SELECT
    dk.constraint_name,
    dk.source_schema,
    dk.source_table,
    key_cols.source_column,
    dk.target_schema,
    dk.target_table,
    key_cols.target_column,
    key_cols.ordinal_position
FROM distinct_keys AS dk
CROSS JOIN LATERAL unnest(dk.source_columns, dk.target_columns)
    WITH ORDINALITY AS key_cols(source_column, target_column, ordinal_position)
ORDER BY dk.constraint_name, key_cols.ordinal_position
"""


def _run_query(
    query: str,
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
    schema_allowlist: list[str] | None = None,
) -> list[dict]:
    params = {
        "schema_allowlist": schema_allowlist or None,
    }

    with get_db_connection(settings, connection_settings=connection_settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def fetch_tables(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
    schema_allowlist: list[str] | None = None,
) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(
        TABLES_QUERY,
        active_settings,
        connection_settings=connection_settings,
        schema_allowlist=schema_allowlist,
    )


def fetch_columns(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
    schema_allowlist: list[str] | None = None,
) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(
        COLUMNS_QUERY,
        active_settings,
        connection_settings=connection_settings,
        schema_allowlist=schema_allowlist,
    )


def fetch_primary_keys(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
    schema_allowlist: list[str] | None = None,
) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(
        PRIMARY_KEYS_QUERY,
        active_settings,
        connection_settings=connection_settings,
        schema_allowlist=schema_allowlist,
    )


def fetch_foreign_keys(
    settings: Settings | None = None,
    connection_settings: PostgresConnectionSettings | None = None,
    schema_allowlist: list[str] | None = None,
) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(
        FOREIGN_KEYS_QUERY,
        active_settings,
        connection_settings=connection_settings,
        schema_allowlist=schema_allowlist,
    )
