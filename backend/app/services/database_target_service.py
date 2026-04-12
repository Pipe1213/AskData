import subprocess
from dataclasses import dataclass
from pathlib import Path

from psycopg import Error as PsycopgError

from app.core.config import Settings, get_settings
from app.core.exceptions import QueryPipelineError
from app.db.connection import get_db_connection
from app.db.metadata_models import DatabaseSchema
from app.schemas.data_source import (
    DataSourceSummary,
    DataSourcesResponse,
    PostgresConnectionSettings,
    RuntimeConnectionTestResponse,
    RuntimePostgresConnectionInput,
    RuntimeTargetActivationResponse,
)
from app.services.schema_service import SchemaService


@dataclass
class ResolvedDatabaseTarget:
    target_id: str
    target_type: str
    display_name: str
    persistence_allowed: bool
    connection_settings: PostgresConnectionSettings | None = None
    schema_allowlist: list[str] | None = None
    dataset_name: str | None = None

    def to_summary(self, *, is_active: bool) -> DataSourceSummary:
        return DataSourceSummary(
            target_id=self.target_id,
            target_type=self.target_type,  # type: ignore[arg-type]
            display_name=self.display_name,
            persistence_allowed=self.persistence_allowed,
            is_active=is_active,
            database_name=(
                self.connection_settings.database if self.connection_settings is not None else None
            ),
            host=self.connection_settings.host if self.connection_settings is not None else None,
            schema_allowlist=list(self.schema_allowlist or []),
        )


