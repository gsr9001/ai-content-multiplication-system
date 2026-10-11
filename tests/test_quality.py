"""Offline tests for the style lint. No model output is involved."""

import pytest

from content_engine.generators import FORMATS
from content_engine.quality import RULES, count_emoji, lint

GRIN = "\U0001F600"


def tweets(*texts):
    return [{"text": x} for x in texts]


def test_every_registered_format_has_rules():
    assert set(RULES) == set(FORMATS)


def test_clean_text_passes():
    assert lint("tweets", tweets("Start with one small input.", "A second, different idea.")) == []


@pytest.mark.parametrize(
    "text",
    [
        "Use **bold** here",
        "Use `code` here",
        "# Heading\nbody",
        "- item one\n- item two",
        "> quoted",
        "[x](http://a.b)",
    ],
)
def test_markdown_artifacts_are_flagged(text):
    assert any("Markdown" in i for i in lint("tweets", tweets(text)))


def test_hashtag_is_not_mistaken_for_a_heading():
    assert lint("instagram_captions", [{"text": "Nice caption.\n#python #ai"}]) == []


def test_numbered_steps_are_allowed():
    assert lint("linkedin", [{"body": "Steps:\n1. Read\n2. Try"}]) == []


def test_exclamation_limit():
    assert lint("linkedin", [{"body": "Good! Very good."}]) == []
    assert any("exclamation" in i for i in lint("linkedin", [{"body": "Wow! Great! Yes."}]))


def test_youtube_allows_no_exclamation_emoji_or_hashtag():
    base = {"title": "T", "hook": "Hello", "body": "b", "call_to_action": "c"}
    assert any("exclamation" in i for i in lint("youtube_scripts", [{**base, "hook": "Hello!"}]))
    assert any("emoji" in i for i in lint("youtube_scripts", [{**base, "hook": f"Hello {GRIN}"}]))
    assert any("hashtag" in i for i in lint("youtube_scripts", [{**base, "body": "try #python"}]))


def test_too_many_emoji_flagged():
    assert any("emoji" in i for i in lint("tweets", tweets(f"a {GRIN}{GRIN}{GRIN}")))


def test_hashtags_allowed_in_tweet_text_but_not_in_notes():
    assert lint("tweets", tweets("Learn this #python")) == []
    assert any("hashtag" in i for i in lint("substack_notes", [{"text": "Learn this #python"}]))


def test_duplicate_openings_flagged_regardless_of_case_and_punctuation():
    issues = lint("tweets", tweets("Here's the simple version: A.", "here's the simple version, B."))
    assert any("start with the same words" in i for i in issues)


def test_issue_list_is_capped():
    assert len(lint("tweets", tweets(*["**x** `y` # z"] * 10))) <= 5


def test_unknown_key_is_ignored():
    assert lint("nope", tweets("**x**")) == []


# --- emoji counting: one visible emoji sequence = one ------------------------------

HEART = "\u2764\N{VARIATION SELECTOR-16}"  # red heart + variation selector
THUMB_TONE = "\U0001F44D\U0001F3FD"  # thumbs up + medium skin tone
WOMAN_TECH = "\U0001F469\N{ZERO WIDTH JOINER}\U0001F4BB"  # woman + ZWJ + laptop
FAMILY = "\U0001F468\N{ZERO WIDTH JOINER}\U0001F469\N{ZERO WIDTH JOINER}\U0001F467"  # man + woman + girl joined
RAINBOW_FLAG = "\U0001F3F3\N{VARIATION SELECTOR-16}\N{ZERO WIDTH JOINER}\U0001F308"  # white flag + VS16 + ZWJ + rainbow
RUNNER = "\U0001F3C3\U0001F3FD\N{ZERO WIDTH JOINER}\u2640\N{VARIATION SELECTOR-16}"  # runner + tone + ZWJ + female sign + VS16
KEYCAP_ONE = "1\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}"
FLAG_IN = "\U0001F1EE\U0001F1F3"  # two regional indicators


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", 0),
        ("plain text, no emoji", 0),
        (GRIN, 1),
        (HEART, 1),
        (THUMB_TONE, 1),
        (WOMAN_TECH, 1),
        (FAMILY, 1),
        (RAINBOW_FLAG, 1),
        (RUNNER, 1),
        (KEYCAP_ONE, 1),
        (FLAG_IN, 1),
        (GRIN + GRIN, 2),
        (HEART + HEART, 2),
        (f"a {HEART} b {THUMB_TONE} c {FAMILY}", 3),
        (WOMAN_TECH + WOMAN_TECH, 2),
    ],
)
def test_emoji_sequences_count_once(text, expected):
    assert count_emoji(text) == expected


