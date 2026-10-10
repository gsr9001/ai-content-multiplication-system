import httpx2
import openai
import pytest

from content_engine.config import Secret
from content_engine.llm import LLMClient, LLMError
from fake_llm import FakeOpenAI

KEY = "sk-test-FAKE-1234567890"


def _resp(status):
    return httpx2.Response(status, request=httpx2.Request("POST", "https://example.invalid"))


def rate_limit():
    return openai.RateLimitError(f"too fast, key {KEY}", response=_resp(429), body=None)


def make(script, retries=3):
    sleeps = []
    fake = FakeOpenAI(script)
    llm = LLMClient(Secret(KEY), "m", 0.5, retries, client=fake, sleep=sleeps.append)
    return llm, fake, sleeps


MSGS = [{"role": "user", "content": "hi"}]


def test_success_sends_json_mode_request():
    llm, fake, _ = make(['{"a": 1}'])
    assert llm.complete_json(MSGS) == '{"a": 1}'
    assert llm.requests == 1 and llm.transport_retries == 0
    call = fake.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == "m" and call["temperature"] == 0.5


def test_retries_rate_limit_with_backoff_then_succeeds():
    llm, fake, sleeps = make([rate_limit(), rate_limit(), "ok"])
    assert llm.complete_json(MSGS) == "ok"
    assert llm.requests == 3 and llm.transport_retries == 2
    assert sleeps == [1, 2]


def test_gives_up_after_max_retries_without_leaking_key():
    llm, _, sleeps = make([rate_limit()] * 4, retries=3)
    with pytest.raises(LLMError) as exc:
        llm.complete_json(MSGS)
    assert llm.requests == 4 and len(sleeps) == 3
    assert "RateLimitError" in str(exc.value)
    assert KEY not in str(exc.value)


def test_timeout_and_connection_errors_are_retried():
    req = httpx2.Request("POST", "https://example.invalid")
    llm, _, _ = make([openai.APITimeoutError(req), openai.APIConnectionError(request=req), "ok"])
    assert llm.complete_json(MSGS) == "ok"


def test_auth_error_is_not_retried_and_does_not_leak():
    err = openai.AuthenticationError(f"bad key {KEY}", response=_resp(401), body=None)
    llm, _, sleeps = make([err])
    with pytest.raises(LLMError) as exc:
        llm.complete_json(MSGS)
    assert llm.requests == 1 and sleeps == []
    assert "HTTP 401" in str(exc.value) and KEY not in str(exc.value)


def test_empty_reply_is_an_error():
    llm, _, _ = make([""])
    with pytest.raises(LLMError, match="empty"):
        llm.complete_json(MSGS)
