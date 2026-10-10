"""The ONLY module that talks to OpenAI. Handles transport retries and counts requests."""

import time
from collections.abc import Callable

import openai

from content_engine.config import Secret

# Temporary failures worth retrying. Anything else (bad key, bad request) fails immediately.
RETRYABLE = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
MAX_BACKOFF_SECONDS = 30


class LLMError(Exception):
    """An OpenAI call failed. Messages never include the API key or raw server text."""


def _describe(exc: Exception) -> str:
    # Deliberately not str(exc): OpenAI messages can echo part of an API key.
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


class LLMClient:
    def __init__(
        self,
        api_key: Secret,
        model: str,
        temperature: float,
        max_transport_retries: int,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # max_retries=0: we do our own retries so they are counted and visible.
        self._client = client or openai.OpenAI(api_key=api_key.reveal(), max_retries=0)
        self._model = model
        self._temperature = temperature
        self._max_retries = max_transport_retries
        self._sleep = sleep
        self.requests = 0  # every request sent, including retried ones
        self.transport_retries = 0

    def complete_json(self, messages: list[dict[str, str]]) -> str:
        """Send chat messages, ask for a JSON object, return the reply text."""
        for attempt in range(self._max_retries + 1):
            self.requests += 1
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=self._temperature,
                    response_format={"type": "json_object"},
                )
            except RETRYABLE as exc:
                if attempt == self._max_retries:
                    raise LLMError(
                        f"OpenAI request failed after {attempt + 1} attempts: {_describe(exc)}"
                    ) from None
                self.transport_retries += 1
                self._sleep(min(2**attempt, MAX_BACKOFF_SECONDS))
                continue
            except openai.OpenAIError as exc:
                raise LLMError(f"OpenAI request failed: {_describe(exc)}") from None
            content = resp.choices[0].message.content
            if not content:
                raise LLMError("OpenAI returned an empty response.")
            return content
        raise AssertionError("unreachable")
