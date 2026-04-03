from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.client_tokens import get_optional_client_token
from app.core.exceptions import QueryPipelineError
from app.schemas.query import DebugPayload, ErrorPayload, QueryErrorResponse, QueryRequest, QueryResponse
from app.services.query_pipeline_service import QueryPipelineService
from app.services.session_service import SessionService

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def run_query(
    request: Request,
    payload: QueryRequest,
    client_token: str | None = Depends(get_optional_client_token),
) -> QueryResponse | JSONResponse:
    pipeline_service = _get_pipeline_service(request)
    session_service = _get_session_service(request)
    schema_cache = getattr(request.app.state, "schema_cache", None)
    debug_mode = bool(getattr(getattr(pipeline_service, "settings", None), "debug_mode", False))

    try:
        response = pipeline_service.run_query(
            question=payload.question,
            schema=schema_cache,
            conversation_context=payload.conversation_context,
        )
        if client_token is None:
            return response

        try:
            persisted_ref = session_service.persist_success(
                client_token=client_token,
                response=response,
                session_id=payload.session_id,
            )
        except ValueError as exc:
            raise QueryPipelineError(
                code="invalid_session",
                message=str(exc),
                stage="persistence",
                retryable=False,
            ) from exc

        return response.model_copy(
            update={
                "session_id": persisted_ref.session_id,
                "turn_id": persisted_ref.turn_id,
                "persisted": True,
                "created_at": persisted_ref.created_at,
            }
        )
    except QueryPipelineError as exc:
        status_code = _map_error_code_to_status(exc.code)
        warnings = exc.details.get("warnings", [])
        error_payload = QueryErrorResponse(
            error=ErrorPayload(**exc.to_error_payload()),
            warnings=warnings if isinstance(warnings, list) else [],
            debug=(
                DebugPayload(
                    stage=exc.stage,
                    repair_attempted="repair" in " ".join(warnings).lower(),
                )
                if debug_mode
                else None
            ),
        )
        if client_token is not None and payload.question.strip():
            try:
                persisted_ref = session_service.persist_error(
                    client_token=client_token,
                    question=payload.question.strip(),
                    error_payload=error_payload,
                    session_id=payload.session_id,
                )
                error_payload = error_payload.model_copy(
                    update={
                        "session_id": persisted_ref.session_id,
                        "turn_id": persisted_ref.turn_id,
                        "persisted": True,
                        "created_at": persisted_ref.created_at,
                    }
                )
            except ValueError:
                if exc.code != "invalid_session":
                    status_code = status.HTTP_404_NOT_FOUND
                    error_payload = QueryErrorResponse(
                        error=ErrorPayload(
                            code="invalid_session",
                            message="Session was not found for the current client token.",
                            details={"stage": "persistence", "retryable": False},
                        ),
                        warnings=[],
                    )
        return JSONResponse(
            status_code=status_code,
            content=error_payload.model_dump(),
        )
    except Exception:
        error_payload = QueryErrorResponse(
            error=ErrorPayload(
                code="internal_error",
                message="An unexpected internal error occurred.",
                details={
                    "stage": "pipeline",
                    "retryable": False,
                },
            ),
            warnings=[],
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload.model_dump(),
        )


def _get_pipeline_service(request: Request) -> QueryPipelineService:
    pipeline_service = getattr(request.app.state, "query_pipeline_service", None)
    if pipeline_service is None:
        pipeline_service = QueryPipelineService()
        request.app.state.query_pipeline_service = pipeline_service

    return pipeline_service


def _get_session_service(request: Request) -> SessionService:
    session_service = getattr(request.app.state, "session_service", None)
    if session_service is None:
        session_service = SessionService()
        request.app.state.session_service = session_service

    return session_service


def _map_error_code_to_status(code: str) -> int:
    status_map = {
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "schema_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "invalid_session": status.HTTP_404_NOT_FOUND,
        "sql_generation_failed": status.HTTP_502_BAD_GATEWAY,
        "unsafe_sql": status.HTTP_400_BAD_REQUEST,
        "sql_validation_failed": status.HTTP_400_BAD_REQUEST,
        "sql_execution_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return status_map.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
