"""Minimal DeepSeek client wrapper using the OpenAI-compatible API."""

import openai

from . import config


def make_client(api_key):
    """Create an OpenAI-compatible client configured for DeepSeek."""
    return openai.OpenAI(api_key=api_key, base_url=config.BASE_URL)


def chat(client, messages, tools=None):
    """Send a chat completion request and return its assistant message."""
    request = {"model": config.MODEL, "messages": messages}
    if tools is not None:
        request["tools"] = tools

    try:
        response = client.chat.completions.create(**request)
    except openai.AuthenticationError as error:
        raise RuntimeError("DeepSeek authentication failed: check your API key.") from error
    except openai.RateLimitError as error:
        raise RuntimeError("DeepSeek rate limit reached; please try again later.") from error
    except openai.APIConnectionError as error:
        raise RuntimeError("Could not connect to DeepSeek; check your network connection.") from error
    except openai.APIError as error:
        raise RuntimeError(f"DeepSeek API request failed: {error}") from error

    return response.choices[0].message
