"""Build the content calendar locally. No LLM call: same input always gives the same schedule."""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from pydantic import BaseModel

PREVIEW_CHARS = 80
SPAN_DAYS = 14  # two weeks always contain exactly 10 weekdays


@dataclass(frozen=True)
class Channel:
    platform: str
    times: tuple[str, ...]  # suggested posting times (24h, your local time); cycled if >1 per day
    first_day: int  # index into the 10 weekdays: where this channel starts
    items: Callable[[BaseModel], list[tuple[str, str]]]  # model -> [(label, preview source)]


# first_day values are staggered so different formats rarely open on the same weekday;
# LinkedIn and tweets stay on day 0 because they lead the week.
CHANNELS: dict[str, Channel] = {
    "linkedin": Channel(
        "LinkedIn", ("08:30",), 0,
        lambda r: [(f"Post {i}", p.body) for i, p in enumerate(r.posts, 1)],
    ),
    "tweets": Channel(
        "X/Twitter", ("09:00", "13:00", "17:00"), 0,
        lambda r: [(f"Tweet {i}", t.text) for i, t in enumerate(r.tweets, 1)],
    ),
    "newsletter": Channel(
        "Newsletter", ("07:00",), 1,
        lambda r: [(f"Section {i}: {s.heading}", s.body) for i, s in enumerate(r.sections, 1)],
    ),
    "substack_notes": Channel(
        "Substack Notes", ("12:00",), 3,
        lambda r: [(f"Note {i}", n.text) for i, n in enumerate(r.notes, 1)],
    ),
    "youtube_scripts": Channel(
        "YouTube", ("10:00",), 1,
        lambda r: [(f"Script {i}: {s.title}", s.hook) for i, s in enumerate(r.scripts, 1)],
    ),
    # 18:00 is used only when two or more captions fall on the same day (not with the default 5).
    "instagram_captions": Channel(
        "Instagram", ("09:00", "18:00"), 2,
        lambda r: [(f"Caption {i}", c.text) for i, c in enumerate(r.captions, 1)],
    ),
}


@dataclass(frozen=True)
class CalendarEntry:
    day: date
    time: str
    platform: str
    piece: str
    preview: str
    file: str  # which output file holds the full text


def next_monday(today: date) -> date:
    """The Monday strictly after `today`."""
    return today + timedelta(days=7 - today.weekday())


def _weekdays(start: date) -> list[date]:
    days = [start + timedelta(days=i) for i in range(SPAN_DAYS)]
    return [d for d in days if d.weekday() < 5]


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[: PREVIEW_CHARS - 1].rstrip() + "\u2026"


def build_calendar(results: dict[str, BaseModel], start: date) -> list[CalendarEntry]:
    """Spread each format's pieces evenly over the two weeks' weekdays, in piece order."""
    weekdays = _weekdays(start)
    order = list(CHANNELS)
    entries: list[tuple[tuple, CalendarEntry]] = []
    for key in order:
        if key not in results:
            continue
        channel = CHANNELS[key]
        days = weekdays[channel.first_day :]
        pieces = channel.items(results[key])
        per_day: dict[date, int] = {}
        for i, (label, text) in enumerate(pieces):
            day = days[(i * len(days)) // len(pieces)]
            nth = per_day.get(day, 0)
            per_day[day] = nth + 1
            time = channel.times[nth % len(channel.times)]
            entry = CalendarEntry(day, time, channel.platform, label, _preview(text), f"{key}.md")
            entries.append(((day, time, order.index(key), i), entry))
    return [e for _, e in sorted(entries, key=lambda pair: pair[0])]


def _csv_safe(text: str) -> str:
    """Stop spreadsheets from running a cell as a formula."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def calendar_csv(entries: list[CalendarEntry]) -> str:
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(["date", "weekday", "time", "platform", "piece", "preview", "file"])
    for e in entries:
        out.writerow(
            [e.day.isoformat(), e.day.strftime("%A"), e.time, e.platform,
             _csv_safe(e.piece), _csv_safe(e.preview), e.file]
        )
    return buf.getvalue()


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def calendar_markdown(entries: list[CalendarEntry], start: date) -> str:
    lines = [
        "# Content calendar",
        f"\nStarts {start.isoformat()}. Times are suggestions in your local time zone.",
    ]
    week = None
    for e in entries:
        this_week = (e.day - start).days // 7 + 1
        if this_week != week:
            week = this_week
            lines += [
                f"\n## Week {week}\n",
                "| Date | Day | Time | Platform | Piece | Preview |",
                "|---|---|---|---|---|---|",
            ]
        lines.append(
            f"| {e.day.isoformat()} | {e.day.strftime('%a')} | {e.time} | {e.platform} "
            f"| {_cell(e.piece)} ({e.file}) | {_cell(e.preview)} |"
        )
    return "\n".join(lines) + "\n"
