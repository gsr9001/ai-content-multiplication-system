"""Offline style checks on generated text. Pure functions: no LLM call, no I/O.

Each check returns short issue strings. The caller decides what to do with them
(one repair request, then keep the content and record the issues as warnings).
"""

import re

MAX_ISSUES = 5  # keep the repair message short

# format key -> (text fields, field whose opening words must be unique, max exclamation marks,
#                max emoji, hashtags allowed in text)
RULES: dict[str, tuple[tuple[str, ...], str, int, int, bool]] = {
    "linkedin": (("body",), "body", 1, 2, False),
    "tweets": (("text",), "text", 1, 2, True),
    "newsletter": (("heading", "body"), "body", 1, 1, False),
    "substack_notes": (("text",), "text", 1, 1, False),
    "youtube_scripts": (("title", "hook", "body", "call_to_action"), "hook", 0, 0, False),
    "instagram_captions": (("text",), "text", 1, 2, True),
}

_BULLET = "\u2022"  # bullet character

MARKDOWN_PATTERNS = {
    "**bold**": re.compile(r"\*\*|__"),
    "backticks": re.compile(r"`"),
    "# heading": re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE),
    "bullet list": re.compile(r"^\s*[-*" + _BULLET + r"]\s+", re.MULTILINE),
    "> quote": re.compile(r"^\s*>", re.MULTILINE),
    "[link](url)": re.compile(r"\[[^\]]+\]\([^)]+\)"),
}

# --- emoji counting -------------------------------------------------------------------
# One visible emoji = one match. A match is a keycap, a flag, or a base emoji with its
# modifiers, optionally joined to more of them by zero-width joiners (ZWJ sequences).
# Stray modifiers, joiners and variation selectors never count on their own.
_VS16 = "\N{VARIATION SELECTOR-16}"  # variation selector: "show as emoji"
_ZWJ = "\N{ZERO WIDTH JOINER}"  # zero-width joiner
_TONE = "[\U0001F3FB-\U0001F3FF]"  # skin-tone modifiers
# Astral emoji blocks, without regional indicators (flags) and skin-tone modifiers.
_ASTRAL = "[\U0001F000-\U0001F1E5\U0001F200-\U0001F3FA\U0001F400-\U0001FAFF]"
# BMP symbols count only with VS16 (so plain typography such as a check mark or an arrow does not)...
_BMP_SYMBOL = (
    "[\u00A9\u00AE\u203C\u2049\u2122\u2139\u2194-\u21AA\u231A-\u23FF\u24C2\u25AA-\u25FE"
    "\u2600-\u27BF\u2934\u2935\u2B05-\u2B55\u3030\u303D\u3297\u3299]"
)
# ...unless they are one of this small set of characters that default to emoji presentation.
_BMP_DEFAULT_EMOJI = "[\u2705\u274C\u2B50\u26A1\u2728\u2757\u2753]"

_ELEMENT = (
    "(?:" + _ASTRAL + "(?:" + _VS16 + "|" + _TONE + ")*"
    "|" + _BMP_SYMBOL + _VS16 + _TONE + "*"
    "|" + _BMP_DEFAULT_EMOJI + _VS16 + "?)"
)
_KEYCAP = "[0-9#*]" + _VS16 + "?\N{COMBINING ENCLOSING KEYCAP}"
_FLAG = "[\U0001F1E6-\U0001F1FF]{2}"
EMOJI = re.compile(_KEYCAP + "|" + _FLAG + "|" + _ELEMENT + "(?:" + _ZWJ + _ELEMENT + ")*")

HASHTAG = re.compile(r"(?<!\w)#\w")
OPENING_WORDS = 3


def count_emoji(text: str) -> int:
    """Number of visible emoji in `text` (a sequence such as a family or a flag counts once)."""
    return len(EMOJI.findall(text))


def _opening(text: str) -> str:
    words = re.sub(r"[^\w']+", " ", text.lower()).split()
    return " ".join(words[:OPENING_WORDS])


def lint(key: str, items: list[dict]) -> list[str]:
    """Return style issues for one format's pieces (each piece as a dict of its text fields)."""
    if key not in RULES:
        return []
    fields, opening_field, max_exclaim, max_emoji, hashtags_ok = RULES[key]
    issues: list[str] = []
    openings: dict[str, int] = {}
    for n, item in enumerate(items, 1):
        piece = "\n".join(str(item.get(f, "")) for f in fields)
        for field in fields:
            text = str(item.get(field, ""))
            for label, pattern in MARKDOWN_PATTERNS.items():
                if pattern.search(text):
                    issues.append(f"piece {n} {field}: contains Markdown ({label})")
        if piece.count("!") > max_exclaim:
            issues.append(f"piece {n}: too many exclamation marks (max {max_exclaim})")
        if count_emoji(piece) > max_emoji:
            issues.append(f"piece {n}: too many emoji (max {max_emoji})")
        if not hashtags_ok and HASHTAG.search(piece):
            issues.append(f"piece {n}: contains a hashtag, which this format does not allow")
        opening = _opening(str(item.get(opening_field, "")))
        if opening in openings:
            issues.append(f"pieces {openings[opening]} and {n} start with the same words ('{opening}')")
        elif opening:
            openings[opening] = n
    return issues[:MAX_ISSUES]


SHINGLE_WORDS = 5
MIN_SHINGLES = 5  # shorter pieces are too small to compare reliably
OVERLAP_THRESHOLD = 0.5


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = re.sub(r"[^\w']+", " ", text.lower()).split()
    return {tuple(words[i : i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)}


def repeated_text(pieces: list[tuple[str, str]]) -> list[str]:
    """Flag pieces from different formats that share long runs of identical wording.

    `pieces` is [(label, text)] where the label starts with the format key. Warnings only:
    this finds copied wording, not repeated ideas in different words.
    """
    prepared = [(label, _shingles(text)) for label, text in pieces]
    found: list[str] = []
    for i, (a, sa) in enumerate(prepared):
        for b, sb in prepared[i + 1 :]:
            if a.split("/")[0] == b.split("/")[0]:
                continue
            smaller = min(len(sa), len(sb))
            if smaller < MIN_SHINGLES:
                continue
            if len(sa & sb) / smaller >= OVERLAP_THRESHOLD:
                found.append(f"{a} and {b} repeat the same wording")
    return found[:MAX_ISSUES]
