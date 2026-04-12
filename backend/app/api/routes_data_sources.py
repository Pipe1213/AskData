from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.client_tokens import get_optional_client_token, require_client_token
from app.core.exceptions import QueryPipelineError
from app.schemas.data_source import (
    DataSourceActivationResponse,
    DataSourcesResponse,
    DemoTargetActivateRequest,
    RuntimeConnectionTestResponse,
    RuntimePostgresConnectionInput,
    RuntimeTargetActivationResponse,
)
from app.services.database_target_service import DatabaseTargetService

router = APIRouter(tags=["data-sources"])


@router.get("/data-sources", response_model=DataSourcesResponse)
def list_data_sources(
    request: Request,
    client_token: str | None = Depends(get_optional_client_token),
) -> DataSourcesResponse | JSONResponse:
    target_service = _get_target_service(request)
    try:
        return target_service.list_targets(client_token)
    except QueryPipelineError as exc:
        return _error_response(exc)


@router.post("/data-sources/runtime/test", response_model=RuntimeConnectionTestResponse)
def test_runtime_connection(
    payload: RuntimePostgresConnectionInput,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> RuntimeConnectionTestResponse | JSONResponse:
    target_service = _get_target_service(request)
    try:
        return target_service.test_runtime_postgres_connection(client_token, payload)
    except QueryPipelineError as exc:
        return _error_response(exc)


@router.post("/data-sources/runtime/activate", response_model=RuntimeTargetActivationResponse)
def activate_runtime_connection(
    payload: RuntimePostgresConnectionInput,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> RuntimeTargetActivationResponse | JSONResponse:
    target_service = _get_target_service(request)
    try:
        return target_service.activate_runtime_postgres_target(client_token, payload)
    except QueryPipelineError as exc:
        return _error_response(exc)


@router.post("/data-sources/demo/activate", response_model=DataSourceActivationResponse)
def activate_demo_target(
    payload: DemoTargetActivateRequest,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> DataSourceActivationResponse | JSONResponse:
    target_service = _get_target_service(request)
    try:
        target, schema = target_service.activate_demo_target(client_token, payload.target_id)
    except QueryPipelineError as exc:
        return _error_response(exc)

    return DataSourceActivationResponse(
        active_target=target.to_summary(is_active=True),
        table_count=len(schema.tables),
    )


@router.delete("/data-sources/runtime", response_model=DataSourceActivationResponse)
def disconnect_runtime_target(
    request: Request,
    client_token: str = Depends(require_client_token),
) -> DataSourceActivationResponse | JSONResponse:
    target_service = _get_target_service(request)
    try:
        target = target_service.clear_runtime_target(client_token)
        _, schema = target_service.get_schema_for_active_target(client_token)
    except QueryPipelineError as exc:
        return _error_response(exc)

    return DataSourceActivationResponse(
        active_target=target.to_summary(is_active=True),
        table_count=len(schema.tables),
    )


def _get_target_service(request: Request) -> DatabaseTargetService:
    target_service = getattr(request.app.state, "database_target_service", None)
    if target_service is None:
        target_service = DatabaseTargetService()
        request.app.state.database_target_service = target_service
    return target_service


def _error_response(exc: QueryPipelineError) -> JSONResponse:
    status_map = {
        "connection_test_failed": status.HTTP_400_BAD_REQUEST,
        "runtime_target_missing": status.HTTP_409_CONFLICT,
        "schema_introspection_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "target_not_selected": status.HTTP_400_BAD_REQUEST,
        "unsupported_runtime_target": status.HTTP_400_BAD_REQUEST,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        content={"error": exc.to_error_payload()},
    )
