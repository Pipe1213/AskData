from fastapi.testclient import TestClient

from app.core.exceptions import QueryPipelineError
from app.schemas.data_source import RuntimeConnectionTestResponse, RuntimeTargetActivationResponse
from app.schemas.query import ChartRecommendation, QueryResponse
from app.schemas.session import SessionDetail, SessionSummary, SessionTurn
from app.services.database_target_service import ResolvedDatabaseTarget


def _demo_target() -> ResolvedDatabaseTarget:
    return ResolvedDatabaseTarget(
        target_id="demo_pagila",
        target_type="demo_pagila",
        display_name="Pagila",
        persistence_allowed=True,
        dataset_name="pagila",
        schema_allowlist=["public"],
    )


def _runtime_target() -> ResolvedDatabaseTarget:
    return ResolvedDatabaseTarget(
        target_id="runtime_postgres:client-token",
        target_type="runtime_postgres",
        display_name="analytics @ localhost",
        persistence_allowed=False,
        schema_allowlist=["public"],
    )


def test_health_route(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_data_sources_route_returns_active_demo_target(client: TestClient) -> None:
    class DummyTargetService:
        def list_targets(self, client_token: str | None):
            target = _demo_target()
            return {
                "active_target": target.to_summary(is_active=True).model_dump(),
                "demo_targets": [target.to_summary(is_active=True).model_dump()],
                "runtime_target": None,
            }

    client.app.state.database_target_service = DummyTargetService()

    response = client.get("/data-sources")

    assert response.status_code == 200
    assert response.json()["active_target"]["target_id"] == "demo_pagila"


def test_examples_route_returns_runtime_prompts_when_runtime_target_is_active(client: TestClient) -> None:
    class DummyTargetService:
        def get_active_target(self, client_token: str | None):
            return _runtime_target()

    client.app.state.database_target_service = DummyTargetService()

    response = client.get("/examples")

    assert response.status_code == 200
    payload = response.json()
    assert payload["examples"]
    assert "revenue" in payload["examples"][0].lower()


def test_schema_overview_route_uses_active_target_schema(client: TestClient, sample_schema) -> None:
    class DummyTargetService:
        def get_schema_for_active_target(self, client_token: str | None):
            return _demo_target(), sample_schema

    client.app.state.database_target_service = DummyTargetService()

    response = client.get("/schema/overview")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["tables"]) == 2
    assert payload["tables"][0]["columns"]


def test_schema_reload_route_refreshes_active_target_schema(client: TestClient, sample_schema) -> None:
    class DummyTargetService:
        def refresh_schema_cache(self, client_token: str | None):
            return _demo_target(), sample_schema

    client.app.state.database_target_service = DummyTargetService()

    response = client.post("/schema/reload")

    assert response.status_code == 200
    assert response.json()["target_id"] == "demo_pagila"
    assert response.json()["table_count"] == 2


def test_query_route_returns_pipeline_success_for_demo_target(client: TestClient, sample_schema) -> None:
    captured: dict[str, object] = {}

    class DummyTargetService:
        def get_schema_for_active_target(self, client_token: str | None):
            return _demo_target(), sample_schema

    class DummyPipelineService:
        def run_query(
            self,
            question: str,
            schema,
            connection_settings=None,
            conversation_context=None,
            memory_context=None,
        ):
            captured["schema"] = schema
            captured["connection_settings"] = connection_settings
            return QueryResponse(
                question=question,
                answer_summary="Summary",
                generated_sql="SELECT 1",
                columns=["value"],
                rows=[[1]],
                row_count=1,
                chart_recommendation=ChartRecommendation(type="table_only"),
                warnings=[],
                used_tables=["public.payment"],
                persisted=False,
                repaired=False,
            )

    class DummySessionService:
        def get_memory_context(self, client_token: str, session_id: str | None, question: str, target_id: str):
            assert target_id == "demo_pagila"
            return None

    client.app.state.database_target_service = DummyTargetService()
    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.session_service = DummySessionService()

    response = client.post("/query", json={"question": "Test query"})

    assert response.status_code == 200
    assert response.json()["generated_sql"] == "SELECT 1"
    assert captured["schema"] == sample_schema
    assert captured["connection_settings"] is None


def test_query_route_runtime_mode_bypasses_persistence(client: TestClient, sample_schema) -> None:
    class DummyTargetService:
        def get_schema_for_active_target(self, client_token: str | None):
            return _runtime_target(), sample_schema

    class DummyPipelineService:
        def run_query(
            self,
            question: str,
            schema,
            connection_settings=None,
            conversation_context=None,
            memory_context=None,
        ):
            return QueryResponse(
                question=question,
                answer_summary="Runtime summary",
                generated_sql="SELECT 1",
                columns=["value"],
                rows=[[1]],
                row_count=1,
                chart_recommendation=ChartRecommendation(type="table_only"),
                warnings=[],
                used_tables=["public.payment"],
                persisted=False,
                repaired=False,
            )

    class DummySessionService:
        def get_memory_context(self, client_token: str, session_id: str | None, question: str, target_id: str):
            raise AssertionError("Runtime mode should not load persisted memory context.")

        def persist_success(self, *args, **kwargs):
            raise AssertionError("Runtime mode should not persist successful turns.")

    client.app.state.database_target_service = DummyTargetService()
    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.session_service = DummySessionService()

    response = client.post(
        "/query",
        json={"question": "Test query"},
        headers={"X-AskData-Client-Token": "client-token"},
    )

    assert response.status_code == 200
    assert response.json()["persisted"] is False


