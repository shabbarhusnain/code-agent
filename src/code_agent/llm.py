"""Resilient DeepSeek client wrapper using the OpenAI-compatible API."""

import time

import openai

from . import config


REQUEST_TIMEOUT_SECONDS = 120
RETRY_DELAYS = (1, 2, 4)


def make_client(api_key):
    """Create an OpenAI-compatible client configured for DeepSeek."""
    return openai.OpenAI(
        api_key=api_key,
        base_url=config.BASE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _retryable(error):
    if isinstance(error, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)):
        return True
    return isinstance(error, openai.APIStatusError) and (error.status_code or 0) >= 500


def chat(client, messages, tools=None, sleep=time.sleep):
    """Send a chat request, retrying transient DeepSeek failures."""
    request = {"model": config.MODEL, "messages": messages}
    if tools is not None:
        request["tools"] = tools

    for attempt, delay in enumerate((*RETRY_DELAYS, None)):
        try:
            response = client.chat.completions.create(**request)
            return response.choices[0].message
        except openai.AuthenticationError as error:
            raise RuntimeError("Invalid API key") from error
        except openai.APIError as error:
            if isinstance(error, openai.APIStatusError) and error.status_code == 402:
                raise RuntimeError(
                    "DeepSeek reports insufficient balance (HTTP 402). "
                    "Add funds to your DeepSeek account, then retry."
                ) from error
            if not _retryable(error) or delay is None:
                raise RuntimeError(f"DeepSeek API request failed: {error}") from error
            sleep(delay)

    raise RuntimeError("DeepSeek request failed after retries")
