import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_examples import router as examples_router
from app.api.routes_health import router as health_router
from app.api.routes_query import router as query_router
from app.api.routes_schema import router as schema_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.query_pipeline_service import QueryPipelineService
from app.services.schema_service import SchemaService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    schema_service = SchemaService(settings)
    query_pipeline_service = QueryPipelineService(settings=settings)

    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    app.state.schema_service = schema_service
    app.state.query_pipeline_service = query_pipeline_service
    app.state.schema_cache = None
    app.state.schema_cache_error = None

    try:
        app.state.schema_cache = schema_service.load_schema()
        logger.info(
            "Loaded schema cache with %s tables",
            len(app.state.schema_cache.tables),
        )
    except Exception as exc:
        app.state.schema_cache_error = str(exc)
        logger.exception("Failed to load schema cache at startup")

    yield
    logger.info("Stopping %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(examples_router)
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(schema_router)
    return app


app = create_app()
