from types import SimpleNamespace
from unittest.mock import Mock, patch

import openai
import pytest

from src.code_agent import config
from src.code_agent.llm import chat, make_client


def test_config_uses_official_deepseek_v4_pro_model():
    assert config.BASE_URL == "https://api.deepseek.com"
    assert config.MODEL == "deepseek-v4-pro"


def test_make_client_uses_deepseek_base_url():
    with patch("src.code_agent.llm.openai.OpenAI") as client_class:
        make_client("test-key")

    client_class.assert_called_once_with(
        api_key="test-key", base_url=config.BASE_URL, timeout=120
    )


def test_chat_returns_message_from_mocked_response():
    message = SimpleNamespace(content="Hello")
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message)]
    )

    assert chat(client, [{"role": "user", "content": "Hi"}]) is message
    client.chat.completions.create.assert_called_once_with(
        model=config.MODEL, messages=[{"role": "user", "content": "Hi"}]
    )


def test_chat_wraps_openai_api_errors_as_runtime_errors():
    client = Mock()
    client.chat.completions.create.side_effect = openai.APIError(
        "service unavailable", request=Mock(), body=None
    )

    with pytest.raises(RuntimeError, match="DeepSeek API request failed"):
        chat(client, [])


def test_chat_explains_insufficient_balance_without_retrying():
    client = Mock()
    client.chat.completions.create.side_effect = openai.APIStatusError(
        "Insufficient Balance",
        response=Mock(status_code=402),
        body={"error": {"message": "Insufficient Balance"}},
    )

    with pytest.raises(RuntimeError, match="insufficient balance.*Add funds"):
        chat(client, [], sleep=lambda _: pytest.fail("should not retry"))
    assert client.chat.completions.create.call_count == 1


def test_chat_retries_transient_failures_and_succeeds_on_third_attempt():
    message = SimpleNamespace(content="recovered")
    client = Mock()
    client.chat.completions.create.side_effect = [
        openai.APIConnectionError(request=Mock()),
        openai.APIConnectionError(request=Mock()),
        SimpleNamespace(choices=[SimpleNamespace(message=message)]),
    ]
    delays = []

    assert chat(client, [], sleep=delays.append) is message
    assert client.chat.completions.create.call_count == 3
    assert delays == [1, 2]


def test_chat_does_not_retry_invalid_api_key():
    client = Mock()
    client.chat.completions.create.side_effect = openai.AuthenticationError(
        "bad key", response=Mock(), body=None
    )

    with pytest.raises(RuntimeError, match="^Invalid API key$"):
        chat(client, [], sleep=lambda _: pytest.fail("should not retry"))
    assert client.chat.completions.create.call_count == 1
