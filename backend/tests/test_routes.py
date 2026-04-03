from fastapi.testclient import TestClient

from app.core.exceptions import QueryPipelineError
from app.schemas.query import ChartRecommendation, QueryResponse
from app.schemas.session import SessionDetail, SessionSummary, SessionTurn


def test_health_route(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_examples_route(client: TestClient) -> None:
    response = client.get("/examples")

    assert response.status_code == 200
    payload = response.json()
    assert "examples" in payload
    assert isinstance(payload["examples"], list)
    assert payload["examples"]


def test_schema_overview_route_uses_cached_schema(client: TestClient, sample_schema) -> None:
    client.app.state.schema_cache = sample_schema
    client.app.state.schema_cache_error = None

    response = client.get("/schema/overview")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["tables"]) == 2
    assert payload["tables"][0]["columns"]


def test_query_route_returns_pipeline_success(client: TestClient) -> None:
    class DummyPipelineService:
        def run_query(self, question: str, schema, conversation_context=None):
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

    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.schema_cache = object()

    response = client.post("/query", json={"question": "Test query"})

    assert response.status_code == 200
    assert response.json()["generated_sql"] == "SELECT 1"


def test_query_route_returns_structured_pipeline_error(client: TestClient) -> None:
    class DummyPipelineService:
        def run_query(self, question: str, schema, conversation_context=None):
            raise QueryPipelineError(
                code="sql_validation_failed",
                message="Generated SQL failed validation.",
                stage="validation",
                retryable=True,
                details={"warnings": ["Ambiguous question"], "errors": ["Parse failure"]},
            )

    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.schema_cache = object()

    response = client.post("/query", json={"question": "Test query"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "sql_validation_failed"
    assert payload["warnings"] == ["Ambiguous question"]


def test_query_route_passes_conversation_context(client: TestClient) -> None:
    captured: dict[str, object] = {}

    class DummyPipelineService:
        def run_query(self, question: str, schema, conversation_context=None):
            captured["question"] = question
            captured["conversation_context"] = conversation_context
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

    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.schema_cache = object()

    response = client.post(
        "/query",
        json={
            "question": "Now only the top 5",
            "conversation_context": [
                {"role": "user", "content": "Which customers spent the most in total?"},
                {"role": "assistant", "content": "Customer 1 led the ranking."},
            ],
        },
    )

    assert response.status_code == 200
    assert captured["question"] == "Now only the top 5"
    assert captured["conversation_context"] is not None


def test_sessions_route_returns_browser_scoped_history(client: TestClient) -> None:
    class DummySessionService:
        def list_sessions(self, client_token: str):
            assert client_token == "client-token"
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

    client.app.state.session_service = DummySessionService()

    response = client.get("/sessions", headers={"X-AskData-Client-Token": "client-token"})

    assert response.status_code == 200
    assert response.json()["sessions"][0]["title"] == "Top customers"


def test_session_detail_route_returns_persisted_turns(client: TestClient) -> None:
    class DummySessionService:
        def get_session(self, client_token: str, session_id: str):
            assert client_token == "client-token"
            assert session_id == "session-1"
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

    client.app.state.session_service = DummySessionService()

    response = client.get(
        "/sessions/session-1",
        headers={"X-AskData-Client-Token": "client-token"},
    )

    assert response.status_code == 200
    assert response.json()["session"]["turns"][0]["response"]["turn_id"] == "turn-1"


def test_rerun_turn_route_returns_persisted_success(client: TestClient) -> None:
    class DummySessionService:
        def get_turn_rerun_context(self, client_token: str, session_id: str, turn_id: str):
            assert client_token == "client-token"
            assert session_id == "session-1"
            assert turn_id == "turn-1"
            return "Which customers spent the most in total?", []

        def persist_success(self, client_token: str, response: QueryResponse, session_id: str | None = None):
            assert client_token == "client-token"
            assert session_id == "session-1"
            return type(
                "PersistedRef",
                (),
                {
                    "session_id": "session-1",
                    "turn_id": "turn-2",
                    "created_at": "2026-04-03T00:00:00+00:00",
                },
            )()

    class DummyPipelineService:
        def run_query(self, question: str, schema, conversation_context=None):
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

    client.app.state.session_service = DummySessionService()
    client.app.state.query_pipeline_service = DummyPipelineService()
    client.app.state.schema_cache = object()

    response = client.post(
        "/sessions/session-1/turns/turn-1/rerun",
        headers={"X-AskData-Client-Token": "client-token"},
    )

    assert response.status_code == 200
    assert response.json()["turn_id"] == "turn-2"


def test_export_turn_csv_route_returns_csv_content(client: TestClient) -> None:
    class DummySessionService:
        def export_turn_csv(self, client_token: str, session_id: str, turn_id: str):
            assert client_token == "client-token"
            assert session_id == "session-1"
            assert turn_id == "turn-1"
            return "name,total\r\nMARION,64.87\r\n"

    client.app.state.session_service = DummySessionService()

    response = client.get(
        "/sessions/session-1/turns/turn-1/export.csv",
        headers={"X-AskData-Client-Token": "client-token"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "MARION" in response.text
