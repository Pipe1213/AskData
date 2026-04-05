from app.schemas.query import ChartRecommendation, QueryPlan, QueryResponse
from app.schemas.session import SessionTurn
from app.services.memory_service import MemoryService


def test_memory_service_builds_context_for_referential_follow_up() -> None:
    service = MemoryService()
    prior_turn = SessionTurn(
        id="turn-1",
        question="Which customers spent the most in total?",
        status="success",
        created_at="2026-04-05T00:00:00+00:00",
        response=QueryResponse(
            question="Which customers spent the most in total?",
            answer_summary="The leading result was first_name=MARION, total_spent=64.87.",
            generated_sql="SELECT first_name, total_spent FROM report",
            columns=["first_name", "total_spent"],
            rows=[["MARION", 64.87], ["ANA", 58.91]],
            row_count=2,
            chart_recommendation=ChartRecommendation(type="bar", x="first_name", y="total_spent"),
            warnings=[],
            used_tables=["public.customer", "public.payment"],
            repaired=False,
            plan=QueryPlan(
                task_type="ranking",
                execution_strategy="single_query",
                interpreted_goal="Return a ranked analytical answer using the strongest matching business metric.",
                metric_targets=["total_spent"],
                dimension_targets=["customer", "first_name"],
                candidate_table_families=["payment", "customer"],
            ),
        ),
    )

    context = service.build_memory_context(
        "Now show only the top 5",
        [prior_turn],
    )

    assert context is not None
    assert context.inherited_from_turn_ids == ["turn-1"]
    assert "total_spent" in context.suggested_metric_targets
    assert "customer" in context.suggested_dimension_targets
    assert "payment" in context.suggested_table_families


def test_memory_service_ignores_unrelated_topic_when_not_referential() -> None:
    service = MemoryService()
    prior_turn = SessionTurn(
        id="turn-1",
        question="Which customers spent the most in total?",
        status="success",
        created_at="2026-04-05T00:00:00+00:00",
        response=QueryResponse(
            question="Which customers spent the most in total?",
            answer_summary="The leading result was first_name=MARION, total_spent=64.87.",
            generated_sql="SELECT first_name, total_spent FROM report",
            columns=["first_name", "total_spent"],
            rows=[["MARION", 64.87], ["ANA", 58.91]],
            row_count=2,
            chart_recommendation=ChartRecommendation(type="bar", x="first_name", y="total_spent"),
            warnings=[],
            used_tables=["public.customer", "public.payment"],
            repaired=False,
            plan=QueryPlan(
                task_type="ranking",
                execution_strategy="single_query",
                interpreted_goal="Return a ranked analytical answer using the strongest matching business metric.",
                metric_targets=["total_spent"],
                dimension_targets=["customer", "first_name"],
                candidate_table_families=["payment", "customer"],
            ),
        ),
    )

    context = service.build_memory_context(
        "Which tables contain address information?",
        [prior_turn],
    )

    assert context is None