class DatabaseTargetService:
    def __init__(
        self,
        schema_service: SchemaService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.schema_service = schema_service or SchemaService(settings=self.settings)
        self._runtime_targets_by_client: dict[str, ResolvedDatabaseTarget] = {}
        self._active_target_ids_by_client: dict[str, str] = {}
        self._last_demo_target_id_by_client: dict[str, str] = {}
        self._schema_cache_by_target: dict[str, DatabaseSchema] = {}
        self._repo_root = Path(__file__).resolve().parents[3]
        self._active_dataset_file = self._repo_root / "demo_data" / "active_dataset.txt"
        self._demo_targets: dict[str, ResolvedDatabaseTarget] = {
            "demo_pagila": ResolvedDatabaseTarget(
                target_id="demo_pagila",
                target_type="demo_pagila",
                display_name="Pagila",
                persistence_allowed=True,
                dataset_name="pagila",
                schema_allowlist=["public"],
            ),
            "demo_retail_ops": ResolvedDatabaseTarget(
                target_id="demo_retail_ops",
                target_type="demo_retail_ops",
                display_name="Retail Ops",
                persistence_allowed=True,
                dataset_name="retail_ops",
                schema_allowlist=["public"],
            ),
        }

    def list_targets(self, client_token: str | None) -> DataSourcesResponse:
        active_target = self.get_active_target(client_token)
        runtime_target = self._get_runtime_target_for_client(client_token)
        return DataSourcesResponse(
            active_target=active_target.to_summary(is_active=True),
            demo_targets=[
                target.to_summary(is_active=target.target_id == active_target.target_id)
                for target in self._demo_targets.values()
            ],
            runtime_target=(
                runtime_target.to_summary(is_active=runtime_target.target_id == active_target.target_id)
                if runtime_target is not None
                else None
            ),
        )

    def get_active_target(self, client_token: str | None) -> ResolvedDatabaseTarget:
        if client_token:
            active_target_id = self._active_target_ids_by_client.get(client_token)
            if active_target_id and active_target_id.startswith("runtime_postgres:"):
                runtime_target = self._runtime_targets_by_client.get(client_token)
                if runtime_target is None:
                    raise QueryPipelineError(
                        code="runtime_target_missing",
                        message="The runtime PostgreSQL connection is no longer available. Reconnect it to continue.",
                        stage="target",
                        retryable=False,
                    )
                return runtime_target
            if active_target_id in self._demo_targets:
                return self._demo_targets[active_target_id]

        return self._default_demo_target()

    def get_schema_for_active_target(
        self,
        client_token: str | None,
    ) -> tuple[ResolvedDatabaseTarget, DatabaseSchema]:
        target = self.get_active_target(client_token)
        if target.dataset_name is not None:
            self._ensure_demo_dataset_loaded(target)

        cached_schema = self._schema_cache_by_target.get(target.target_id)
        if cached_schema is None:
            cached_schema = self.schema_service.load_schema(
                connection_settings=target.connection_settings,
                schema_allowlist=target.schema_allowlist,
            )
            self._schema_cache_by_target[target.target_id] = cached_schema

        return target, cached_schema

    def activate_demo_target(
        self,
        client_token: str,
        target_id: str,
    ) -> tuple[ResolvedDatabaseTarget, DatabaseSchema]:
        target = self._demo_targets.get(target_id)
        if target is None:
            raise QueryPipelineError(
                code="unsupported_runtime_target",
                message="The requested demo target is not supported.",
                stage="target",
                retryable=False,
            )

        self._ensure_demo_dataset_loaded(target, force_reload=True)
        self._active_target_ids_by_client[client_token] = target.target_id
        self._last_demo_target_id_by_client[client_token] = target.target_id
        schema = self.schema_service.load_schema(schema_allowlist=target.schema_allowlist)
        self._schema_cache_by_target[target.target_id] = schema
        return target, schema

    def test_runtime_postgres_connection(
        self,
        client_token: str,
        payload: RuntimePostgresConnectionInput,
    ) -> RuntimeConnectionTestResponse:
        del client_token
        connection_settings = payload.to_connection_settings()
        try:
            return self._inspect_runtime_connection(
                connection_settings=connection_settings,
                schema_allowlist=payload.schema_allowlist,
            )
        except QueryPipelineError:
            raise
        except Exception as exc:
            raise QueryPipelineError(
                code="connection_test_failed",
                message="AskData could not connect to that PostgreSQL database.",
                stage="target",
                retryable=False,
                details={"error": str(exc)},
            ) from exc

    def activate_runtime_postgres_target(
        self,
        client_token: str,
        payload: RuntimePostgresConnectionInput,
    ) -> RuntimeTargetActivationResponse:
        inspection = self.test_runtime_postgres_connection(client_token, payload)
        connection_settings = payload.to_connection_settings()

        try:
            schema = self.schema_service.load_schema(
                connection_settings=connection_settings,
                schema_allowlist=payload.schema_allowlist,
            )
        except Exception as exc:
            raise QueryPipelineError(
                code="schema_introspection_failed",
                message="AskData connected successfully but could not load the database schema.",
                stage="schema",
                retryable=False,
                details={"error": str(exc)},
            ) from exc

        runtime_target = ResolvedDatabaseTarget(
            target_id=f"runtime_postgres:{client_token}",
            target_type="runtime_postgres",
            display_name=f"{payload.database} @ {payload.host}",
            persistence_allowed=False,
            connection_settings=connection_settings,
            schema_allowlist=list(payload.schema_allowlist),
        )
        self._runtime_targets_by_client[client_token] = runtime_target
        self._active_target_ids_by_client[client_token] = runtime_target.target_id
        self._schema_cache_by_target[runtime_target.target_id] = schema

        return RuntimeTargetActivationResponse(
            active_target=runtime_target.to_summary(is_active=True),
            database_version=inspection.database_version,
            visible_schemas=inspection.visible_schemas,
            table_count=len(schema.tables),
            warnings=inspection.warnings,
        )

    def clear_runtime_target(self, client_token: str) -> ResolvedDatabaseTarget:
        runtime_target = self._runtime_targets_by_client.pop(client_token, None)
        if runtime_target is not None:
            self._schema_cache_by_target.pop(runtime_target.target_id, None)
        fallback_target_id = self._last_demo_target_id_by_client.get(
            client_token,
            self._default_demo_target().target_id,
        )
        fallback_target = self._demo_targets[fallback_target_id]
        self._active_target_ids_by_client[client_token] = fallback_target_id
        self._ensure_demo_dataset_loaded(fallback_target)
        return fallback_target

    def refresh_schema_cache(self, client_token: str | None) -> tuple[ResolvedDatabaseTarget, DatabaseSchema]:
        target = self.get_active_target(client_token)
        if target.dataset_name is not None:
            self._ensure_demo_dataset_loaded(target)
        schema = self.schema_service.load_schema(
            connection_settings=target.connection_settings,
            schema_allowlist=target.schema_allowlist,
        )
        self._schema_cache_by_target[target.target_id] = schema
        return target, schema

    def _inspect_runtime_connection(
        self,
        connection_settings: PostgresConnectionSettings,
        schema_allowlist: list[str],
    ) -> RuntimeConnectionTestResponse:
        warnings: list[str] = []
        try:
            with get_db_connection(
                self.settings,
                connection_settings=connection_settings,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SHOW server_version")
                    version_row = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT schema_name
                        FROM information_schema.schemata
                        WHERE schema_name = ANY(%s)
                        ORDER BY schema_name
                        """,
                        (schema_allowlist,),
                    )
                    visible_schemas = [row["schema_name"] for row in cursor.fetchall()]
                    cursor.execute(
                        """
                        SELECT COUNT(*) AS table_count
                        FROM information_schema.tables
                        WHERE table_type = 'BASE TABLE'
                          AND table_schema = ANY(%s)
                        """,
                        (schema_allowlist,),
                    )
                    table_row = cursor.fetchone()
        except PsycopgError as exc:
            raise QueryPipelineError(
                code="connection_test_failed",
                message="AskData could not connect to that PostgreSQL database.",
                stage="target",
                retryable=False,
                details={
                    "error": str(exc),
                    "sqlstate": getattr(exc, "sqlstate", None),
                },
            ) from exc

        table_count = int(table_row["table_count"] if table_row is not None else 0)
        if not visible_schemas:
            warnings.append("None of the requested schemas are visible to the provided user.")
        if table_count == 0:
            warnings.append("The selected schemas do not contain base tables AskData can analyze yet.")

        return RuntimeConnectionTestResponse(
            database_version=str(version_row["server_version"] if version_row is not None else "unknown"),
            visible_schemas=visible_schemas,
            table_count=table_count,
            warnings=warnings,
        )

    def _ensure_demo_dataset_loaded(
        self,
        target: ResolvedDatabaseTarget,
        *,
        force_reload: bool = False,
    ) -> None:
        if target.dataset_name is None:
            return

        active_dataset = self._read_active_dataset_name()
        if not force_reload and active_dataset == target.dataset_name:
            return

        script_path = self._repo_root / "backend" / "scripts" / "load_dataset.sh"
        completed = subprocess.run(
            [str(script_path), target.dataset_name],
            check=False,
            capture_output=True,
            text=True,
            cwd=self._repo_root,
        )
        if completed.returncode != 0:
            raise QueryPipelineError(
                code="schema_introspection_failed",
                message=f"AskData could not activate the {target.display_name} demo dataset.",
                stage="target",
                retryable=False,
                details={
                    "stdout": completed.stdout.strip(),
                    "error": completed.stderr.strip(),
                },
            )

        for demo_target_id in list(self._schema_cache_by_target):
            if demo_target_id.startswith("demo_"):
                self._schema_cache_by_target.pop(demo_target_id, None)

    def _default_demo_target(self) -> ResolvedDatabaseTarget:
        active_dataset = self._read_active_dataset_name()
        if active_dataset == "retail_ops":
            return self._demo_targets["demo_retail_ops"]
        return self._demo_targets["demo_pagila"]

    def _read_active_dataset_name(self) -> str:
        if not self._active_dataset_file.exists():
            return "pagila"
        dataset_name = self._active_dataset_file.read_text(encoding="utf-8").strip()
        return dataset_name or "pagila"

    def _get_runtime_target_for_client(self, client_token: str | None) -> ResolvedDatabaseTarget | None:
        if not client_token:
            return None
        return self._runtime_targets_by_client.get(client_token)
