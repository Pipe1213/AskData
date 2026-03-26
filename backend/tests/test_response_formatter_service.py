from types import SimpleNamespace
from decimal import Decimal

from app.llm.base import BaseLLMClient
from app.schemas.execution import SQLExecutionResult
from app.services.response_formatter_service import ResponseFormatterService


class WeakSummaryLLMClient(BaseLLMClient):
    def generate_text(self, messages, config=None):
        return SimpleNamespace(text="Top")

    def generate_structured(self, messages, response_model, config=None):
        raise NotImplementedError


def test_response_formatter_fallback_summary_uses_leading_row_details() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT category, revenue FROM report",
        success=True,
        columns=["category", "revenue"],
        rows=[["Sports", 12000], ["Animation", 11100]],
        row_count=2,
    )

    response = service.format_query_response(
        question="What are the top categories by revenue?",
        generated_sql="SELECT category, revenue FROM report",
        execution_result=execution_result,
        used_tables=["public.payment", "public.category"],
        warnings=[],
    )

    assert "leading result" in response.answer_summary.lower()
    assert "Sports" in response.answer_summary
    assert response.chart_recommendation.type == "bar"


def test_response_formatter_rejects_too_short_llm_summary() -> None:
    service = ResponseFormatterService(
        llm_client=WeakSummaryLLMClient(),
        settings=SimpleNamespace(openai_api_key=None),
    )
    execution_result = SQLExecutionResult(
        sql="SELECT staff_id, revenue FROM report",
        success=True,
        columns=["staff_id", "revenue"],
        rows=[[1, 3392.0], [2, 3187.0]],
        row_count=2,
    )

    response = service.format_query_response(
        question="How much revenue did each staff member process?",
        generated_sql="SELECT staff_id, revenue FROM report",
        execution_result=execution_result,
        used_tables=["public.payment", "public.staff"],
        warnings=[],
    )

    assert response.answer_summary != "Top"
    assert "leading result" in response.answer_summary.lower()


def test_response_formatter_prefers_label_and_metric_over_identifier_columns() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT customer_id, first_name, total_spent FROM report",
        success=True,
        columns=["customer_id", "first_name", "total_spent"],
        rows=[[178, "MARION", Decimal("64.87")], [181, "ANA", Decimal("58.91")]],
        row_count=2,
    )

    response = service.format_query_response(
        question="Which customers spent the most in total?",
        generated_sql="SELECT customer_id, first_name, total_spent FROM report",
        execution_result=execution_result,
        used_tables=["public.customer", "public.payment"],
        warnings=[],
    )

    assert "first_name=MARION" in response.answer_summary
    assert "total_spent=64.87" in response.answer_summary
    assert response.chart_recommendation.type == "bar"
    assert response.chart_recommendation.x == "first_name"
    assert response.chart_recommendation.y == "total_spent"


def test_response_formatter_avoids_chart_for_large_result_sets() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    rows = [[f"customer_{index}", index * 10] for index in range(30)]
    execution_result = SQLExecutionResult(
        sql="SELECT customer, total FROM report",
        success=True,
        columns=["customer", "total"],
        rows=rows,
        row_count=len(rows),
    )

    response = service.format_query_response(
        question="Show customer totals",
        generated_sql="SELECT customer, total FROM report",
        execution_result=execution_result,
        used_tables=["public.customer", "public.payment"],
        warnings=[],
    )

    assert response.chart_recommendation.type == "table_only"
