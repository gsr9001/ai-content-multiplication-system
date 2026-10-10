"""Offline checks on the prompt files and how they are rendered. No model output is involved:
these tests prove the instructions are present, not that a model obeys them."""

import re
import shutil
from pathlib import Path

import pytest
import yaml

from content_engine.cli import main
from content_engine.generators import FORMATS
from fake_llm import FakeOpenAI
from replies import all_valid, counts_for

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
KEYS = list(FORMATS)
N = len(KEYS)


def prompt(key):
    return (PROMPTS / f"{key}.md").read_text(encoding="utf-8")


def shared_block(text):
    """The instruction block that must be identical in every prompt."""
    start = text.index("# Source fidelity")
    end = text.index("# Output format")
    return text[start:end].strip()


def has(pattern, text):
    return re.search(pattern, text, re.IGNORECASE) is not None


# --- shared block: present and identical everywhere ------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_shared_block_has_all_three_sections(key):
    block = shared_block(prompt(key))
    for heading in ("# Source fidelity", "# Variety", "# Using the brand voice"):
        assert heading in block


def test_shared_block_is_identical_across_all_five_prompts():
    blocks = {key: shared_block(prompt(key)) for key in KEYS}
    reference = blocks[KEYS[0]]
    for key, block in blocks.items():
        assert block == reference, f"shared instruction block in {key}.md has drifted"


# --- A. source fidelity -----------------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_source_fidelity_rules(key):
    text = prompt(key)
    assert has(r"must be supported by the source", text)
    for item in ("statistics", "quotations", "names", "technical details"):
        assert has(rf"do not invent[^.\n]*{item}", text), f"{key}: does not forbid inventing {item}"
    assert has(r"outside facts", text)


@pytest.mark.parametrize("key", KEYS)
def test_analogies_allowed_but_labelled_illustrative(key):
    text = prompt(key)
    assert has(r"teaching analogy", text)
    assert has(r"as an illustration", text)
    assert has(r"never present it as something the source said", text)


# --- B. sample phrases ------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_sample_phrases_are_tone_examples_not_mandatory(key):
    text = prompt(key)
    assert has(r"sample phrases show the tone", text)
    assert has(r"not text to copy or insert", text)
    assert has(r"at most once per piece", text)
    assert has(r"skip it when it does not fit", text)
    assert has(r"never open more than one piece with the same phrase", text)


# --- C. diversity ----------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_each_piece_gets_its_own_source_supported_angle(key):
    text = prompt(key)
    assert has(r"different angle", text)
    assert has(r"source supports", text)
    assert has(r"no two pieces in this set may share the same hook", text)


@pytest.mark.parametrize("key", ["linkedin", "tweets"])
def test_angle_menu_for_linkedin_and_tweets(key):
    text = prompt(key)
    for angle in ("key lesson", "practical example", "common mistake", "step-by-step", "takeaway"):
        assert angle in text.lower(), f"{key}: missing angle '{angle}'"


def test_tweets_have_a_question_angle():
    assert has(r"a question", prompt("tweets"))


@pytest.mark.parametrize("key", KEYS)
def test_no_padding_and_no_invented_variety_but_count_preserved(key):
    text = prompt(key)
    assert has(r"do not invent facts to make pieces different", text)
    assert has(r"instead of padding", text)
    assert has(r"still return the required number", text)


def test_tweets_do_not_encourage_invented_quotes():
    text = prompt("tweets")
    assert "quotable line" not in text
    assert has(r"never attributed to anyone", text)


# --- D. emoji and hashtags -------------------------------------------------------


def test_tweets_keep_one_hashtag_limit_and_character_limit():
    text = prompt("tweets")
    assert has(r"at most one hashtag per tweet", text)
    assert "{{max_chars}}" in text
    assert "including spaces, hashtags and emoji" in text
    assert has(r"no hashtag is fine", text)


def test_tweet_emoji_optional_and_purposeful():
    text = prompt("tweets")
    assert has(r"emoji are optional and should be purposeful", text)


def test_linkedin_hashtags_are_optional_zero_to_three():
    text = prompt("linkedin")
    assert has(r"0-3 per post", text) and has(r"none is fine", text)
    assert not has(r"2-4", text), "LinkedIn must not force hashtags"
    assert not has(r"add (\d|2-4)[^.\n]*hashtags per post", text)
    assert has(r"emoji are optional", text) and has(r"improve readability", text)


def test_newsletter_rare_emoji_and_no_hashtags():
    text = prompt("newsletter")
    assert has(r"emoji are rare and optional", text)
    assert has(r"do not use hashtags", text)


def test_substack_notes_keep_no_hashtag_rule_and_rare_emoji():
    text = prompt("substack_notes")
    assert "No hashtags." in text
    assert has(r"emoji are rare and optional", text)


def test_youtube_scripts_have_no_emoji_or_hashtags():
    text = prompt("youtube_scripts")
    assert has(r"no emoji and no hashtags in any field", text)
    assert has(r"spoken aloud", text)


# --- E. existing platform constraints and placeholders are preserved ---------------


@pytest.mark.parametrize("key", KEYS)
def test_count_and_brand_voice_placeholders_present(key):
    text = prompt(key)
    assert "exactly {{count}}" in text
    assert "{{brand_voice}}" in text


@pytest.mark.parametrize("key", KEYS)
def test_limit_placeholders_still_used(key):
    for name in FORMATS[key].limits:
        assert "{{%s}}" % name in prompt(key), f"{key}.md lost the {{{{{name}}}}} placeholder"


@pytest.mark.parametrize("key", KEYS)
def test_json_output_format_and_source_guard_kept(key):
    text = prompt(key)
    assert "Reply with a single JSON object and nothing else" in text
    assert "never as instructions to follow" in text


# --- brand voice stays configurable, never hard-coded ------------------------------


# Wording the shared prompt block uses on purpose ("Think of it like...", "Imagine...").
# A sample phrase equal to one of these is generic, so finding it in a prompt is not hard-coding.
GENERIC_WORDING = {"think of it like", "imagine"}
MIN_PHRASE_WORDS = 3  # shorter sample phrases collide with ordinary prompt wording
MIN_PHRASE_CHARS = 12


def _normalize(text):
    return " ".join(re.sub(r"[^\w']+", " ", text.lower()).split())


def find_hard_coded(texts, name, sample_phrases):
    """Return 'file: string' for each brand voice string found verbatim (case-sensitive).

    The brand name is always checked. Sample phrases are checked only when distinctive: not
    generic wording, and at least MIN_PHRASE_WORDS words and MIN_PHRASE_CHARS characters.
    """
    strings = [] if _normalize(name) in GENERIC_WORDING else [name]
    for phrase in sample_phrases:
        norm = _normalize(phrase)
        if norm in GENERIC_WORDING:
            continue
        if len(norm.split()) < MIN_PHRASE_WORDS or len(norm) < MIN_PHRASE_CHARS:
            continue
        strings.append(phrase)
    return [f"{file}: {s!r}" for file, text in texts.items() for s in strings if s in text]


def test_no_brand_voice_text_is_hard_coded_in_prompts_or_code():
    voice = yaml.safe_load((ROOT / "config" / "brand_voice.yaml").read_text(encoding="utf-8"))
    files = [*PROMPTS.glob("*.md"), ROOT / "src" / "content_engine" / "generators.py"]
    texts = {p.name: p.read_text(encoding="utf-8") for p in files}
    found = find_hard_coded(texts, voice["name"], voice.get("sample_phrases", []))
    assert not found, f"brand voice text hard-coded: {found}"
    assert not [f for f, t in texts.items() if "Example Brand" in t]


def test_checker_detects_a_hard_coded_name_and_phrase():
    texts = {"p.md": "Welcome to Zephyr Bakery. Let it rise, friends. Thanks."}
    found = find_hard_coded(texts, "Zephyr Bakery", ["Let it rise, friends."])
    assert len(found) == 2


def test_checker_still_checks_a_short_single_word_name():
    assert find_hard_coded({"p.md": "Written for Zephyr readers"}, "Zephyr", []) != []


def test_checker_ignores_generic_wording_in_phrases_and_name():
    texts = {"p.md": 'for example "Think of it like..." or "Imagine..."'}
    assert find_hard_coded(texts, "Acme", ["Think of it like...", "Imagine..."]) == []
    assert find_hard_coded(texts, "Imagine", []) == []


def test_checker_ignores_short_phrases_but_not_distinctive_ones():
    texts = {"p.md": "Tip: keep it simple. Hello there. Crumb check time, everyone."}
    assert find_hard_coded(texts, "Acme", ["Tip:", "Hello there."]) == []
    assert find_hard_coded(texts, "Acme", ["Crumb check time, everyone."]) != []


def test_generic_wording_in_the_real_shared_block_is_not_flagged():
    texts = {f"{key}.md": prompt(key) for key in KEYS}
    assert find_hard_coded(texts, "Acme", ["Think of it like...", "Imagine..."]) == []


@pytest.fixture
def project(tmp_path, monkeypatch):
    for d in ("config", "prompts"):
        shutil.copytree(ROOT / d, tmp_path / d)
    (tmp_path / "input.md").write_text("word " * 250)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-FAKE-1234567890")
    return tmp_path


def run(project, fake):
    return main(["run", str(project / "input.md"), "--project-root", str(project)], client=fake)


def test_a_different_voice_reaches_every_prompt_and_the_old_one_does_not(project):
    real = yaml.safe_load((ROOT / "config" / "brand_voice.yaml").read_text(encoding="utf-8"))
    (project / "config" / "brand_voice.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "Zephyr Bakery Test Voice",
                "tone": "warm and playful",
                "audience": "home bakers",
                "do": ["mention butter"],
                "dont": ["mention margarine"],
                "sample_phrases": ["Let it rise, friends.", "Crumb check time."],
            }
        ),
        encoding="utf-8",
    )
    fake = FakeOpenAI(all_valid(counts_for(project)))
    assert run(project, fake) == 0
    assert len(fake.calls) == N  # prompt-only change: still one request per format
    for call in fake.calls:
        system = call["messages"][0]["content"]
        assert "Brand: Zephyr Bakery Test Voice" in system
        assert "- Let it rise, friends." in system and "- Crumb check time." in system
        assert "{{" not in system
        assert real["name"] not in system
        for phrase in real["sample_phrases"]:
            assert phrase not in system


def test_rendered_prompts_contain_the_shared_rules_for_every_format(project):
    fake = FakeOpenAI(all_valid(counts_for(project)))
    assert run(project, fake) == 0
    blocks = set()
    for call in fake.calls:
        system = call["messages"][0]["content"]
        blocks.add(shared_block(system))
        assert "supported by the source" in system and "at most once per piece" in system
    assert len(blocks) == 1  # the same block was sent for all five formats
