"""Checks that a database user can only read, before AskData runs generated SQL with it."""

SERVER_FILE_ROLES = ("pg_read_server_files", "pg_write_server_files", "pg_execute_server_program")

ROLE_QUERY = """
SELECT current_user AS role_name, rolsuper AS is_superuser
FROM pg_catalog.pg_roles
WHERE rolname = current_user
"""

SERVER_FILE_ROLES_QUERY = """
SELECT roles.rolname AS role_name
FROM pg_catalog.pg_roles AS roles
WHERE roles.rolname = ANY(%(role_names)s)
  AND pg_has_role(current_user, roles.oid, 'MEMBER')
ORDER BY roles.rolname
"""

SCHEMA_CREATE_QUERY = """
SELECT ns.nspname AS schema_name
FROM pg_catalog.pg_namespace AS ns
WHERE ns.nspname = ANY(%(schema_allowlist)s)
  AND has_schema_privilege(ns.oid, 'CREATE')
ORDER BY ns.nspname
"""

WRITABLE_TABLES_QUERY = """
SELECT
    ns.nspname AS schema_name,
    cls.relname AS table_name,
    ARRAY_REMOVE(
        ARRAY[
            CASE WHEN has_table_privilege(cls.oid, 'INSERT') THEN 'INSERT' END,
            CASE WHEN has_table_privilege(cls.oid, 'UPDATE') THEN 'UPDATE' END,
            CASE WHEN has_table_privilege(cls.oid, 'DELETE') THEN 'DELETE' END,
            CASE WHEN has_table_privilege(cls.oid, 'TRUNCATE') THEN 'TRUNCATE' END,
            CASE WHEN has_any_column_privilege(cls.oid, 'INSERT, UPDATE')
                  AND NOT has_table_privilege(cls.oid, 'INSERT, UPDATE')
                 THEN 'column INSERT/UPDATE' END
        ],
        NULL
    ) AS privileges,
    COUNT(*) OVER () AS total_count
FROM pg_catalog.pg_class AS cls
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = cls.relnamespace
WHERE ns.nspname = ANY(%(schema_allowlist)s)
  AND cls.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND (
      has_table_privilege(cls.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')
      OR has_any_column_privilege(cls.oid, 'INSERT, UPDATE')
  )
ORDER BY ns.nspname, cls.relname
LIMIT 3
"""


def find_unsafe_role_privileges(cursor, schema_allowlist: list[str]) -> list[str]:
    """Plain-language reasons the current user is not read-only; empty when it is.

    `cursor` must return dict rows (the app's connections use dict_row).
    """
    problems: list[str] = []

    cursor.execute(ROLE_QUERY)
    role = cursor.fetchone()
    if role is not None and role["is_superuser"]:
        problems.append("is a superuser")

    cursor.execute(SERVER_FILE_ROLES_QUERY, {"role_names": list(SERVER_FILE_ROLES)})
    file_roles = [row["role_name"] for row in cursor.fetchall()]
    if file_roles:
        problems.append("is a member of " + ", ".join(file_roles) + " (server file access)")

    cursor.execute(SCHEMA_CREATE_QUERY, {"schema_allowlist": schema_allowlist})
    creatable = [row["schema_name"] for row in cursor.fetchall()]
    if creatable:
        problems.append("can create objects in schema " + ", ".join(creatable))

    cursor.execute(WRITABLE_TABLES_QUERY, {"schema_allowlist": schema_allowlist})
    writable = cursor.fetchall()
    if writable:
        examples = ", ".join(
            f"{row['schema_name']}.{row['table_name']} ({', '.join(row['privileges'])})" for row in writable
        )
        total = int(writable[0]["total_count"])
        problems.append(f"can change data in {total} table(s), e.g. {examples}")

    return problems
