from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import QueryPipelineError
from app.schemas.query import ErrorPayload, QueryErrorResponse, QueryRequest, QueryResponse
from app.services.query_pipeline_service import QueryPipelineService

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def run_query(request: Request, payload: QueryRequest) -> QueryResponse | JSONResponse:
    pipeline_service = _get_pipeline_service(request)
    schema_cache = getattr(request.app.state, "schema_cache", None)

    try:
        return pipeline_service.run_query(
            question=payload.question,
            schema=schema_cache,
        )
    except QueryPipelineError as exc:
        status_code = _map_error_code_to_status(exc.code)
        warnings = exc.details.get("warnings", [])
        error_payload = QueryErrorResponse(
            error=ErrorPayload(**exc.to_error_payload()),
            warnings=warnings if isinstance(warnings, list) else [],
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


def _map_error_code_to_status(code: str) -> int:
    status_map = {
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "schema_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "sql_generation_failed": status.HTTP_502_BAD_GATEWAY,
        "unsafe_sql": status.HTTP_400_BAD_REQUEST,
        "sql_validation_failed": status.HTTP_400_BAD_REQUEST,
        "sql_execution_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return status_map.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
