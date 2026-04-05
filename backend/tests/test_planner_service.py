from app.schemas.query import ConversationMessage, MemoryContext, TurnMemory
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


def test_planner_inherits_memory_for_follow_up_refinement() -> None:
    service = PlannerService()

    memory_context = MemoryContext(
        memory_summary="Previous result focus: first_name=MARION, total_spent=64.87.",
        suggested_metric_targets=["amount", "total_spent"],
        suggested_dimension_targets=["customer", "customer_id", "first_name"],
        suggested_table_families=["payment", "customer"],
        inherited_from_turn_ids=["turn-1"],
        relevant_turn_memories=[
            TurnMemory(
                source_turn_id="turn-1",
                question="Which customers spent the most in total?",
                task_type="ranking",
                interpreted_goal="Return a ranked analytical answer using the strongest matching business metric.",
                metric_targets=["amount", "total_spent"],
                dimension_targets=["customer", "customer_id", "first_name"],
                candidate_table_families=["payment", "customer"],
                used_tables=["public.payment", "public.customer"],
                generated_sql="SELECT 1",
                answer_summary="MARION led the ranking.",
                row_count=10,
                result_focus="Previous result focus: first_name=MARION, total_spent=64.87.",
                memory_tags=["customer", "payment", "spent", "top"],
            )
        ],
    )

    plan = service.build_plan(
        "Now show only the top 5",
        conversation_context=[
            ConversationMessage(role="user", content="Which customers spent the most in total?"),
            ConversationMessage(role="assistant", content="MARION led the ranking by total spend."),
        ],
        memory_context=memory_context,
    )

    assert plan.task_type == "follow_up_refinement"
    assert "amount" in plan.metric_targets
    assert "customer" in plan.dimension_targets
    assert "payment" in plan.candidate_table_families
    assert plan.inherited_from_turn_ids == ["turn-1"]
