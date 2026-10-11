---
name: add-content-format
description: Add a new content format (e.g. a new platform) to content-engine safely and in dependency order. Edits schemas, config, prompt, generator, calendar and offline tests. Manual use only.
argument-hint: [format-key]
disable-model-invocation: true
---

# Add a content format

Procedure for adding one new format to `content-engine`. The project-wide rules in `CLAUDE.md` always apply; the ones that matter most here are repeated below.

## Ground rules
- Never open, read, print, expose, or commit `.env` or any secret.
- Never run the application or `pytest -m live` without the user's explicit approval. A full run adds one more billable OpenAI request.
- Offline tests only. Ask for approval once before running them (Step 5).
- Never overwrite or delete anything in `outputs/`.
- Only `src/content_engine/llm.py` talks to OpenAI. Do not edit it.
- Never weaken, delete, or skip an existing test to make it pass. Fix the implementation.
- Do not commit. Leave all changes uncommitted for review.
- If anything is missing, unclear, or conflicting, ask the user. Do not guess.

## Step 1: Gather inputs
Use `$ARGUMENTS` as the format key if given. Collect all of these; ask for whatever is missing:
- Format key (lowercase, underscores) and display name. Check it is not already in `FORMATS`.
- Item count and the `count_attr` name for `Counts` (default `ge=1`).
- Output fields for one item, and any max-length limits.
- Calendar: platform label, posting times (24h), and `first_day` (0-4, index into the 10 weekdays).
- Position in generation order (default: end of `FORMATS`).
- Prompt style rules (tone, structure, emoji/hashtags).

## Step 2: Inspect (read-only)
Read `src/content_engine/{generators,models,calendar,config}.py`, `config/settings.yaml`, `tests/replies.py`, `tests/test_pipeline.py`, `tests/test_calendar.py`, `tests/test_prompts.py`, and the most similar existing format end to end plus its prompt. Note anything surprising.

## Step 3: Present the plan, then WAIT
Show the user: inputs gathered, every file to change with the exact edit, the new prompt text, and the risks. **Do not edit any project file until the user explicitly approves.**

## Step 4: Implement in dependency order
1. `src/content_engine/models.py`: optional `*_MAX_CHARS` constant, item model, list wrapper (`extra="ignore"`).
2. `src/content_engine/config.py`: new `int` field on `Counts` (`extra="forbid"`, so the field must exist before the YAML key).
3. `config/settings.yaml`: the `counts:` entry.
4. `prompts/<key>.md`: same headings as the other prompts. Copy the shared block, from `# Source fidelity` up to (not including) `# Output format`, byte-for-byte from an existing prompt. Never reword it and never touch it in the existing prompts. Only `# Brand voice`, `# Task` and `# Output format` are new. Use only placeholders that `generate()` fills: `{{brand_voice}}`, `{{count}}`, and the keys in the format's `limits`.
5. `src/content_engine/generators.py`: a `_<key>_markdown` renderer and a `FormatSpec` entry in `FORMATS`.
6. `src/content_engine/calendar.py`: a `Channel` entry in `CHANNELS`. The key must equal the `FORMATS` key.
7. `tests/replies.py`: a `BUILDERS` entry.
8. `tests/test_pipeline.py`: add to `HEADINGS`; update the hard-coded `KEYS == [...]` list.
9. `tests/test_calendar.py`: add the new format to the hard-coded totals and per-file counts. Extend the assertions; do not loosen them.

`cli.py` and most of `test_prompts.py` iterate over `FORMATS`, so they need no edit.

## Step 5: Offline verification
Ask the user once for approval to run offline tests. If approved, run `pytest tests/test_prompts.py`, then `pytest`. If a test fails, diagnose and fix the implementation; do not change the test's intent. Never run the app or live tests.

## Step 6: Documentation (only where now wrong)
- `README.md`: the format list, the output-files list, and "identical in all five prompts" if outdated.
- `CLAUDE.md`: change "all five `prompts/*.md`" to "all prompt templates" and the "5 templates" in the module map, when they become outdated. Keep CLAUDE.md to rules and context; put no procedures there.
- Keep the test function name `test_shared_block_is_identical_across_all_five_prompts` unchanged unless there is a compelling technical reason.

## Step 7: Final review (no commit)
Run read-only `git status` and `git diff --stat`. Report: files changed, tests run and results, and open decisions. Confirm that the shared block is identical across all prompts and that no file outside the allowed list changed.

## Files this skill may modify
`models.py`, `config.py`, `generators.py`, `calendar.py` (all under `src/content_engine/`), `config/settings.yaml`, the new `prompts/<key>.md`, `tests/replies.py`, `tests/test_pipeline.py`, `tests/test_calendar.py`, and, only if genuinely needed, `README.md` and `CLAUDE.md`.

## Never modify
`.env`, `.env.example`, `src/content_engine/llm.py`, `outputs/`, `pyproject.toml`, `tests/test_live.py`, the shared block of the existing five prompts, or this skill file.

## Key risks
- Shared block drift (the prompt test catches it).
- Key mismatch across `FORMATS`, `CHANNELS`, the prompt filename and the output filename.
- `count_attr` not matching the `Counts` field, or a YAML key added before the field.
- Unfilled `{{placeholders}}` sent to the model.
- Hard-coded test totals left stale.
- A poor `first_day` or `times` setting crowding the calendar.
