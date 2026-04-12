from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.client_tokens import get_optional_client_token
from app.core.exceptions import QueryPipelineError
from app.schemas.examples import ExamplesResponse
from app.services.database_target_service import DatabaseTargetService
from app.services.examples_service import ExamplesService

router = APIRouter(tags=["examples"])
examples_service = ExamplesService()


@router.get("/examples", response_model=ExamplesResponse)
def get_examples(
    request: Request,
    client_token: str | None = Depends(get_optional_client_token),
) -> ExamplesResponse:
    target_service = _get_target_service(request)
    try:
        target = target_service.get_active_target(client_token)
    except QueryPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.to_error_payload()["details"],
            },
        ) from exc
    return ExamplesResponse(examples=examples_service.get_examples(target))


def _get_target_service(request: Request) -> DatabaseTargetService:
    target_service = getattr(request.app.state, "database_target_service", None)
    if target_service is None:
        target_service = DatabaseTargetService()
        request.app.state.database_target_service = target_service
    return target_service
