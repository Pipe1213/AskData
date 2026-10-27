from types import SimpleNamespace
from decimal import Decimal

from app.llm.base import BaseLLMClient
from app.schemas.execution import SQLExecutionResult
from app.schemas.query import QueryPlan
from app.services.response_formatter_service import ResponseFormatterService


class WeakSummaryLLMClient(BaseLLMClient):
    def generate_text(self, messages, config=None):
        return SimpleNamespace(text="Top")

    def generate_structured(self, messages, response_model, config=None):
        raise NotImplementedError


def test_response_formatter_fallback_summary_uses_direct_business_language() -> None:
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

    assert "top result" in response.answer_summary.lower()
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
    assert "highest revenue" in response.answer_summary.lower()


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

    assert "MARION" in response.answer_summary
    assert "64.87" in response.answer_summary
    assert response.chart_recommendation.type == "bar"
    assert response.chart_recommendation.x == "first_name"
    assert response.chart_recommendation.y == "total_spent"


def test_response_formatter_returns_clear_no_result_summary() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT * FROM rental WHERE EXTRACT(YEAR FROM rental_date) = 1990",
        success=True,
        columns=["rental_id"],
        rows=[],
        row_count=0,
    )

    response = service.format_query_response(
        question="Show rentals from the year 1990.",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.rental"],
        warnings=[],
    )

    assert response.answer_summary == "Nothing in the data matched this question."
    assert response.chart_recommendation.type == "table_only"


def test_response_formatter_prefers_revenue_metric_over_count_for_spend_question() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT first_name, payment_count, total_spent FROM report",
        success=True,
        columns=["first_name", "payment_count", "total_spent"],
        rows=[["MARION", 13, Decimal("64.87")], ["ANA", 9, Decimal("58.91")]],
        row_count=2,
    )

    response = service.format_query_response(
        question="Which customers spent the most in total?",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.customer", "public.payment"],
        warnings=[],
    )

    assert "64.87" in response.answer_summary
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


def test_response_formatter_marks_ranking_question_as_table_primary() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT customer, total_spent FROM report",
        success=True,
        columns=["customer", "total_spent"],
        rows=[["MARION", 64.87], ["ANA", 58.91]],
        row_count=2,
    )

    response = service.format_query_response(
        question="Which 10 customers spent the most in total?",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.customer", "public.payment"],
        warnings=[],
        plan=QueryPlan(
            task_type="ranking",
            execution_strategy="single_query",
            interpreted_goal="Return a ranked analytical answer using the strongest matching business metric.",
        ),
    )

    assert response.primary_artifact == "table"
    assert response.memory is not None


def test_response_formatter_marks_trend_question_as_chart_primary() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT rental_month, rental_count FROM report",
        success=True,
        columns=["rental_month", "rental_count"],
        rows=[["2022-01-01", 120], ["2022-02-01", 182], ["2022-03-01", 174]],
        row_count=3,
    )

    response = service.format_query_response(
        question="How many rentals happened each month?",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.rental"],
        warnings=[],
        plan=QueryPlan(
            task_type="trend",
            execution_strategy="single_query",
            interpreted_goal="Summarize how the requested metric changes over time.",
        ),
    )

    assert response.primary_artifact == "chart"
    assert "February 2022" in response.answer_summary
    assert "182" in response.answer_summary


def test_response_formatter_prefers_time_column_for_trend_chart() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT order_channel, revenue_month, total_revenue FROM report",
        success=True,
        columns=["order_channel", "revenue_month", "total_revenue"],
        rows=[
            ["online", "2024-01-01", 1200],
            ["store", "2024-02-01", 1480],
            ["online", "2024-03-01", 1525],
        ],
        row_count=3,
    )

    response = service.format_query_response(
        question="How did monthly revenue change by sales channel?",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.orders", "public.payments"],
        warnings=[],
        plan=QueryPlan(
            task_type="trend",
            execution_strategy="single_query",
            interpreted_goal="Summarize how the requested metric changes over time.",
        ),
    )

    assert response.chart_recommendation.type == "line"
    assert response.chart_recommendation.x == "revenue_month"
    assert response.primary_artifact == "chart"


def test_response_formatter_keeps_schema_lookup_on_summary() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(
        sql="SELECT table_name FROM report",
        success=True,
        columns=["table_name"],
        rows=[["shipment"], ["shipments"]],
        row_count=2,
    )

    response = service.format_query_response(
        question="Which tables contain shipment information?",
        generated_sql=execution_result.sql,
        execution_result=execution_result,
        used_tables=["public.shipments"],
        warnings=[],
        plan=QueryPlan(
            task_type="schema_lookup",
            execution_strategy="schema_guided",
            interpreted_goal="Identify the most relevant schema area before answering.",
        ),
    )

    assert response.primary_artifact == "summary"


class FixedSummaryLLMClient(BaseLLMClient):
    def __init__(self, text: str) -> None:
        self.text = text
        self.last_messages = None

    def generate_text(self, messages, config=None):
        self.last_messages = messages
        return SimpleNamespace(text=self.text)

    def generate_structured(self, messages, response_model, config=None):
        raise NotImplementedError


