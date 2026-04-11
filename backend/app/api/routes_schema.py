from fastapi import APIRouter, HTTPException, Request, status

from app.db.metadata_models import DatabaseSchema
from app.schemas.schema import (
    SchemaColumnResponse,
    SchemaForeignKeyResponse,
    SchemaOverviewResponse,
    SchemaTableResponse,
)

router = APIRouter(tags=["schema"])


@router.get("/schema/overview", response_model=SchemaOverviewResponse)
def get_schema_overview(request: Request) -> SchemaOverviewResponse:
    schema_cache = getattr(request.app.state, "schema_cache", None)
    schema_cache_error = getattr(request.app.state, "schema_cache_error", None)

    if schema_cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "schema_unavailable",
                "message": "Schema metadata is not available.",
                "details": {
                    "stage": "startup",
                    "error": schema_cache_error,
                },
            },
        )

    return _build_schema_overview_response(schema_cache)


@router.post("/schema/reload")
def reload_schema_cache(request: Request) -> dict[str, int | str]:
    schema_service = getattr(request.app.state, "schema_service", None)
    if schema_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "schema_unavailable",
                "message": "Schema service is not available.",
                "details": {"stage": "runtime"},
            },
        )

    try:
        schema_cache = schema_service.load_schema()
    except Exception as exc:
        request.app.state.schema_cache_error = str(exc)
        request.app.state.schema_cache = None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "schema_reload_failed",
                "message": "Schema metadata could not be reloaded.",
                "details": {"stage": "runtime", "error": str(exc)},
            },
        ) from exc

    request.app.state.schema_cache = schema_cache
    request.app.state.schema_cache_error = None
    return {"status": "ok", "table_count": len(schema_cache.tables)}


def _build_schema_overview_response(
    schema: DatabaseSchema,
) -> SchemaOverviewResponse:
    tables = [
        SchemaTableResponse(
            name=table.table_name,
            schema_name=table.schema_name,
            description=table.description,
            columns=[
                SchemaColumnResponse(
                    name=column.name,
                    data_type=column.data_type,
                    nullable=column.is_nullable,
                    description=column.description,
                )
                for column in table.columns
            ],
            primary_key=table.primary_key,
            foreign_keys=[
                SchemaForeignKeyResponse(
                    name=foreign_key.name,
                    columns=foreign_key.source_columns,
                    references_schema=foreign_key.target_schema,
                    references_table=foreign_key.target_table,
                    references_columns=foreign_key.target_columns,
                )
                for foreign_key in table.foreign_keys
            ],
        )
        for table in schema.tables
    ]

    return SchemaOverviewResponse(tables=tables)
