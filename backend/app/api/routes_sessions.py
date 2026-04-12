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
from app.services.database_target_service import DatabaseTargetService
from app.services.query_pipeline_service import QueryPipelineService
from app.services.session_service import SessionService

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    client_token: str = Depends(require_client_token),
) -> SessionListResponse:
    session_service = _get_session_service(request)
    active_target = _require_persisted_target(request, client_token)
    return SessionListResponse(
        sessions=session_service.list_sessions(client_token, active_target.target_id)
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(
    session_id: str,
    request: Request,
    client_token: str = Depends(require_client_token),
) -> SessionDetailResponse:
    session_service = _get_session_service(request)
    active_target = _require_persisted_target(request, client_token)
    session = session_service.get_session(client_token, session_id, active_target.target_id)
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
    active_target = _require_persisted_target(request, client_token)
    try:
        renamed = session_service.rename_session(
            client_token,
            session_id,
            payload.title,
            active_target.target_id,
        )
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

    session = session_service.get_session(client_token, session_id, active_target.target_id)
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
    target_service = _get_target_service(request)
    debug_mode = bool(getattr(getattr(pipeline_service, "settings", None), "debug_mode", False))
    active_target = _require_persisted_target(request, client_token)
    try:
        _, schema = target_service.get_schema_for_active_target(client_token)
    except QueryPipelineError as exc:
        return JSONResponse(
            status_code=_map_error_code_to_status(exc.code),
            content=QueryErrorResponse(
                error=ErrorPayload(**exc.to_error_payload()),
                warnings=[],
            ).model_dump(),
        )

    rerun_input = session_service.get_turn_rerun_context(
        client_token,
        session_id,
        turn_id,
        active_target.target_id,
    )
    if rerun_input is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session turn was not found for the current client token.",
        )

    question, conversation_context, memory_context = rerun_input

    try:
        response = pipeline_service.run_query(
            question=question,
            schema=schema,
            connection_settings=active_target.connection_settings,
            conversation_context=conversation_context,
            memory_context=memory_context,
        )
        persisted_ref = session_service.persist_success(
            client_token=client_token,
            response=response,
            session_id=session_id,
            target_id=active_target.target_id,
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
                    inherited_turn_ids=(
                        memory_context.inherited_from_turn_ids
                        if memory_context is not None
                        else []
                    ),
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
            target_id=active_target.target_id,
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
    active_target = _require_persisted_target(request, client_token)
    csv_content = session_service.export_turn_csv(
        client_token,
        session_id,
        turn_id,
        active_target.target_id,
    )
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


def _get_target_service(request: Request) -> DatabaseTargetService:
    target_service = getattr(request.app.state, "database_target_service", None)
    if target_service is None:
        target_service = DatabaseTargetService()
        request.app.state.database_target_service = target_service

    return target_service


def _require_persisted_target(request: Request, client_token: str):
    target_service = _get_target_service(request)
    try:
        active_target = target_service.get_active_target(client_token)
    except QueryPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.to_error_payload()["details"],
            },
        ) from exc
    if active_target.persistence_allowed:
        return active_target

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "runtime_history_unavailable",
            "message": "Persistent session history is disabled while a runtime PostgreSQL connection is active.",
        },
    )


def _map_error_code_to_status(code: str) -> int:
    status_map = {
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "schema_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "invalid_session": status.HTTP_404_NOT_FOUND,
        "runtime_history_unavailable": status.HTTP_409_CONFLICT,
        "runtime_target_missing": status.HTTP_409_CONFLICT,
        "sql_generation_failed": status.HTTP_502_BAD_GATEWAY,
        "unsafe_sql": status.HTTP_400_BAD_REQUEST,
        "sql_validation_failed": status.HTTP_400_BAD_REQUEST,
        "sql_execution_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return status_map.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
