# targoo

`targoo` is a **Hebrew→English translation pipeline** built around your
provider trio (with the bake-off to pick the winner):

| Provider | Kind | Where it runs |
| --- | --- | --- |
| `bedrock` — Claude | Bedrock Messages API (Anthropic SDK) | your AWS account |
| `ollama-cloud` — Gemma | Ollama API over HTTPS | Ollama Cloud |
| `dicta-local` — Dicta 3.0 | Ollama API | Ollama on this machine |

The main pipeline is `targoo translate` → edit → `targoo freeze <id>` (see below). The
blind bake-off (`bakeoff`, `judge`, `inspect-key`) is kept as a secondary tool for
comparing models or prompt revisions (Phase 3+, e.g. when you add a new provider).

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

## The final-translation pipeline

```bash
targoo translate                          # every corpus passage via the `final:` provider
targoo translate --ids amidah --provider bedrock
# edit translations/<id>.txt by hand — that file is the review surface
targoo freeze amidah                      # approve the .txt as the passage's final text
targoo status                             # untranslated / drafted / draft-error / frozen
```

- **`targoo translate`** renders `prompts/final.md` for each passage and calls the
  configured provider. Passages that already have a draft are skipped (pass `--force` to
  re-draft); **frozen passages are never re-drafted** — unfreeze with
  `targoo freeze <id> --reopen` first. Failures are recorded per passage and the run
  continues, so a provider timeout costs that passage, not the run.
- **`translations/<id>.txt`** is the readable export and the review surface: freeze always
  imports *that file's current contents*. Edit it freely — freeze records whether it
  changed since the draft (`edit_history`).
- **`tm/<id>.yaml`** is the record of truth: the Hebrew source, the draft with full
  provenance (provider, model, prompt name + sha256), `english_frozen`, and
  `edit_history`. **It is committed to git, and git history is the authorship record —
  never rewrite history on a frozen TM file.**

Adding new texts later is the same loop: drop a `.txt` file into `texts/`, run
`targoo translate` (existing passages are skipped), review, freeze.

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
    model: us.anthropic.claude-sonnet-4-6   # inference-profile id — plain anthropic.*
    aws_region: us-east-1                # ids fail on-demand throughput validation
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
    model: dicta-il/DictaLM-3.0-1.7B-Thinking:latest    # exact tag from `ollama list`
    timeout_seconds: 300

judge: bedrock            # which provider grades the blind drafts (temperature 0)
final: bedrock            # which provider renders final translations via prompts/final.md
```

**Secrets are environment-only:** Ollama Cloud keys come from the env var named by
`api_key_env`; Bedrock auth uses the standard AWS chain (`AWS_PROFILE`, SSO, or explicit keys),
so run `aws sso login` first or export keys. See `.env.example` for the full list.

**Verifying your three models:** copy the exact model tag from `ollama list` for the local Dicta
model; `ollama run gemma4:cloud` (or `ollama pull`) confirms the cloud model name; and
`aws bedrock list-inference-profiles --region <your-region>` shows the Claude profile ids your
account can invoke. Bedrock accounts normally invoke Claude through cross-region inference
profiles (`us.anthropic.claude-*` or `eu.anthropic.claude-*`): the plain `anthropic.*` model id
fails on-demand throughput validation, and the 5.x/Fable ids can additionally 403 if access
wasn't granted to your account. targoo's Bedrock leg talks to bedrock-runtime, so pass the
inference-profile id.

**Adding another provider** is any `kind: ollama` block pointing at a reachable base URL, or a
`kind: bedrock` block with another model id — then name it in `--models`.

## Running a bake-off (model comparisons, Phase 3+)

The three-way bake-off ran in 2026-10: Bedrock (Claude sonnet-4-6) won decisively against
ollama-cloud (Gemma) and dicta-local (Dicta 3.0), confirmed by both the blind LLM judge and
the human blind review. The commands stay available for re-benchmarking when you add a
provider or revise a prompt:

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
├── cli.py            # commands: translate, freeze, status + bake-off suite
├── config.py         # targoo.yaml loading + validation
├── corpus.py         # texts/*.txt → passages with stable ids
├── prompts.py        # Jinja2 rendering of prompts/
├── finalize.py       # final-translation orchestration (draft → edit → freeze)
├── tm.py             # translation-memory documents under tm/
├── bakeoff.py        # blind model-comparison orchestration
├── judge.py          # judge pass, JSON parsing, mean-score summary
└── providers/
    ├── base.py       # Provider protocol + Completion + ProviderError
    ├── ollama.py     # one client for local daemon and Ollama Cloud
    └── bedrock.py    # Claude via AnthropicBedrock (bedrock-runtime, SigV4)
prompts/draft.md      # the bake-off draft prompt ({{ source }} template)
prompts/judge.md      # the judge prompt ({{ source }} + {{ draft }})
prompts/final.md      # the final-translation prompt (no review after this pass)
texts/                # your corpus — add passages here
tm/                   # translation memory — committed to git; history is authorship
translations/         # readable exports + your post-edits (the freeze surface)
outputs/              # bake-off runs (gitignored)
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

Phase 2's core is in (`tm.py` + `finalize.py`): TM YAML per passage, the draft →
post-edit → freeze workflow. Remaining: the style guide + glossary + exemplar retrieval
(prompt-side, `style/`), the consistency audit (repeated Hebrew spans → divergent English),
and the assemble/export step. The provider protocol in
`src/targoo/providers/base.py` is the seam all of that plugs into.

## Releasing

Tags on `main` trigger the CI workflow (`/.github/workflows/ci.yml`); add a GoReleaser- or
pyproject-based release job here when targoo needs distribution.