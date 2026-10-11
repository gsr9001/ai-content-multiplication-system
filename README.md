# AI Content Multiplication System

Turn one article or transcript into a full content pack, written in your brand voice:

- 5 LinkedIn posts
- 10 tweets
- 3 newsletter sections
- 3 Substack Notes
- 2 YouTube scripts
- 5 Instagram captions
- A two-week content calendar (CSV and Markdown)

It uses the OpenAI API. A normal run sends **6 requests** (one per format). The calendar is built
locally and costs nothing. Retries only happen when a request fails or returns invalid output.

## Setup (once)

You need Python 3.10 or newer. From this folder:

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then add your API key:

1. Copy `.env.example` to `.env`.
2. Open `.env` and put your key after `OPENAI_API_KEY=`.

`.env` is listed in `.gitignore`, so Git will never track it. Never paste your key into chat,
code, or any file other than `.env`. If a key is ever exposed, rotate it in the OpenAI dashboard.

## Use

1. Put your article or transcript (`.txt` or `.md`) in `inputs/`. To just try it, use the bundled
   example, `tests/fixtures/sample_article.md`.
2. Run (use `/` instead of `\` on macOS / Linux):

```powershell
content-engine run inputs\my_article.md
```

Options:

| Option | Meaning |
|---|---|
| `--voice PATH` | Use a different brand voice file (default `config\brand_voice.yaml`) |
| `--start-date YYYY-MM-DD` | First day of the calendar (default: next Monday) |
| `--project-root PATH` | Folder holding `config\`, `prompts\` and `.env` (default: current folder) |

`python -m content_engine run ...` works the same way.

## Where the results go

Each run creates a new folder, for example `outputs\2026-10-10_143205_my-article\`:

| File | Contents |
|---|---|
| `linkedin.md`, `tweets.md`, `newsletter.md`, `substack_notes.md`, `youtube_scripts.md`, `instagram_captions.md` | The generated content |
| `calendar.csv`, `calendar.md` | The two-week schedule |
| `run_meta.json` | Model, brand voice, input hash, per-format status, requests and retries (never your key) |

Earlier runs are never overwritten. If two runs start in the same second, the second folder gets a
`_2` suffix, and files are only ever created, never replaced.

If one format fails (for example the model keeps returning invalid output), the other formats are
still saved, the failure is recorded in `run_meta.json`, and the command exits with code 1.

## Customise

- **Brand voice:** edit `config\brand_voice.yaml` (tone, audience, do/don't, sample phrases).
- **Model, temperature, retries, counts:** edit `config\settings.yaml`. Check that the `model`
  name is a current one before your first run.
- **Prompts:** edit the files in `prompts\`. Keep the `{{placeholders}}` and the JSON output format.
  The shared rules block (from `# Source fidelity` to just before `# Output format`) must stay
  identical in all prompts; a test checks this, so change it in every file.
- **Calendar times and spacing:** see `CHANNELS` in `src\content_engine\calendar.py`. Instagram
  captions list two times (09:00 and 18:00), but with the default 5 captions only 09:00 is used:
  18:00 is used only when two or more captions fall on the same day.

## Project layout

| Path | Purpose |
|---|---|
| `src\content_engine\cli.py` | The `content-engine` command |
| `config.py` | Loads `.env`, settings and brand voice; hides the key |
| `loader.py` | Reads and cleans the input file |
| `llm.py` | The only code that talks to OpenAI; handles retries |
| `generators.py` | Builds prompts, validates replies, repairs once if invalid |
| `models.py` | Rules each format must meet (counts, character limits) |
| `calendar.py` | Builds the schedule locally |
| `writer.py` | Creates a fresh run folder and writes files without overwriting |
| `prompts\` | One prompt template per format |
| `tests\` | Offline tests, plus one opt-in live test |

## Tests

```powershell
pytest
```

Ordinary tests never use the network or a real API key: a fake OpenAI client is used, network
access is blocked, and `OPENAI_API_KEY` is cleared while they run.

There is one opt-in live test that makes real API calls (about 6 requests):

```powershell
pytest -m live
```

## Limits to know about

- Tweet length is checked in characters. X counts links and some emoji differently, so check long
  or link-heavy tweets before posting.
- Instagram caption length (2,200 characters) is also checked in characters by this application.
  Instagram's own counting may differ slightly, especially for emoji, so check captions that are
  close to the limit on the platform before posting.
- The system writes drafts. It does not post anywhere. Read everything before publishing.
- Very long inputs cost more and may exceed the model's context window.
