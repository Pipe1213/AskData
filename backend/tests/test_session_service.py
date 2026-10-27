from datetime import datetime, timezone

from app.schemas.query import QueryResponse
from app.services.session_service import SessionService


def _row(service: SessionService, response: QueryResponse | None, **overrides) -> dict:
    row = {
        "id": "turn-1",
        "question": "Who are the best customers?",
        "status": "success",
        "answer_summary": "“Best” can mean two things. (1) Spent the most (2) Rented the most",
        "generated_sql": "",
        "columns_json": [],
        "rows_preview_json": [],
        "row_count": 0,
        "chart_type": None,
        "chart_x": None,
        "chart_y": None,
        "primary_artifact": "summary",
        "warnings_json": [],
        "used_tables_json": [],
        "memory_json": {},
        "plan_json": {},
        "trace_json": {},
        "error_code": None,
        "error_message": None,
        "repaired": False,
        "response_payload": (
            service._to_jsonable(service._build_response_payload(response)) if response else None
        ),
        "created_at": datetime(2026, 10, 26, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_clarification_turn_round_trips_through_saved_row() -> None:
    service = SessionService()
    response = QueryResponse(
        question="Who are the best customers?",
        response_type="clarification",
        clarification={"question": "“Best” can mean two things. Which one?", "options": ["Spent the most", "Rented the most"]},
        answer_summary="ignored",
        generated_sql="",
        chart_recommendation={"type": "table_only"},
    )

    turn = service._build_session_turn("session-1", _row(service, response))

    assert turn.response is not None
    assert turn.response.response_type == "clarification"
    assert turn.response.clarification is not None
    assert turn.response.clarification.options == ["Spent the most", "Rented the most"]
    assert turn.response.cannot_answer is None


def test_cannot_answer_and_assumptions_round_trip() -> None:
    service = SessionService()
    declined = QueryResponse(
        question="What was the profit per film?",
        response_type="cannot_answer",
        cannot_answer={"reason": "No cost data is recorded.", "alternatives": ["Which films earned the most?"]},
        answer_summary="ignored",
        generated_sql="",
        chart_recommendation={"type": "table_only"},
    )
    answered = QueryResponse(
        question="Top customer?",
        answer_summary="Karl Seal spent the most: $221.55.",
        assumptions=["“spent” = total of all payments"],
        generated_sql="SELECT 1",
        chart_recommendation={"type": "table_only"},
    )

    declined_turn = service._build_session_turn("s", _row(service, declined))
    answered_turn = service._build_session_turn("s", _row(service, answered))

    assert declined_turn.response.response_type == "cannot_answer"
    assert declined_turn.response.cannot_answer.alternatives == ["Which films earned the most?"]
    assert answered_turn.response.response_type == "answer"
    assert answered_turn.response.assumptions == ["“spent” = total of all payments"]


def test_turn_saved_before_the_column_existed_is_a_plain_answer() -> None:
    service = SessionService()

    turn = service._build_session_turn("s", _row(service, None))

    assert turn.response.response_type == "answer"
    assert turn.response.clarification is None
    assert turn.response.assumptions == []
    assert turn.response.answer_summary.startswith("“Best”")
