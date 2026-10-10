import json
from datetime import datetime

import pytest

from content_engine.writer import RunOutput, WriterError, slugify

NOW = datetime(2026, 10, 10, 14, 32, 5)


# --- no-overwrite proof tests -------------------------------------------------


def test_two_runs_in_same_second_get_distinct_folders(tmp_path):
    a = RunOutput.create(tmp_path, "article.md", now=NOW)
    b = RunOutput.create(tmp_path, "article.md", now=NOW)
    assert a.path != b.path
    assert a.path.name == "2026-10-10_143205_article"
    assert b.path.name == "2026-10-10_143205_article_2"
    assert a.path.is_dir() and b.path.is_dir()


def test_existing_folder_and_sentinel_are_untouched(tmp_path):
    existing = tmp_path / "2026-10-10_143205_article"
    existing.mkdir()
    sentinel = existing / "linkedin.md"
    sentinel.write_bytes(b"PRECIOUS ORIGINAL")
    before = sentinel.stat()

    run = RunOutput.create(tmp_path, "article.md", now=NOW)
    run.write_text("linkedin.md", "new content")

    assert run.path != existing
    assert sentinel.read_bytes() == b"PRECIOUS ORIGINAL"
    after = sentinel.stat()
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_size == before.st_size
    assert sorted(p.name for p in existing.iterdir()) == ["linkedin.md"]


def test_writing_an_existing_file_raises_and_preserves_it(tmp_path):
    run = RunOutput.create(tmp_path, "article.md", now=NOW)
    target = run.write_text("tweets.md", "original")
    before = target.stat()
    with pytest.raises(FileExistsError):
        run.write_text("tweets.md", "REPLACEMENT")
    assert target.read_text(encoding="utf-8") == "original"
    assert target.stat().st_mtime_ns == before.st_mtime_ns


def test_hundred_rapid_runs_are_all_unique(tmp_path):
    paths = {RunOutput.create(tmp_path, "article.md", now=NOW).path for _ in range(100)}
    assert len(paths) == 100
    assert all(p.is_dir() for p in paths)
    assert len(list(tmp_path.iterdir())) == 100


def test_run_never_modifies_other_existing_runs(tmp_path):
    first = RunOutput.create(tmp_path, "article.md", now=NOW)
    first.write_text("a.md", "one")
    snapshot = {p.name: p.read_bytes() for p in first.path.iterdir()}
    second = RunOutput.create(tmp_path, "article.md", now=NOW)
    second.write_text("a.md", "two")
    assert {p.name: p.read_bytes() for p in first.path.iterdir()} == snapshot


# --- other behaviour ----------------------------------------------------------


def test_creates_missing_outputs_root(tmp_path):
    run = RunOutput.create(tmp_path / "does" / "not" / "exist", "x.md", now=NOW)
    assert run.path.is_dir()


@pytest.mark.parametrize("bad", ["../escape.md", "sub/file.md", "..\\x.md", "", ".", ".."])
def test_rejects_non_plain_filenames(tmp_path, bad):
    run = RunOutput.create(tmp_path, "article.md", now=NOW)
    with pytest.raises(WriterError):
        run.write_text(bad, "x")
    assert not (tmp_path / "escape.md").exists()


def test_write_json_roundtrip_unicode(tmp_path):
    run = RunOutput.create(tmp_path, "article.md", now=NOW)
    p = run.write_json("run_meta.json", {"note": "café — ok"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"note": "café — ok"}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("My Article (final).md", "my-article-final"),
        ("../../etc/passwd", "passwd"),
        ("???.md", "input"),
        ("", "input"),
        ("café notes.txt", "caf-notes"),
        ("a" * 200 + ".md", "a" * 50),
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected
