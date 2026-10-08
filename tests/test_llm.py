from types import SimpleNamespace
from unittest.mock import Mock, patch

import openai
import pytest

from src.code_agent import config
from src.code_agent.llm import chat, make_client


def test_make_client_uses_deepseek_base_url():
    with patch("src.code_agent.llm.openai.OpenAI") as client_class:
        make_client("test-key")

    client_class.assert_called_once_with(api_key="test-key", base_url=config.BASE_URL)


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
