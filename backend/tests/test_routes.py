from fastapi.testclient import TestClient

from app.core.exceptions import QueryPipelineError
from app.schemas.query import ChartRecommendation, QueryResponse


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
                chart_recommendation=ChartRecommendation(type="table_only"),
                warnings=[],
                used_tables=["public.payment"],
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
                chart_recommendation=ChartRecommendation(type="table_only"),
                warnings=[],
                used_tables=["public.payment"],
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