def _ranking_result(row_count: int = 10) -> SQLExecutionResult:
    rows = [[526, "KARL", "SEAL", Decimal("221.55")], [148, "ELEANOR", "HUNT", Decimal("216.54")]]
    rows += [[100 + index, "NAME", "LAST", Decimal("174.66")] for index in range(row_count - 2)]
    return SQLExecutionResult(
        sql="SELECT ...",
        success=True,
        columns=["customer_id", "first_name", "last_name", "total_spent"],
        rows=rows,
        row_count=row_count,
    )


def test_summary_with_numbers_from_the_rows_is_kept() -> None:
    summary = "Karl Seal (customer 526) spent the most: $221.55. The top 10 spent between $174.66 and $221.55."
    service = ResponseFormatterService(
        llm_client=FixedSummaryLLMClient(summary),
        settings=SimpleNamespace(openai_api_key=None),
    )

    response = service.format_query_response(
        question="Which 10 customers spent the most in total?",
        generated_sql="SELECT ...",
        execution_result=_ranking_result(),
        used_tables=["public.payment"],
    )

    assert response.answer_summary == summary


def test_summary_with_a_number_not_in_the_result_falls_back_to_the_template() -> None:
    service = ResponseFormatterService(
        llm_client=FixedSummaryLLMClient("Karl Seal spent the most: $221.55, which is 12% more than average."),
        settings=SimpleNamespace(openai_api_key=None),
    )

    response = service.format_query_response(
        question="Which 10 customers spent the most in total?",
        generated_sql="SELECT ...",
        execution_result=_ranking_result(),
        used_tables=["public.payment"],
    )

    assert "12%" not in response.answer_summary
    assert "KARL" in response.answer_summary


def test_summary_prompt_gets_the_row_count_and_up_to_twenty_rows() -> None:
    client = FixedSummaryLLMClient("Karl Seal spent the most: $221.55.")
    service = ResponseFormatterService(llm_client=client, settings=SimpleNamespace(openai_api_key=None))

    service.format_query_response(
        question="Which customers spent the most in total?",
        generated_sql="SELECT ...",
        execution_result=_ranking_result(row_count=30),
        used_tables=["public.payment"],
        assumptions=["“spent” = total of all payments"],
    )

    user_prompt = client.last_messages[1].content
    assert "Result: 30 rows." in user_prompt
    assert "Result rows (the first 20 of 30 rows):" in user_prompt
    assert "- “spent” = total of all payments" in user_prompt


def test_assumptions_are_trimmed_deduplicated_and_capped_at_three() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))

    response = service.format_query_response(
        question="Which customers spent the most in total?",
        generated_sql="SELECT ...",
        execution_result=_ranking_result(),
        used_tables=["public.payment"],
        assumptions=[" all dates ", "all dates", "", "spent = payments", "ties by id", "fourth"],
    )

    assert response.assumptions == ["all dates", "spent = payments", "ties by id"]


def test_empty_result_summary_states_the_data_coverage() -> None:
    service = ResponseFormatterService(settings=SimpleNamespace(openai_api_key=None))
    execution_result = SQLExecutionResult(sql="SELECT ...", success=True, columns=["id"], rows=[], row_count=0)

    response = service.format_query_response(
        question="Show signups from the year 1990.",
        generated_sql="SELECT ...",
        execution_result=execution_result,
        used_tables=["public.signup"],
        data_coverage=["signup created at from 2022-02-14 to 2022-08-23"],
    )

    assert response.answer_summary == (
        "Nothing in the data matched this question. "
        "The data covers signup created at from 2022-02-14 to 2022-08-23."
    )


def test_summary_with_a_date_not_in_the_coverage_falls_back() -> None:
    service = ResponseFormatterService(
        llm_client=FixedSummaryLLMClient("No signups matched 1990. Signups run from 2022-02-15 to 2022-02-23."),
        settings=SimpleNamespace(openai_api_key=None),
    )
    execution_result = SQLExecutionResult(sql="SELECT ...", success=True, columns=["id"], rows=[], row_count=0)

    response = service.format_query_response(
        question="Show signups from the year 1990.",
        generated_sql="SELECT ...",
        execution_result=execution_result,
        used_tables=["public.signup"],
        data_coverage=["signup created at from 2022-02-14 to 2022-08-23"],
    )

    assert "2022-02-15" not in response.answer_summary
    assert "2022-02-14 to 2022-08-23" in response.answer_summary


def test_summary_prompt_gives_extremes_over_all_rows_when_only_some_are_shown() -> None:
    client = FixedSummaryLLMClient("Revenue peaked at 9000 in month 29.")
    service = ResponseFormatterService(llm_client=client, settings=SimpleNamespace(openai_api_key=None))
    rows = [[f"month {index}", Decimal(100 + index)] for index in range(30)]
    rows[29][1] = Decimal("9000")

    service.format_query_response(
        question="How did revenue change by month?",
        generated_sql="SELECT ...",
        execution_result=SQLExecutionResult(
            sql="SELECT ...", success=True, columns=["month", "revenue"], rows=rows, row_count=30
        ),
        used_tables=["public.payment"],
    )

    user_prompt = client.last_messages[1].content
    assert "- revenue highest: 9000 (month 29)" in user_prompt
    assert "- revenue lowest: 100 (month 0)" in user_prompt
