"""Command-line entry point."""

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

from content_engine import __version__
from content_engine.calendar import CHANNELS, build_calendar, calendar_csv, calendar_markdown, next_monday
from content_engine.config import ConfigError, load_config
from content_engine.generators import FORMATS, GenerationError, generate
from content_engine.llm import LLMClient, LLMError
from content_engine.loader import LoaderError, load_source
from content_engine.quality import repeated_text
from content_engine.writer import RunOutput, WriterError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-engine",
        description="Turn one article or transcript into a multi-platform content pack.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Generate content from an input file.")
    run.add_argument("input_file", help="Path to an article or transcript (.txt or .md).")
    run.add_argument("--project-root", default=".", help="Folder holding config/, prompts/, .env.")
    run.add_argument("--voice", default=None, help="Brand voice YAML (default: config/brand_voice.yaml).")
    run.add_argument(
        "--start-date",
        type=_iso_date,
        default=None,
        help="First day of the 2-week calendar, YYYY-MM-DD (default: next Monday).",
    )
    return parser


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a date; use YYYY-MM-DD.") from None


def main(argv: list[str] | None = None, *, client=None) -> int:
    """`client` lets tests inject a fake OpenAI client; normally it is None."""
    args = build_parser().parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        return _run(args, root, client)
    except (ConfigError, LoaderError, LLMError, GenerationError, WriterError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run(args, root: Path, client) -> int:
    config = load_config(root, voice_path=Path(args.voice) if args.voice else None)
    source = load_source(args.input_file)
    for warning in source.warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    llm = LLMClient(
        config.api_key,
        config.settings.model,
        config.settings.temperature,
        config.settings.max_transport_retries,
        client=client,
    )
    run = RunOutput.create(root / "outputs", source.path.name)
    meta = {
        "content_engine_version": __version__,
        "model": config.settings.model,
        "brand_voice": config.brand_voice.name,
        "input_file": source.path.name,
        "input_sha256": hashlib.sha256(source.text.encode("utf-8")).hexdigest(),
        "formats": {},
    }
    status = 0
    generated = {}
    print(f"Generating {len(FORMATS)} formats with {config.settings.model} ...")
    for key, spec in FORMATS.items():  # each format is independent: one failing doesn't stop the rest
        print(f"  {key} ...", flush=True)
        try:
            result = generate(spec, source, config, llm, root / "prompts")
            generated[key] = result.value
            run.write_text(f"{key}.md", spec.render(result.value))
            meta["formats"][key] = {"status": "ok", "validation_retries": result.validation_retries}
            if result.warnings:
                meta["formats"][key]["style_warnings"] = result.warnings
                print(f"Warning: {key} saved with style issues (see run_meta.json)", file=sys.stderr)
        except (LLMError, GenerationError) as exc:
            meta["formats"][key] = {"status": "failed", "error": str(exc)}
            print(f"Error: {key} failed: {exc}", file=sys.stderr)
            status = 1
    pieces = [
        (f"{key}/{label}", text)
        for key, value in generated.items()
        for label, text in CHANNELS[key].items(value)
    ]
    repeats = repeated_text(pieces)
    if repeats:
        meta["repeated_text"] = repeats
        print("Warning: some pieces repeat wording across formats (see run_meta.json)", file=sys.stderr)
    if generated:  # local, free: no extra request
        start = args.start_date or next_monday(date.today())
        entries = build_calendar(generated, start)
        run.write_text("calendar.csv", calendar_csv(entries))
        run.write_text("calendar.md", calendar_markdown(entries, start))
        meta["calendar"] = {"status": "ok", "start_date": start.isoformat(), "entries": len(entries)}
    else:
        meta["calendar"] = {"status": "skipped", "reason": "no content was generated"}
    meta["requests_sent"] = llm.requests
    meta["transport_retries"] = llm.transport_retries
    run.write_json("run_meta.json", meta)
    ok = [k for k, f in meta["formats"].items() if f["status"] == "ok"]
    failed = [k for k, f in meta["formats"].items() if f["status"] == "failed"]
    print(f"\nDone: {len(ok)} of {len(FORMATS)} formats succeeded.")
    if failed:
        print(f"Failed: {', '.join(failed)} (see run_meta.json)")
    print(f"Requests sent: {llm.requests} (retries: {llm.transport_retries})")
    print(f"Saved to {run.path}")
    return status
