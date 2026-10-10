"""Save outputs safely: every run gets a brand-new folder, files are never overwritten."""

import json
import re
from datetime import datetime
from pathlib import Path

MAX_SLUG = 50
MAX_COLLISIONS = 10_000


class WriterError(Exception):
    """An output could not be saved safely."""


def slugify(name: str) -> str:
    """Filesystem-safe lowercase slug from a file name or title."""
    stem = Path(name).stem if name else ""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:MAX_SLUG].strip("-")
    return slug or "input"


class RunOutput:
    """One run's output folder. Created fresh; files can only be created, never replaced."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(
        cls, outputs_root: Path, input_name: str, now: datetime | None = None
    ) -> "RunOutput":
        """Make outputs/<YYYY-MM-DD_HHMMSS>_<slug>/, adding _2, _3, ... if it already exists."""
        now = now or datetime.now()
        base = f"{now:%Y-%m-%d_%H%M%S}_{slugify(input_name)}"
        outputs_root = Path(outputs_root)
        outputs_root.mkdir(parents=True, exist_ok=True)
        for n in range(1, MAX_COLLISIONS + 1):
            candidate = outputs_root / (base if n == 1 else f"{base}_{n}")
            try:
                candidate.mkdir(exist_ok=False)  # atomic: fails if it exists
            except FileExistsError:
                continue
            return cls(candidate)
        raise WriterError(f"Could not find an unused output folder for {base}.")

    def write_text(self, filename: str, content: str) -> Path:
        """Create a new file in this run's folder. Raises FileExistsError if it exists."""
        if Path(filename).name != filename or filename in {"", ".", ".."}:
            raise WriterError(f"Output file name must be a plain file name: {filename!r}")
        target = self.path / filename
        with open(target, "x", encoding="utf-8", newline="\n") as fh:  # "x" = exclusive create
            fh.write(content)
        return target

    def write_json(self, filename: str, data: object) -> Path:
        return self.write_text(filename, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
