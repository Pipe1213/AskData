from fastapi import APIRouter

from app.schemas.examples import ExamplesResponse
from app.services.examples_service import ExamplesService

router = APIRouter(tags=["examples"])
examples_service = ExamplesService()


@router.get("/examples", response_model=ExamplesResponse)
def get_examples() -> ExamplesResponse:
    return ExamplesResponse(examples=examples_service.get_examples())
