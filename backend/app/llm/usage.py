import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.core.config import OPENAI_PRICES_PER_MILLION_TOKENS
from app.schemas.query import QueryUsage

logger = logging.getLogger(__name__)


class UsageMeter:
    """Adds up token usage and cost of the LLM calls made while answering one request."""

    def __init__(self, prices: dict[str, tuple[float, float, float]] | None = None) -> None:
        self.prices = prices if prices is not None else OPENAI_PRICES_PER_MILLION_TOKENS
        self.llm_calls = 0
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.cost_usd = 0.0
        self.unpriced_models: set[str] = set()

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> None:
        self.llm_calls += 1
        self.input_tokens += input_tokens
        self.cached_input_tokens += cached_input_tokens
        self.output_tokens += output_tokens
        self.reasoning_tokens += reasoning_tokens

        prices = self.prices.get(model)
        if prices is None:
            self.unpriced_models.add(model)
            return

        input_price, cached_input_price, output_price = prices
        uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
        self.cost_usd += (
            uncached_input_tokens * input_price
            + cached_input_tokens * cached_input_price
            + output_tokens * output_price
        ) / 1_000_000

    def summary(self) -> QueryUsage:
        return QueryUsage(
            llm_calls=self.llm_calls,
            input_tokens=self.input_tokens,
            cached_input_tokens=self.cached_input_tokens,
            output_tokens=self.output_tokens,
            reasoning_tokens=self.reasoning_tokens,
            cost_usd=None if self.unpriced_models else round(self.cost_usd, 6),
            unpriced_models=sorted(self.unpriced_models),
        )


_active_meter: ContextVar[UsageMeter | None] = ContextVar("askdata_usage_meter", default=None)


@contextmanager
def track_llm_usage() -> Iterator[UsageMeter]:
    meter = UsageMeter()
    token = _active_meter.set(meter)
    try:
        yield meter
    finally:
        _active_meter.reset(token)


def record_llm_usage(model: str, usage: object | None) -> None:
    """Record one OpenAI response's `usage` on the meter of the current request, if any."""
    meter = _active_meter.get()
    if meter is None or usage is None:
        return

    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    meter.record(
        model=model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
        reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
    )


def log_usage(usage: QueryUsage) -> None:
    logger.info(
        "LLM usage: calls=%d input_tokens=%d cached_input_tokens=%d output_tokens=%d "
        "reasoning_tokens=%d cost_usd=%s",
        usage.llm_calls,
        usage.input_tokens,
        usage.cached_input_tokens,
        usage.output_tokens,
        usage.reasoning_tokens,
        usage.cost_usd,
    )
    if usage.unpriced_models:
        logger.warning("No price configured for models: %s", ", ".join(usage.unpriced_models))