def test_query_route_returns_runtime_missing_error(client: TestClient) -> None:
    class DummyTargetService:
        def get_schema_for_active_target(self, client_token: str | None):
            raise QueryPipelineError(
                code="runtime_target_missing",
                message="Reconnect required.",
                stage="target",
                retryable=False,
            )

    client.app.state.database_target_service = DummyTargetService()

    response = client.post("/query", json={"question": "Test query"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "runtime_target_missing"


def test_sessions_route_returns_browser_scoped_history_for_demo_target(client: TestClient) -> None:
    class DummyTargetService:
        def get_active_target(self, client_token: str):
            return _demo_target()

    class DummySessionService:
        def list_sessions(self, client_token: str, target_id: str):
            assert client_token == "client-token"
            assert target_id == "demo_pagila"
            return [
                SessionSummary(
                    id="session-1",
                    title="Top customers",
                    created_at="2026-04-03T00:00:00+00:00",
                    updated_at="2026-04-03T00:00:00+00:00",
                    turn_count=1,
                    last_question="Which customers spent the most in total?",
                    last_status="success",
                )
            ]

    client.app.state.database_target_service = DummyTargetService()
    client.app.state.session_service = DummySessionService()

    response = client.get("/sessions", headers={"X-AskData-Client-Token": "client-token"})

    assert response.status_code == 200
    assert response.json()["sessions"][0]["title"] == "Top customers"


def test_sessions_route_returns_runtime_history_error_for_runtime_target(client: TestClient) -> None:
    class DummyTargetService:
        def get_active_target(self, client_token: str):
            return _runtime_target()

    client.app.state.database_target_service = DummyTargetService()

    response = client.get("/sessions", headers={"X-AskData-Client-Token": "client-token"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "runtime_history_unavailable"


def test_session_detail_route_returns_persisted_turns(client: TestClient) -> None:
    class DummyTargetService:
        def get_active_target(self, client_token: str):
            return _demo_target()

    class DummySessionService:
        def get_session(self, client_token: str, session_id: str, target_id: str):
            assert client_token == "client-token"
            assert session_id == "session-1"
            assert target_id == "demo_pagila"
            return SessionDetail(
                id="session-1",
                title="Top customers",
                created_at="2026-04-03T00:00:00+00:00",
                updated_at="2026-04-03T00:00:00+00:00",
                turns=[
                    SessionTurn(
                        id="turn-1",
                        question="Which customers spent the most in total?",
                        status="success",
                        created_at="2026-04-03T00:00:00+00:00",
                        response=QueryResponse(
                            question="Which customers spent the most in total?",
                            answer_summary="MARION led the ranking.",
                            generated_sql="SELECT 1",
                            columns=["name", "total"],
                            rows=[["MARION", 64.87]],
                            row_count=1,
                            chart_recommendation=ChartRecommendation(type="bar", x="name", y="total"),
                            warnings=[],
                            used_tables=["public.customer", "public.payment"],
                            session_id="session-1",
                            turn_id="turn-1",
                            persisted=True,
                            created_at="2026-04-03T00:00:00+00:00",
                            repaired=False,
                        ),
                    )
                ],
            )

    client.app.state.database_target_service = DummyTargetService()
    client.app.state.session_service = DummySessionService()

    response = client.get(
        "/sessions/session-1",
        headers={"X-AskData-Client-Token": "client-token"},
    )

    assert response.status_code == 200
    assert response.json()["session"]["turns"][0]["response"]["turn_id"] == "turn-1"


def test_runtime_connection_test_route_returns_backend_summary(client: TestClient) -> None:
    class DummyTargetService:
        def test_runtime_postgres_connection(self, client_token: str, payload):
            assert client_token == "client-token"
            assert payload.host == "localhost"
            return RuntimeConnectionTestResponse(
                database_version="16.2",
                visible_schemas=["public"],
                table_count=12,
                warnings=[],
            )

    client.app.state.database_target_service = DummyTargetService()

    response = client.post(
        "/data-sources/runtime/test",
        headers={"X-AskData-Client-Token": "client-token"},
        json={
            "host": "localhost",
            "port": 5432,
            "database": "analytics",
            "user": "postgres",
            "password": "postgres",
            "sslmode": "prefer",
            "schema_allowlist": ["public"],
        },
    )

    assert response.status_code == 200
    assert response.json()["table_count"] == 12


def test_runtime_activation_route_returns_active_target_summary(client: TestClient) -> None:
    class DummyTargetService:
        def activate_runtime_postgres_target(self, client_token: str, payload):
            assert client_token == "client-token"
            return RuntimeTargetActivationResponse(
                active_target=_runtime_target().to_summary(is_active=True),
                database_version="16.2",
                visible_schemas=["public"],
                table_count=12,
                warnings=[],
            )

    client.app.state.database_target_service = DummyTargetService()

    response = client.post(
        "/data-sources/runtime/activate",
        headers={"X-AskData-Client-Token": "client-token"},
        json={
            "host": "localhost",
            "port": 5432,
            "database": "analytics",
            "user": "postgres",
            "password": "postgres",
            "sslmode": "prefer",
            "schema_allowlist": ["public"],
        },
    )

    assert response.status_code == 200
    assert response.json()["active_target"]["target_type"] == "runtime_postgres"
