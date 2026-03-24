from psycopg.rows import dict_row

from app.core.config import Settings, get_settings
from app.db.connection import get_db_connection

TABLES_QUERY = """
SELECT
    ns.nspname AS schema_name,
    cls.relname AS table_name,
    obj_description(cls.oid) AS description
FROM pg_class AS cls
JOIN pg_namespace AS ns
    ON ns.oid = cls.relnamespace
WHERE cls.relkind = 'r'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
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
LEFT JOIN pg_catalog.pg_statio_all_tables AS st
    ON st.schemaname = cols.table_schema
   AND st.relname = cols.table_name
LEFT JOIN pg_catalog.pg_description AS pgd
    ON pgd.objoid = st.relid
   AND pgd.objsubid = cols.ordinal_position
WHERE cols.table_schema NOT IN ('pg_catalog', 'information_schema')
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
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
"""

FOREIGN_KEYS_QUERY = """
SELECT
    tc.constraint_name,
    tc.table_schema AS source_schema,
    tc.table_name AS source_table,
    kcu.column_name AS source_column,
    ccu.table_schema AS target_schema,
    ccu.table_name AS target_table,
    ccu.column_name AS target_column,
    kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
   AND tc.table_name = kcu.table_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY tc.constraint_name, kcu.ordinal_position
"""


def _run_query(query: str, settings: Settings | None = None) -> list[dict]:
    with get_db_connection(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [dict(row) for row in rows]


def fetch_tables(settings: Settings | None = None) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(TABLES_QUERY, active_settings)


def fetch_columns(settings: Settings | None = None) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(COLUMNS_QUERY, active_settings)


def fetch_primary_keys(settings: Settings | None = None) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(PRIMARY_KEYS_QUERY, active_settings)


def fetch_foreign_keys(settings: Settings | None = None) -> list[dict]:
    active_settings = settings or get_settings()
    return _run_query(FOREIGN_KEYS_QUERY, active_settings)
