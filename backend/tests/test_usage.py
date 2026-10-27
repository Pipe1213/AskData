from types import SimpleNamespace

import pytest

from app.llm.openai_client import OpenAILLMClient
from app.llm.response_models import LLMMessage
from app.llm.usage import UsageMeter, record_llm_usage, track_llm_usage

PRICES = {"sql-model": (2.00, 0.10, 10.00)}


def _openai_usage(input_tokens: int, output_tokens: int, cached: int = 0, reasoning: int = 0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


def test_usage_meter_prices_uncached_cached_and_output_tokens() -> None:
    meter = UsageMeter(prices=PRICES)

    meter.record("sql-model", input_tokens=1_000, output_tokens=200, cached_input_tokens=400, reasoning_tokens=50)
    meter.record("sql-model", input_tokens=500, output_tokens=100)

    usage = meter.summary()
    assert usage.llm_calls == 2
    assert usage.input_tokens == 1_500
    assert usage.cached_input_tokens == 400
    assert usage.output_tokens == 300
    assert usage.reasoning_tokens == 50
    # (600 + 500) * $2 + 400 * $0.10 + 300 * $10, per 1M tokens
    assert usage.cost_usd == pytest.approx((1_100 * 2.00 + 400 * 0.10 + 300 * 10.00) / 1_000_000)


def test_usage_meter_reports_no_cost_when_a_model_has_no_price() -> None:
    meter = UsageMeter(prices=PRICES)

    meter.record("sql-model", input_tokens=100, output_tokens=10)
    meter.record("unknown-model", input_tokens=100, output_tokens=10)

    usage = meter.summary()
    assert usage.llm_calls == 2
    assert usage.cost_usd is None
    assert usage.unpriced_models == ["unknown-model"]


def test_record_llm_usage_only_counts_inside_a_tracked_request() -> None:
    record_llm_usage("gpt-5.1", _openai_usage(100, 10))

    with track_llm_usage() as meter:
        record_llm_usage("gpt-5.1", _openai_usage(700, 160, cached=0, reasoning=0))
        record_llm_usage("gpt-5.1", None)

    record_llm_usage("gpt-5.1", _openai_usage(100, 10))

    usage = meter.summary()
    assert usage.llm_calls == 1
    assert usage.input_tokens == 700
    assert usage.output_tokens == 160


def test_openai_client_records_usage_even_when_output_is_unusable() -> None:
    responses = [
        SimpleNamespace(output_text="The top customer spent 221.55.", usage=_openai_usage(300, 40)),
        SimpleNamespace(
            output_text="",
            output=[],
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            usage=_openai_usage(300, 128, reasoning=128),
        ),
    ]
    client = OpenAILLMClient.__new__(OpenAILLMClient)
    client.model = "gpt-5-mini"
    client.client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: responses.pop(0)),
    )
    messages = [LLMMessage(role="user", content="Summarize.")]

    with track_llm_usage() as meter:
        client.generate_text(messages)
        with pytest.raises(Exception, match="incomplete"):
            client.generate_text(messages)

    usage = meter.summary()
    assert usage.llm_calls == 2
    assert usage.output_tokens == 168
    assert usage.reasoning_tokens == 128
    assert usage.cost_usd is not None
