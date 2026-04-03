from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from app.api.client_tokens import require_client_token
from app.core.exceptions import QueryPipelineError
from app.schemas.query import DebugPayload, ErrorPayload, QueryErrorResponse, QueryResponse
from app.schemas.session import (
    SessionDetailResponse,
    SessionListResponse,
    SessionRenameRequest,
)
from app.services.query_pipeline_service import QueryPipelineService
from app.services.session_service import SessionService

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    client_token: str = Depends(require_client_token),
) -> SessionListResponse:
    session_service = _get_session_service(request)
    return SessionListResponse(sessions=session_service.list_sessions(client_token))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(
    session_id: str,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> SessionDetailResponse:
    session_service = _get_session_service(request)
    session = session_service.get_session(client_token, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session was not found for the current client token.",
        )

    return SessionDetailResponse(session=session)


@router.patch("/sessions/{session_id}", response_model=SessionDetailResponse)
def rename_session(
    session_id: str,
    payload: SessionRenameRequest,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> SessionDetailResponse:
    session_service = _get_session_service(request)
    try:
        renamed = session_service.rename_session(client_token, session_id, payload.title)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if renamed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session was not found for the current client token.",
        )

    session = session_service.get_session(client_token, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session was not found for the current client token.",
        )

    return SessionDetailResponse(session=session)


@router.post("/sessions/{session_id}/turns/{turn_id}/rerun", response_model=QueryResponse)
def rerun_turn(
    session_id: str,
    turn_id: str,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> QueryResponse | JSONResponse:
    session_service = _get_session_service(request)
    pipeline_service = _get_pipeline_service(request)
    schema_cache = getattr(request.app.state, "schema_cache", None)
    debug_mode = bool(getattr(getattr(pipeline_service, "settings", None), "debug_mode", False))

    rerun_input = session_service.get_turn_rerun_context(client_token, session_id, turn_id)
    if rerun_input is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session turn was not found for the current client token.",
        )

    question, conversation_context = rerun_input

    try:
        response = pipeline_service.run_query(
            question=question,
            schema=schema_cache,
            conversation_context=conversation_context,
        )
        persisted_ref = session_service.persist_success(
            client_token=client_token,
            response=response,
            session_id=session_id,
        )
        return response.model_copy(
            update={
                "session_id": persisted_ref.session_id,
                "turn_id": persisted_ref.turn_id,
                "persisted": True,
                "created_at": persisted_ref.created_at,
            }
        )
    except QueryPipelineError as exc:
        error_payload = QueryErrorResponse(
            error=ErrorPayload(**exc.to_error_payload()),
            warnings=(
                exc.details.get("warnings", [])
                if isinstance(exc.details.get("warnings", []), list)
                else []
            ),
            debug=(
                DebugPayload(
                    stage=exc.stage,
                    repair_attempted=False,
                )
                if debug_mode
                else None
            ),
        )
        persisted_ref = session_service.persist_error(
            client_token=client_token,
            question=question,
            error_payload=error_payload,
            session_id=session_id,
        )
        error_payload = error_payload.model_copy(
            update={
                "session_id": persisted_ref.session_id,
                "turn_id": persisted_ref.turn_id,
                "persisted": True,
                "created_at": persisted_ref.created_at,
            }
        )
        return JSONResponse(
            status_code=_map_error_code_to_status(exc.code),
            content=error_payload.model_dump(),
        )


@router.get("/sessions/{session_id}/turns/{turn_id}/export.csv")
def export_turn_csv(
    session_id: str,
    turn_id: str,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> Response:
    session_service = _get_session_service(request)
    csv_content = session_service.export_turn_csv(client_token, session_id, turn_id)
    if csv_content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Successful turn preview was not found for export.",
        )

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="askdata-{turn_id}.csv"',
        },
    )


def _get_session_service(request: Request) -> SessionService:
    session_service = getattr(request.app.state, "session_service", None)
    if session_service is None:
        session_service = SessionService()
        request.app.state.session_service = session_service

    return session_service


def _get_pipeline_service(request: Request) -> QueryPipelineService:
    pipeline_service = getattr(request.app.state, "query_pipeline_service", None)
    if pipeline_service is None:
        pipeline_service = QueryPipelineService()
        request.app.state.query_pipeline_service = pipeline_service

    return pipeline_service


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
