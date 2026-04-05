from app.schemas.query import ConversationMessage
from app.services.planner_service import PlannerService


def test_planner_identifies_ranking_revenue_question() -> None:
    service = PlannerService()

    plan = service.build_plan("Which 10 customers spent the most in total?")

    assert plan.task_type == "ranking"
    assert "amount" in plan.metric_targets
    assert "customer" in plan.dimension_targets
    assert "payment" in plan.candidate_table_families


def test_planner_marks_referential_follow_up_as_refinement() -> None:
    service = PlannerService()

    plan = service.build_plan(
        "Now show only the top 5",
        conversation_context=[
            ConversationMessage(role="user", content="Which customers spent the most in total?"),
            ConversationMessage(role="assistant", content="MARION led the ranking by total spend."),
        ],
    )

    assert plan.task_type == "follow_up_refinement"
    assert plan.memory_summary is not None
    assert plan.confidence in {"low", "medium"}


def test_planner_identifies_schema_lookup_questions() -> None:
    service = PlannerService()

    plan = service.build_plan("Which tables contain payment information?")

    assert plan.task_type == "schema_lookup"
    assert plan.execution_strategy == "schema_guided"
