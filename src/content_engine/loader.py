"""Read and clean the input article or transcript."""

import re
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_SUFFIXES = {".txt", ".md"}
MAX_BYTES = 2_000_000  # hard limit: refuse anything bigger
SHORT_WORDS = 200  # warn below this
LONG_WORDS = 20_000  # warn above this

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_RUNS = re.compile(r"\n{3,}")


class LoaderError(Exception):
    """The input file cannot be used."""


@dataclass(frozen=True)
class Source:
    path: Path
    text: str
    word_count: int
    warnings: list[str] = field(default_factory=list)


def clean_text(raw: str) -> str:
    """Normalize newlines, drop control characters, trim, collapse blank-line runs."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_RUNS.sub("\n\n", text)
    return text.strip()


def load_source(path: str | Path) -> Source:
    path = Path(path)
    if not path.is_file():
        raise LoaderError(f"Input file not found: {path}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise LoaderError(
            f"Unsupported file type '{path.suffix}'. Use one of: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise LoaderError(f"{path.name} is too large ({size:,} bytes; limit {MAX_BYTES:,}).")
    try:
        raw = path.read_text(encoding="utf-8-sig")  # also strips a BOM
    except UnicodeDecodeError:
        raise LoaderError(f"{path.name} is not valid UTF-8 text. Re-save it as UTF-8.") from None

    text = clean_text(raw)
    if not text:
        raise LoaderError(f"{path.name} is empty.")

    words = len(text.split())
    warnings = []
    if words < SHORT_WORDS:
        warnings.append(f"Input is short ({words} words); results may be thin.")
    if words > LONG_WORDS:
        warnings.append(f"Input is very long ({words:,} words); cost and latency will be higher.")
    return Source(path=path, text=text, word_count=words, warnings=warnings)