@pytest.mark.parametrize("text", ["\N{VARIATION SELECTOR-16}", "\N{ZERO WIDTH JOINER}", "\U0001F3FD", "\U0001F1EE", "\N{COMBINING ENCLOSING KEYCAP}", "1", "#", "*"])
def test_stray_modifiers_and_joiners_do_not_count(text):
    assert count_emoji(text) == 0


@pytest.mark.parametrize("symbol", "\u2705\u274C\u2B50\u26A1\u2728\u2757\u2753")
def test_default_emoji_symbols_count_without_variation_selector(symbol):
    assert count_emoji(symbol) == 1
    assert count_emoji(symbol + "\N{VARIATION SELECTOR-16}") == 1


@pytest.mark.parametrize("symbol", ["\u2713", "\u2192", "\u2022", "\u2605", "\u2122", "\u00A9", "\u2714", "\u27A1"])
def test_plain_typography_symbols_do_not_count(symbol):
    assert count_emoji(symbol) == 0


@pytest.mark.parametrize("symbol", ["\u2714", "\u27A1", "\u2122", "\u2605"])
def test_bmp_symbols_count_when_followed_by_variation_selector(symbol):
    assert count_emoji(symbol + "\N{VARIATION SELECTOR-16}") == 1


def test_one_heart_is_within_every_nonzero_limit_and_two_are_not_for_newsletter():
    assert lint("tweets", tweets(f"Nice {HEART}")) == []
    assert lint("tweets", tweets(f"Nice {HEART}{HEART}")) == []
    assert any("emoji" in i for i in lint("tweets", tweets(f"Nice {HEART}{HEART}{HEART}")))
    assert lint("newsletter", [{"heading": "H", "body": f"Nice {HEART}"}]) == []
    assert any("emoji" in i for i in lint("newsletter", [{"heading": "H", "body": f"Nice {HEART}{HEART}"}]))


def test_zwj_and_skin_tone_sequences_count_once_against_the_limit():
    assert lint("substack_notes", [{"text": f"Nice {WOMAN_TECH}"}]) == []
    assert lint("linkedin", [{"body": f"A {FAMILY} B {THUMB_TONE}"}]) == []


def test_any_emoji_fails_youtube_but_typography_does_not():
    base = {"title": "T", "hook": "Hello", "body": "b", "call_to_action": "c"}
    assert any("emoji" in i for i in lint("youtube_scripts", [{**base, "body": f"b {HEART}"}]))
    assert lint("youtube_scripts", [{**base, "body": "step 1 \u2192 step 2 \u2713"}]) == []


# --- cross-format repeated wording -------------------------------------------------

from content_engine.quality import repeated_text  # noqa: E402

LONG = "start with one small example and then change one thing at a time to see the result"


def test_copied_wording_across_formats_is_reported():
    found = repeated_text([("linkedin/Post 1", LONG), ("tweets/Tweet 1", LONG + " today")])
    assert found and "linkedin/Post 1" in found[0] and "tweets/Tweet 1" in found[0]


def test_same_format_pairs_and_short_pieces_are_ignored():
    assert repeated_text([("tweets/Tweet 1", LONG), ("tweets/Tweet 2", LONG)]) == []
    assert repeated_text([("linkedin/Post 1", "short text"), ("tweets/Tweet 1", "short text")]) == []


def test_different_wording_is_not_reported():
    other = "a completely different sentence about calendars and scheduling posts across two weeks"
    assert repeated_text([("linkedin/Post 1", LONG), ("tweets/Tweet 1", other)]) == []
