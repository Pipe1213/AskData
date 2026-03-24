from types import SimpleNamespace

import pytest

from app.llm.base import LLMClientError
from app.llm.openai_client import OpenAILLMClient
from app.llm.response_models import LLMGenerationConfig


def test_extract_text_falls_back_to_message_content() -> None:
    client = OpenAILLMClient.__new__(OpenAILLMClient)
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(type="reasoning", content=None),
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(type="output_text", text='{"sql":"SELECT 1;"}'),
                ],
            ),
        ],
    )

    extracted = client._extract_text(response)

    assert extracted == '{"sql":"SELECT 1;"}'


def test_extract_text_raises_incomplete_reason() -> None:
    client = OpenAILLMClient.__new__(OpenAILLMClient)
    response = SimpleNamespace(
        output_text="",
        output=[],
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )

    with pytest.raises(LLMClientError, match="incomplete: max_output_tokens"):
        client._extract_text(response)


def test_build_generation_kwargs_omits_temperature_by_default() -> None:
    client = OpenAILLMClient.__new__(OpenAILLMClient)

    kwargs = client._build_generation_kwargs(LLMGenerationConfig(max_output_tokens=2500))

    assert kwargs == {"max_output_tokens": 2500}
