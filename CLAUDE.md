# CLAUDE.md

## 1. Project Overview
`content-engine` turns one `.txt`/`.md` article or transcript into a multi-platform content pack (LinkedIn posts, tweets, newsletter sections, Substack Notes, YouTube scripts, Instagram captions) in a configured brand voice, plus a two-week posting calendar (CSV + Markdown). Python 3.10+, OpenAI chat completions (one request per format), pydantic validation.

Flow: load config + source -> one LLM call per format -> validate -> build calendar locally -> write a new run folder in `outputs/`.

## 2. Architecture and Module Map
`src/content_engine/`:
- `cli.py` - entry point (`content-engine run ...`); orchestrates the pipeline
- `config.py` - loads `config/settings.yaml` and `config/brand_voice.yaml`; reads the API key
- `llm.py` - the only OpenAI client; retries/backoff and request counting
- `loader.py` - reads and cleans the source file
- `models.py` - pydantic schemas and length limits
- `generators.py` - fills `prompts/<key>.md`, validates replies, renders Markdown; formats registered in `FORMATS`
- `calendar.py` - local scheduling; channels in `CHANNELS`
- `writer.py` - creates timestamped run folders under `outputs/`

Other: `prompts/` (one template per format), `config/` (settings + brand voice), `inputs/` (sources), `tests/` (offline tests, `tests/fake_llm.py` fake client, one opt-in live test).

## 3. Critical Rules
- **Secrets:** Never open, read, print, expose, or commit the contents of `.env` or any API secret. You may refer to the filename and explain how configuration works, but do not inspect secret values. The key is supplied as `OPENAI_API_KEY`, from the environment or from `.env`.
- **Billable calls:** Never run the application (`content-engine run`, `python -m content_engine`) or live tests (`pytest -m live`) without my explicit approval first. Both can make real, billable OpenAI API calls.
- Prefer offline tests for routine verification.
- `outputs/` is generated output (gitignored). Never overwrite or delete existing runs.
- Only `src/content_engine/llm.py` may communicate with the OpenAI API.
- **Shared prompt block:** The text from `# Source fidelity` through `# Using the brand voice` (everything before `# Output format`) must stay identical across all prompt templates. This is enforced by `test_shared_block_is_identical_across_all_five_prompts` in `tests/test_prompts.py`.
- Inspect before modifying files, and explain risky changes before proceeding.

## 4. Development Setup and Commands
PowerShell on Windows:
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
content-engine run inputs\<file>.md      # or: python -m content_engine run ...
```
Optional flags: `--voice`, `--start-date YYYY-MM-DD`, `--project-root`. Running the app is subject to the approval rule above.

## 5. Testing and Verification
- Routine: `pytest` (offline; `pyproject.toml` deselects `live` tests, and `tests/conftest.py` clears the key and blocks sockets).
- Prefer targeted runs, e.g. `pytest tests/test_prompts.py`, after prompt changes.
- Live: `pytest -m live` only with my explicit approval.
- No lint or type-check tooling is configured.

## 6. When to Read Additional Documentation
- `README.md` - setup, usage, output layout, customising, limits.
- `prompts/*.md` and `tests/test_prompts.py` - before editing any prompt.
- `config/settings.yaml`, `config/brand_voice.yaml` - model, counts, retries, voice.
- `generators.py` (`FORMATS`) and `calendar.py` (`CHANNELS`) - before adding or changing a content format.
