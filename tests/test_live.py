"""Opt-in smoke test against the real OpenAI API. Never runs in ordinary test runs.

Run it deliberately with:  pytest -m live
It needs a real OPENAI_API_KEY in .env or the environment, and costs a few cents.
"""

import shutil
from pathlib import Path

import pytest

from content_engine.cli import main

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.live
def test_one_real_run(tmp_path):
    for d in ("config", "prompts"):
        shutil.copytree(ROOT / d, tmp_path / d)
    if (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env", tmp_path / ".env")
    sample = tmp_path / "sample_article.md"
    shutil.copy(ROOT / "tests" / "fixtures" / "sample_article.md", sample)

    assert main(["run", str(sample), "--project-root", str(tmp_path)]) == 0

    (out,) = (tmp_path / "outputs").iterdir()
    for name in ("linkedin.md", "tweets.md", "newsletter.md", "substack_notes.md",
                 "youtube_scripts.md", "calendar.csv", "calendar.md", "run_meta.json"):
        assert (out / name).exists()
