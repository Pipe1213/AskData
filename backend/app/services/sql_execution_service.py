from psycopg import Error as PsycopgError

from app.core.config import Settings, get_settings
from app.db.connection import get_db_connection
from app.schemas.execution import SQLExecutionError, SQLExecutionResult


class SQLExecutionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def execute_sql(self, validated_sql: str) -> SQLExecutionResult:
        sql = validated_sql.strip()
        if not sql:
            return SQLExecutionResult(
                sql=validated_sql,
                success=False,
                error=SQLExecutionError(
                    code="empty_sql",
                    message="Validated SQL is empty and cannot be executed.",
                ),
            )

        timeout_ms = int(self.settings.query_timeout_seconds * 1000)
        fetch_limit = self.settings.max_result_rows + 1

        try:
            with get_db_connection(self.settings) as connection:
                connection.read_only = True

                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('statement_timeout', %s, true)",
                            (f"{timeout_ms}ms",),
                        )
                        cursor.execute(sql)

                        columns = [
                            description.name for description in (cursor.description or [])
                        ]
                        raw_rows = cursor.fetchmany(fetch_limit)

            warnings: list[str] = []
            if len(raw_rows) > self.settings.max_result_rows:
                raw_rows = raw_rows[: self.settings.max_result_rows]
                warnings.append(
                    f"Result set exceeded {self.settings.max_result_rows} rows and was truncated."
                )

            rows = [
                [row.get(column_name) for column_name in columns]
                for row in raw_rows
            ]

            return SQLExecutionResult(
                sql=sql,
                success=True,
                columns=columns,
                rows=rows,
                row_count=len(rows),
                warnings=warnings,
            )
        except PsycopgError as exc:
            return SQLExecutionResult(
                sql=sql,
                success=False,
                error=SQLExecutionError(
                    code="sql_execution_failed",
                    message=str(exc).strip() or "SQL execution failed.",
                    details={
                        "sqlstate": getattr(exc, "sqlstate", None),
                        "error_type": exc.__class__.__name__,
                    },
                ),
            )
