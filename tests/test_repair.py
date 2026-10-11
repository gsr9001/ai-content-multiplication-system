"""Offline tests for run_with_repair: style repair must never lose content that was already valid."""

import json

import pytest

from content_engine.generators import (
    REPAIR_FAILED_NOTE,
    REPAIR_INVALID_NOTE,
    GenerationError,
    run_with_repair,
)
from content_engine.llm import LLMError

MAX_LEN = 10
COUNT = 2


class StubLLM:
    """Scripted replies: each item is reply text or an exception to raise."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = 0

    def complete_json(self, messages):
        self.requests += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def parse(reply):
    """Stands in for schema + item-count + hard-limit validation."""
    items = json.loads(reply)  # json errors are ValueError
    if len(items) != COUNT:
        raise ValueError(f"Expected exactly {COUNT} items but got {len(items)}.")
    if any(len(x) > MAX_LEN for x in items):
        raise ValueError("an item is over the length limit")
    return items


def style_check(items):
    return ["has an exclamation mark"] if any("!" in x for x in items) else []


def reply(*items):
    return json.dumps(list(items))


BAD = reply("one!", "two")  # valid, but breaks a style rule
BAD_B = reply("three!", "four")  # a different valid reply that also breaks the style rule
CLEAN = reply("fine", "also fine")
ISSUE = "has an exclamation mark"


def run(script, retries=1):
    llm = StubLLM(script)
    return run_with_repair(llm, "system", "user", parse, retries, style_check), llm


# --- style failure, then a bad repair reply: keep the earlier valid reply -------------


@pytest.mark.parametrize(
    "repair",
    [
        "not json at all",
        reply("only one"),  # wrong item count
        reply("x" * (MAX_LEN + 1), "ok"),  # over a hard length limit
        reply("fine!", "x" * (MAX_LEN + 1)),  # over the limit AND a style issue: still never saved
    ],
    ids=["invalid-json", "wrong-count", "over-limit", "over-limit-and-style"],
)
def test_invalid_repair_reply_falls_back_to_the_earlier_valid_reply(repair):
    result, llm = run([BAD, repair])
    assert result.value == ["one!", "two"]
    assert result.warnings == [ISSUE, REPAIR_INVALID_NOTE]
    assert result.validation_retries == 1
    assert llm.requests == 2


def test_transport_failure_during_repair_falls_back_with_a_clear_warning():
    result, llm = run([BAD, LLMError("OpenAI request failed: boom")])
    assert result.value == ["one!", "two"]
    assert result.warnings == [ISSUE, REPAIR_FAILED_NOTE]
    assert result.validation_retries == 1
    assert llm.requests == 2


# --- no valid fallback: current error behaviour is preserved ---------------------------


def test_two_invalid_replies_still_raise():
    with pytest.raises(GenerationError, match="invalid after 2 attempt"):
        run(["nope", "still nope"])


def test_transport_failure_on_the_first_request_still_raises():
    with pytest.raises(LLMError):
        run([LLMError("boom")])


def test_transport_failure_after_only_invalid_replies_still_raises():
    with pytest.raises(LLMError):
        run(["nope", LLMError("boom")])


def test_invalid_reply_then_style_bad_reply_is_kept_with_its_warnings():
    result, _ = run(["nope", BAD])
    assert result.value == ["one!", "two"]
    assert result.warnings == [ISSUE]


# --- unchanged happy paths ---------------------------------------------------------------


def test_clean_reply_has_no_warnings_and_one_request():
    result, llm = run([CLEAN])
    assert result.value == ["fine", "also fine"] and result.warnings == []
    assert result.validation_retries == 0 and llm.requests == 1


def test_style_failure_then_clean_repair_returns_the_clean_reply():
    result, llm = run([BAD, CLEAN])
    assert result.value == ["fine", "also fine"] and result.warnings == []
    assert result.validation_retries == 1 and llm.requests == 2


def test_style_failure_then_style_failure_keeps_the_repair_reply_with_its_own_warnings():
    result, llm = run([BAD, BAD_B])
    assert result.value == ["three!", "four"]
    assert result.warnings == [ISSUE]  # no fallback note: this reply is itself valid
    assert llm.requests == 2


# --- max_validation_retries = 0 ----------------------------------------------------------


def test_zero_retries_keeps_a_style_bad_valid_reply_with_a_warning():
    result, llm = run([BAD], retries=0)
    assert result.value == ["one!", "two"] and result.warnings == [ISSUE]
    assert result.validation_retries == 0 and llm.requests == 1


def test_zero_retries_invalid_reply_raises():
    with pytest.raises(GenerationError, match="invalid after 1 attempt"):
        run(["nope"], retries=0)


def test_zero_retries_transport_failure_raises():
    with pytest.raises(LLMError):
        run([LLMError("boom")], retries=0)


# --- more than one repair allowed ----------------------------------------------------------


def test_most_recent_valid_reply_is_the_fallback():
    result, llm = run([BAD, BAD_B, "nope"], retries=2)
    assert result.value == ["three!", "four"]  # not the older valid reply
    assert result.warnings == [ISSUE, REPAIR_INVALID_NOTE]
    assert result.validation_retries == 2 and llm.requests == 3


def test_fallback_survives_two_bad_repairs():
    result, llm = run([BAD, "nope", reply("only one")], retries=2)
    assert result.value == ["one!", "two"]
    assert result.warnings == [ISSUE, REPAIR_INVALID_NOTE]
    assert llm.requests == 3


def test_a_later_valid_reply_replaces_the_fallback():
    result, _ = run([BAD, "nope", CLEAN], retries=2)
    assert result.value == ["fine", "also fine"] and result.warnings == []


def test_a_later_valid_style_bad_reply_is_returned_not_the_older_fallback():
    result, _ = run([BAD, "nope", BAD_B], retries=2)
    assert result.value == ["three!", "four"] and result.warnings == [ISSUE]


def test_transport_failure_on_a_later_repair_keeps_the_latest_valid_reply():
    result, llm = run([BAD, BAD_B, LLMError("boom")], retries=2)
    assert result.value == ["three!", "four"]
    assert result.warnings == [ISSUE, REPAIR_FAILED_NOTE]
    assert llm.requests == 3
