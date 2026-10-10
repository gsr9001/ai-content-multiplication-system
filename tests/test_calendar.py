import csv
import io
import json
import shutil
import socket
from datetime import date
from pathlib import Path

import pytest

from content_engine.calendar import (
    CHANNELS,
    build_calendar,
    calendar_csv,
    calendar_markdown,
    next_monday,
)
from content_engine.cli import main
from content_engine.generators import FORMATS
from fake_llm import FakeOpenAI
from replies import all_valid, count_of, counts_for, valid

MONDAY = date(2026, 10, 12)
ROOT = Path(__file__).resolve().parent.parent


def results(keys=None):
    keys = keys or list(FORMATS)
    return {k: FORMATS[k].schema.model_validate(json.loads(valid(k))) for k in keys}


def test_one_entry_per_piece():
    entries = build_calendar(results(), MONDAY)
    assert len(entries) == 5 + 10 + 3 + 3 + 2
    by_file = {}
    for e in entries:
        by_file[e.file] = by_file.get(e.file, 0) + 1
    assert by_file == {
        "linkedin.md": 5, "tweets.md": 10, "newsletter.md": 3, "substack_notes.md": 3,
        "youtube_scripts.md": 2,
    }


def test_deterministic_and_makes_no_network_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("calendar must not use the network")

    monkeypatch.setattr(socket.socket, "connect", boom)
    assert build_calendar(results(), MONDAY) == build_calendar(results(), MONDAY)


def test_all_entries_are_weekdays_within_two_weeks_and_sorted():
    entries = build_calendar(results(), MONDAY)
    assert all(e.day.weekday() < 5 for e in entries)
    assert all(0 <= (e.day - MONDAY).days < 14 for e in entries)
    assert [(e.day, e.time) for e in entries] == sorted((e.day, e.time) for e in entries)


def test_pieces_stay_in_order_within_a_format():
    entries = build_calendar(results(), MONDAY)
    for file in {e.file for e in entries}:
        pieces = [e.piece for e in entries if e.file == file]
        numbers = [int(p.split()[1].rstrip(":")) for p in pieces]
        assert numbers == sorted(numbers)


def test_pieces_are_spread_not_bunched():
    posts = [e.day for e in build_calendar(results(["linkedin"]), MONDAY)]
    assert len(set(posts)) == 5
    assert posts[0] == MONDAY and posts[-1] >= date(2026, 10, 19)


def test_only_successful_formats_appear():
    entries = build_calendar(results(["tweets"]), MONDAY)
    assert {e.platform for e in entries} == {"X/Twitter"}
    assert build_calendar({}, MONDAY) == []


def test_start_on_a_non_monday_still_works():
    entries = build_calendar(results(), date(2026, 10, 10))  # a Saturday
    assert len(entries) == 23 and all(e.day.weekday() < 5 for e in entries)
    assert all(0 <= (e.day - date(2026, 10, 10)).days < 14 for e in entries)


def test_more_pieces_than_days_cycle_through_times():
    r = results(["tweets"])
    r["tweets"] = r["tweets"].model_copy(
        update={"tweets": r["tweets"].tweets * 3}  # 30 tweets over 10 weekdays
    )
    entries = build_calendar(r, MONDAY)
    first_day = [e.time for e in entries if e.day == MONDAY]
    assert first_day == list(CHANNELS["tweets"].times)


@pytest.mark.parametrize(
    "today,expected",
    [(date(2026, 10, 10), date(2026, 10, 12)), (date(2026, 10, 12), date(2026, 10, 19)),
     (date(2026, 10, 11), date(2026, 10, 12))],
)
def test_next_monday_is_strictly_after_today(today, expected):
    assert next_monday(today) == expected and expected.weekday() == 0


def test_csv_is_parseable_and_formula_safe():
    r = results(["tweets"])
    r["tweets"].tweets[0].text = '=HYPERLINK("http://x"), "quoted", comma'
    rows = list(csv.DictReader(io.StringIO(calendar_csv(build_calendar(r, MONDAY)))))
    assert len(rows) == 10
    assert rows[0]["platform"] == "X/Twitter" and rows[0]["date"] == "2026-10-12"
    assert rows[0]["preview"].startswith("'=HYPERLINK")


def test_preview_is_truncated_and_flattened():
    r = results(["linkedin"])
    r["linkedin"].posts[0].body = "line one\n\nline two " + "x" * 200
    entry = build_calendar(r, MONDAY)[0]
    assert len(entry.preview) == 80 and entry.preview.endswith("…")
    assert "\n" not in entry.preview


def test_markdown_groups_by_week_and_escapes_pipes():
    r = results()
    r["linkedin"].posts[0].body = "a | b"
    md = calendar_markdown(build_calendar(r, MONDAY), MONDAY)
    assert "## Week 1" in md and "## Week 2" in md and "a \\| b" in md
    assert "local time zone" in md


# --- through the CLI ------------------------------------------------------------


@pytest.fixture
def project(tmp_path, monkeypatch):
    for d in ("config", "prompts"):
        shutil.copytree(ROOT / d, tmp_path / d)
    (tmp_path / "input.md").write_text("word " * 250)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-FAKE-1234567890")
    return tmp_path


def run(project, fake, *extra):
    return main(["run", str(project / "input.md"), "--project-root", str(project), *extra], client=fake)


def out_dir(project):
    (d,) = (project / "outputs").iterdir()
    return d


def test_cli_writes_calendar_without_extra_request(project):
    counts = counts_for(project)
    fake = FakeOpenAI(all_valid(counts))
    assert run(project, fake, "--start-date", "2026-10-12") == 0
    assert len(fake.calls) == len(FORMATS)
    out = out_dir(project)
    assert (out / "calendar.csv").exists() and (out / "calendar.md").exists()
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    expected = sum(count_of(k, counts) for k in FORMATS)  # one entry per configured piece
    assert meta["calendar"] == {"status": "ok", "start_date": "2026-10-12", "entries": expected}


def test_cli_calendar_skips_failed_formats(project):
    counts = counts_for(project)
    script = [valid(k, counts=counts) if k != "tweets" else "bad" for k in FORMATS]
    script.insert(list(FORMATS).index("tweets") + 1, "bad")  # repair attempt also bad
    assert run(project, FakeOpenAI(script), "--start-date", "2026-10-12") == 1
    rows = list(csv.DictReader((out_dir(project) / "calendar.csv").open(encoding="utf-8")))
    assert len(rows) == sum(count_of(k, counts) for k in FORMATS if k != "tweets")
    assert "X/Twitter" not in {r["platform"] for r in rows}


def test_cli_no_calendar_when_everything_failed(project):
    script = ["bad", "bad"] * len(FORMATS)
    assert run(project, FakeOpenAI(script)) == 1
    out = out_dir(project)
    assert not (out / "calendar.csv").exists()
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["calendar"]["status"] == "skipped"


def test_cli_rejects_bad_start_date(project, capsys):
    with pytest.raises(SystemExit):
        run(project, FakeOpenAI([]), "--start-date", "next tuesday")
    assert "YYYY-MM-DD" in capsys.readouterr().err
