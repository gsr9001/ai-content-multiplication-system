"""Turn source text into content. Each format = prompt template + schema + validation retry."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from content_engine.config import BrandVoice, Config
from content_engine.llm import LLMClient
from content_engine.loader import Source
from content_engine.models import (
    LINKEDIN_MAX_CHARS,
    NEWSLETTER_HEADING_MAX_CHARS,
    SUBSTACK_NOTE_MAX_CHARS,
    TWEET_MAX_CHARS,
    YOUTUBE_TITLE_MAX_CHARS,
    LinkedInPosts,
    NewsletterSections,
    SubstackNotes,
    Tweets,
    YouTubeScripts,
)

T = TypeVar("T")


class GenerationError(Exception):
    """Output still invalid after the allowed repair attempts."""


@dataclass
class Generated:
    value: object
    validation_retries: int


def format_brand_voice(voice: BrandVoice) -> str:
    lines = [f"Brand: {voice.name}", f"Tone: {voice.tone}", f"Audience: {voice.audience}"]
    if voice.do:
        lines += ["Do:"] + [f"- {x}" for x in voice.do]
    if voice.dont:
        lines += ["Don't:"] + [f"- {x}" for x in voice.dont]
    if voice.sample_phrases:
        lines += ["Sample phrases:"] + [f"- {x}" for x in voice.sample_phrases]
    return "\n".join(lines)


def render_template(template: str, values: dict[str, str]) -> str:
    """Fill {{name}} placeholders in one pass, so inserted text is never re-scanned."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def load_prompt(prompts_dir: Path, name: str) -> str:
    path = Path(prompts_dir) / f"{name}.md"
    if not path.is_file():
        raise GenerationError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def run_with_repair(
    llm: LLMClient,
    system: str,
    user: str,
    parse: Callable[[str], T],
    max_validation_retries: int,
) -> Generated:
    """Call the LLM; if the reply fails validation, send one repair request per retry allowed."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(max_validation_retries + 1):
        reply = llm.complete_json(messages)
        try:
            return Generated(parse(reply), attempt)
        except (ValueError, ValidationError) as exc:  # json errors and pydantic both subclass ValueError
            if attempt == max_validation_retries:
                raise GenerationError(
                    f"Output was invalid after {attempt + 1} attempt(s): {_short(exc)}"
                ) from None
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"Your reply was invalid: {_short(exc)}. "
                    "Reply again with corrected JSON only, in the required format.",
                },
            ]
    raise AssertionError("unreachable")


def _short(exc: Exception) -> str:
    return " ".join(str(exc).split())[:300]


@dataclass(frozen=True)
class FormatSpec:
    """Everything that makes one content format different from another."""

    key: str  # prompt file name (prompts/<key>.md) and output file name (<key>.md)
    count_attr: str  # which number in settings.yaml `counts:` says how many to make
    schema: type[BaseModel]  # what a valid reply looks like
    items_attr: str  # the list inside the schema holding the pieces
    render: Callable[[BaseModel], str]  # schema -> Markdown file text
    limits: dict[str, str] = field(default_factory=dict)  # extra prompt placeholders


def generate(spec: FormatSpec, source: Source, config: Config, llm: LLMClient, prompts_dir: Path) -> Generated:
    count = getattr(config.settings.counts, spec.count_attr)
    system = render_template(
        load_prompt(prompts_dir, spec.key),
        {"brand_voice": format_brand_voice(config.brand_voice), "count": str(count), **spec.limits},
    )
    user = f"<source>\n{source.text}\n</source>"

    def parse(reply: str) -> BaseModel:
        result = spec.schema.model_validate(json.loads(reply))
        found = len(getattr(result, spec.items_attr))
        if found != count:
            raise ValueError(f"Expected exactly {count} items in '{spec.items_attr}' but got {found}.")
        return result

    return run_with_repair(llm, system, user, parse, config.settings.max_validation_retries)


def _linkedin_markdown(posts: LinkedInPosts) -> str:
    parts = ["# LinkedIn posts\n"]
    for i, post in enumerate(posts.posts, 1):
        tags = " ".join(f"#{t.lstrip('#')}" for t in post.hashtags)
        parts.append(f"## Post {i}\n\n{post.body.strip()}\n" + (f"\n{tags}\n" if tags else ""))
    return "\n".join(parts)


def _tweets_markdown(data: Tweets) -> str:
    parts = ["# Tweets\n"]
    for i, tweet in enumerate(data.tweets, 1):
        parts.append(f"## Tweet {i}\n\n{tweet.text.strip()}\n")
    return "\n".join(parts)


def _newsletter_markdown(data: NewsletterSections) -> str:
    parts = ["# Newsletter sections\n"]
    for i, section in enumerate(data.sections, 1):
        parts.append(f"## Section {i}: {section.heading.strip()}\n\n{section.body.strip()}\n")
    return "\n".join(parts)


def _substack_notes_markdown(data: SubstackNotes) -> str:
    parts = ["# Substack Notes\n"]
    for i, note in enumerate(data.notes, 1):
        parts.append(f"## Note {i}\n\n{note.text.strip()}\n")
    return "\n".join(parts)


def _youtube_scripts_markdown(data: YouTubeScripts) -> str:
    parts = ["# YouTube scripts\n"]
    for i, s in enumerate(data.scripts, 1):
        parts.append(
            f"## Script {i}: {s.title.strip()}\n\n"
            f"**Hook**\n\n{s.hook.strip()}\n\n"
            f"**Script**\n\n{s.body.strip()}\n\n"
            f"**Call to action**\n\n{s.call_to_action.strip()}\n"
        )
    return "\n".join(parts)


# Order here = order of generation = one OpenAI request each.
FORMATS: dict[str, FormatSpec] = {
    "linkedin": FormatSpec(
        "linkedin", "linkedin_posts", LinkedInPosts, "posts", _linkedin_markdown,
        {"max_chars": str(LINKEDIN_MAX_CHARS)},
    ),
    "tweets": FormatSpec(
        "tweets", "tweets", Tweets, "tweets", _tweets_markdown,
        {"max_chars": str(TWEET_MAX_CHARS)},
    ),
    "newsletter": FormatSpec(
        "newsletter", "newsletter_sections", NewsletterSections, "sections", _newsletter_markdown,
        {"max_heading_chars": str(NEWSLETTER_HEADING_MAX_CHARS)},
    ),
    "substack_notes": FormatSpec(
        "substack_notes", "substack_notes", SubstackNotes, "notes", _substack_notes_markdown,
        {"max_chars": str(SUBSTACK_NOTE_MAX_CHARS)},
    ),
    "youtube_scripts": FormatSpec(
        "youtube_scripts", "youtube_scripts", YouTubeScripts, "scripts", _youtube_scripts_markdown,
        {"max_title_chars": str(YOUTUBE_TITLE_MAX_CHARS)},
    ),
}
