# targoo

`targoo` is a bake-off harness for **Hebrew→English translation with LLMs**, built around your
provider trio:

| Provider | Kind | Where it runs |
| --- | --- | --- |
| `bedrock` — Claude | Bedrock Messages API (Anthropic SDK) | your AWS account |
| `ollama-cloud` — Gemma | Ollama API over HTTPS | Ollama Cloud |
| `dicta-local` — Dicta 3.0 | Ollama API | Ollama on this machine |

You add Hebrew source texts as plain files, run them through some or all of the providers, read
the drafts **blind** (each translation is labelled A/B/C, and only a separate key file knows which
letter was which model), and can additionally have an LLM judge score each blind draft. This is
Phase 0/1 of the pipeline in [PLAN.md](PLAN.md) — the translation memory, review/freeze
workflow, and consistency audit come later on the same scaffold.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is provisioned by uv itself)
- An AWS account where Claude is enabled on **Amazon Bedrock**, configured either via SSO
  (`aws sso login --profile <profile>`) or a key (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)
- An [Ollama Cloud](https://ollama.com) API key
- A local [Ollama](https://ollama.com) install running the Dicta 3.0 model
  (`ollama list` shows the exact tag; you may need to `ollama pull` or `ollama pull hf.co/...`
  the model first)

## Quick start

```bash
uv sync                    # create .venv and install deps

# Credentials (all from the environment; nothing is ever read from targoo.yaml):
aws sso login --profile my-profile   # or export AWS keys directly
export AWS_PROFILE=my-profile
export OLLAMA_API_KEY=sk-...         # Ollama Cloud key

ollama list             # confirm the local Dicta model tag; adjust targoo.yaml if it differs

targoo texts            # lists what would be translated
targoo bakeoff          # translate everything with every configured provider
targoo judge --run outputs/<run-name>
targoo inspect-key outputs/<run-name>   # only after your blind review is done
```

## Adding source texts

The corpus is a directory of plain UTF-8 text files (`texts/` by default):

- **One passage per file.** A passage is the unit of review: a verse, a paragraph, a prayer,
  a psalm — whatever you want to compare one draft at a time. Short to medium passages give the
  sharpest comparisons; anything over a page or so risks provider timeouts (bump
  `timeout_seconds` if you go big).
- **The filename is the passage id** — it appears in every output file and (later) in the
  translation memory, so keep ids stable and human-readable, lowercase-kebab: `genesis-1.1-4.txt`,
  `amidah-avot.txt`. Never put spaces in it. Renaming a file changes its id.
- **The file's entire content is sent to the models.** No comments, headers, or provenance
  notes in the file — record source references in a note elsewhere if you need them (or in code
  review docs later, one place per passage id).
- Blank lines are meaningful: line/paragraph structure is preserved in the draft prompt, so
  separate verses with blank lines if you want that structure honored.
- Niqqud is fine (and a good idea); cantillation marks are also fine but make texts noisier.

Handy: use [nechama](https://github.com/shekelator/nechama) to fetch a passage from Sefaria
directly into the corpus (it strips cantillation by default, keeps niqqud):

```bash
nechama "Genesis 1:1-4" -o texts/genesis-1.1-4.txt
nechama --preserve-cantillation "Psalm 23:1-4" -o texts/psalm-23.1-4.txt
```

Then check what targoo sees:

```bash
targoo texts
# genesis-1.1-4	he	7 lines	304 chars
# psalm-23.1-4	he	7 lines	266 chars
```

## Configuration

Settings live in `targoo.yaml` in the repo root (override the location with `TARGOO_CONFIG`,
or a per-invocation `--config`). `targoo init` writes a fresh starter file anywhere else.

```yaml
temperature: 0.2          # draft sampling temperature — Ollama providers only
max_tokens: 8000          # per-passage draft output ceiling

providers:
  bedrock:
    kind: bedrock
    model: anthropic.claude-opus-5-5     # Bedrock model id (anthropic. prefix)
    aws_region: us-east-1                # a region where Claude is enabled for you
    # effort: medium                     # optional (low..max) — replaces temperature,
    #                                    # which current Claude families no longer accept
    # aws_profile: default # optional; otherwise the standard AWS chain applies
  ollama-cloud:
    kind: ollama
    base_url: https://ollama.com         # Ollama Cloud endpoint
    model: gemma4:cloud
    api_key_env: OLLAMA_API_KEY          # name of the env var holding the key
    timeout_seconds: 180
  dicta-local:
    kind: ollama
    base_url: http://127.0.0.1:11434
    model: dictalm-3.0                   # exact tag from `ollama list`
    timeout_seconds: 300

judge: bedrock            # which provider grades the blind drafts (temperature 0)
```

**Secrets are environment-only:** Ollama Cloud keys come from the env var named by
`api_key_env`; Bedrock auth uses the standard AWS chain (`AWS_PROFILE`, SSO, or explicit keys),
so run `aws sso login` first or export keys. See `.env.example` for the full list.

**Verifying your three models:** copy the exact model tag from `ollama list` for the local Dicta
model; `ollama run gemma4:cloud` (or `ollama pull`) confirms the cloud model name; and
`aws bedrock list-foundation-models --region <your-region> --by-provider anthropic` shows the
Claude ids your account can invoke. If your account requires a cross-region inference profile,
set `model` to the profile id (e.g. `us.anthropic.claude-opus-5-5`).

**Adding another provider** is any `kind: ollama` block pointing at a reachable base URL, or a
`kind: bedrock` block with another model id — then name it in `--models`.

## Running a bake-off

```bash
targoo bakeoff                                  # all configured providers
targoo bakeoff --models dicta-local,ollama-cloud
targoo bakeoff --run-name amidah-avot --seed 42 # reproducible letter assignment
```

For every text you get an anonymized draft file in `outputs/<run-name>/`:

```
outputs/<run-name>/
├── bakeoff-key.yaml    # letter → model map — DON'T open while reviewing
├── drafts.yaml         # machine-readable blind drafts (letter-keyed)
├── judgments.yaml      # written by `targoo judge`
└── passages/
    └── genesis-1.1-4.md   # the source + Draft A / Draft B / Draft C
```

Letters are freshly shuffled per passage (unless seeded), so "A" is not the same model in every
file. Nothing user-facing names the models — the outputs, the prompts the judge sees, and even
the progress log only carry letters — and `outputs/` is gitignored so the key can't leak into a
commit by accident.

## Reviewing and judging

1. `targoo bakeoff` → read `outputs/<run>/passages/*.md` and rank the drafts per passage while
   still blind. Edit the `.md` files with your notes if you want an audit trail.
2. `targoo judge --run outputs/<run>` — the configured judge scores each blind draft on
   **faithfulness**, **fluency**, and **accuracy** (1–5) with written notes, and prints a mean
   table per letter. Judge output that isn't parseable JSON is recorded as an error, not scores.
3. `targoo inspect-key outputs/<run>` — only now look at which letter was which model, and
   reconcile the judge's letters with your own rankings.

The judge stays blind by construction (it receives letters, never provider names), but remember
it is another LLM: treat its scores as triage, and your own read as the deciding vote — that is
the point of the blind step.

## Project layout

```
src/targoo/
├── cli.py            # commands: init, texts, bakeoff, judge, inspect-key
├── config.py         # targoo.yaml loading + validation
├── corpus.py         # texts/*.txt → passages with stable ids
├── prompts.py        # Jinja2 rendering of prompts/
├── bakeoff.py        # run orchestration + anonymization
├── judge.py          # judge pass, JSON parsing, mean-score summary
└── providers/
    ├── base.py       # Provider protocol + Completion + ProviderError
    ├── ollama.py     # one client for local daemon and Ollama Cloud
    └── bedrock.py    # Claude via AnthropicBedrockMantle (AWS SigV4)
prompts/draft.md      # the draft prompt ({{ source }} template)
prompts/judge.md      # the judge prompt ({{ source }} + {{ draft }})
texts/                # your corpus — add passages here
PLAN.md               # full pipeline roadmap (Phases 0–4)
```

## Development

```bash
uv run pytest
uv run ruff check src tests
uv run pre-commit run --all-files   # optional, after `uv tool install pre-commit`
```

Tests are network-free: the ollama client is exercised through `httpx.MockTransport`, and the
Bedrock client through an injected fake, so provider behavior is pinned without paid calls.

## Roadmap

Phases 2–4 of [PLAN.md](PLAN.md) build `bakeoff.py`'s successor: translation-memory YAML files
per passage id, a draft → post-edit → freeze workflow, the style guide + glossary + exemplar
retrieval, and a consistency audit. The provider protocol in
`src/targoo/providers/base.py` is the seam all of that plugs into.

## Releasing

Tags on `main` trigger the CI workflow (`/.github/workflows/ci.yml`); add a GoReleaser- or
pyproject-based release job here when targoo needs distribution.