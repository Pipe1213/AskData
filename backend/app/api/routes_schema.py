from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.client_tokens import get_optional_client_token
from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.schemas.schema import (
    SchemaColumnResponse,
    SchemaForeignKeyResponse,
    SchemaOverviewResponse,
    SchemaTableResponse,
)
from app.services.database_target_service import DatabaseTargetService

router = APIRouter(tags=["schema"])


@router.get("/schema/overview", response_model=SchemaOverviewResponse)
def get_schema_overview(
    request: Request,
    client_token: str | None = Depends(get_optional_client_token),
) -> SchemaOverviewResponse:
    target_service = _get_target_service(request)
    try:
        _, schema = target_service.get_schema_for_active_target(client_token)
    except QueryPipelineError as exc:
        raise HTTPException(
            status_code=_map_error_code_to_status(exc.code),
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.to_error_payload()["details"],
            },
        ) from exc

    return _build_schema_overview_response(schema)


@router.post("/schema/reload")
def reload_schema_cache(
    request: Request,
    client_token: str | None = Depends(get_optional_client_token),
) -> dict[str, int | str]:
    target_service = _get_target_service(request)
    try:
        target, schema = target_service.refresh_schema_cache(client_token)
    except QueryPipelineError as exc:
        raise HTTPException(
            status_code=_map_error_code_to_status(exc.code),
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.to_error_payload()["details"],
            },
        ) from exc

    return {
        "status": "ok",
        "table_count": len(schema.tables),
        "target_id": target.target_id,
    }


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


def _get_target_service(request: Request) -> DatabaseTargetService:
    target_service = getattr(request.app.state, "database_target_service", None)
    if target_service is None:
        target_service = DatabaseTargetService()
        request.app.state.database_target_service = target_service
    return target_service


def _map_error_code_to_status(code: str) -> int:
    status_map = {
        "schema_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "runtime_target_missing": status.HTTP_409_CONFLICT,
        "schema_introspection_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "target_not_selected": status.HTTP_400_BAD_REQUEST,
    }
    return status_map.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
