"""Valid canned model replies for each format.

The number of items follows the active project's configured counts, so tests stay correct
when `config/settings.yaml` changes. With no counts given, the built-in defaults are used.
"""

import json
from pathlib import Path

from content_engine.config import Counts, load_config
from content_engine.generators import FORMATS


def _linkedin(n):
    return {"posts": [{"body": f"Post number {i} body.", "hashtags": ["ai", "#content"]} for i in range(n)]}


def _tweets(n):
    return {"tweets": [{"text": f"Tweet number {i}."} for i in range(n)]}


def _newsletter(n):
    return {"sections": [{"heading": f"Heading {i}", "body": f"Section {i} body."} for i in range(n)]}


def _substack_notes(n):
    return {"notes": [{"text": f"Note number {i}."} for i in range(n)]}


def _youtube_scripts(n):
    return {
        "scripts": [
            {
                "title": f"Video {i}",
                "hook": "Hook line.",
                "body": f"Script {i} body.",
                "call_to_action": "Subscribe.",
            }
            for i in range(n)
        ]
    }


BUILDERS = {
    "linkedin": _linkedin,
    "tweets": _tweets,
    "newsletter": _newsletter,
    "substack_notes": _substack_notes,
    "youtube_scripts": _youtube_scripts,
}


def counts_for(project: Path) -> Counts:
    """The content counts configured in this test project's own settings.yaml."""
    return load_config(project, env={"OPENAI_API_KEY": "sk-test-not-used"}).settings.counts


def count_of(key: str, counts: Counts | None = None) -> int:
    """How many items `key` should produce under `counts` (defaults if None)."""
    return getattr(counts or Counts(), FORMATS[key].count_attr)


def valid(key, n=None, counts=None):
    """JSON reply text for one format. `n` overrides the item count; else use `counts`."""
    return json.dumps(BUILDERS[key](count_of(key, counts) if n is None else n))


def all_valid(counts=None):
    """One valid reply per registered format, in generation order."""
    return [valid(key, counts=counts) for key in FORMATS]
