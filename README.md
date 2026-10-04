# targoo

`targoo` is a **Hebrew→English translation pipeline**: you add Hebrew source texts, Claude
(on your AWS Bedrock account) drafts translations, you review and edit them, and the
approved results live in a git-tracked translation memory. Provenance is recorded
end-to-end — which model, which prompt, who edited what.

It can also run blind **bake-offs** comparing multiple models side by side — that's how
Bedrock/Claude was picked as the winner in the 2026-10 three-way comparison. See the
[appendix](docs/bakeoff.md) if you want to re-run model comparisons later.

## Requirements

For the translation pipeline you need only:

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is provisioned by uv itself)
- An AWS account where Claude is enabled on **Amazon Bedrock**, configured either via SSO
  (`aws sso login --profile <profile>`) or a key (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)

Additional Ollama providers (local Dicta, Ollama Cloud) are only needed for bake-off
comparisons; see the appendix.

## Quick start

```bash
uv sync                                # create .venv and install deps

# Credentials come from the environment; nothing is ever read from targoo.yaml:
aws sso login --profile my-profile     # or export AWS keys directly
export AWS_PROFILE=my-profile          # or omit if your default profile is set up

targoo texts        # list the source passages targoo would translate
targoo translate    # draft final translations with the configured provider
# …edit translations/<id>.txt by hand…
targoo freeze <id>  # approve an edited translation
targoo status       # per-passage state: untranslated / drafted / draft-error / frozen
```

## Adding source texts

The corpus is a directory of plain UTF-8 text files (`texts/` by default):

- **One passage per file.** A passage is the unit of translation and review: a verse, a
  paragraph, a prayer, a psalm — whatever you want to read as one translation at a time.
  Short to medium passages are best; anything over a page or so risks provider timeouts
  (bump the provider's `timeout_seconds` if you go big).
- **The filename is the passage id** — it appears in output filenames, the translation
  memory, and git history, so keep ids stable and human-readable, lowercase-kebab:
  `genesis-1.1-4.txt`, `amidah-avot.txt`. Never put spaces in it. Renaming a file changes
  its id (and would orphan its TM record).
- **The file's entire content is sent to the model.** No comments, headers, or provenance
  notes in the file — record source references in `tm/<id>.yaml`'s `source:` block, or in
  a separate notes file.
- Blank lines are meaningful: line/paragraph structure is preserved in the prompt, so
  separate verses with blank lines if you want that structure honored in the translation.
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

Adding texts is the entry point of the whole pipeline: drop files in, then
`targoo translate`, review, `targoo freeze`. Passages you've already translated are left
alone, so the same command always covers exactly what's new.

## The final-translation pipeline

```
texts/<id>.txt ──translate──▶ tm/<id>.yaml + translations/<id>.txt ──you──▶ edits
                                                                        │
                              frozen record ◀──────────── freeze ◀──────┘
```

1. **`targoo translate`** renders `prompts/final.md` for each passage and sends it to the
   provider named by `final:` in targoo.yaml. Passages that already have a draft are
   skipped (`--force` re-drafts); **frozen passages are never re-drafted** — unfreeze
   first with `targoo freeze <id> --reopen`. A provider failure is recorded for that
   passage and the run continues, so a timeout costs that passage, not the run.
2. **Edit `translations/<id>.txt` by hand.** This file is the review surface — the only
   thing that matters at freeze time is what the file contains when you freeze it. targoo
   doesn't watch or sync it; your edits simply live there until you freeze.
3. **`targoo freeze <id>`** imports the `.txt`'s current contents as the passage's
   `english_frozen` text and appends an `edit_history` entry — "frozen with edits" or
   "frozen unchanged" — dated, with the editor's name.
4. **After freezing:** further edits to the `.txt` are ignored by targoo. To revise a
   frozen passage: `targoo freeze <id> --reopen` → edit → `targoo freeze <id>` again.
   Every reopen and freeze is another `edit_history` entry.

`tm/<id>.yaml` is the **record of truth**: the Hebrew source, the raw model draft, the
frozen English, provenance (provider, model, prompt name + sha256), and `edit_history`.

**Where the diffs live:** `tm/<id>.yaml` stores the draft and the frozen text side by
side, so the human edit is the diff between `draft.text` and `english_frozen`. targoo
itself records only the summary fact ("with edits" / "unchanged") — the full diff is git's
job: the translate commit holds the draft TM record, the freeze commit holds the record
with your text in it, and `git diff` between them is your post-edit, attributed to you.
That's why **`tm/` is committed to git and its history must never be rewritten** — the
history is the authorship trail.

**Cautions:** don't run `translate --force` while you have unreviewed edits in
`translations/*.txt` — it re-drafts and overwrites those files. Freeze early, edit often.

## Configuration

Settings live in `targoo.yaml` in the repo root (override the location with `TARGOO_CONFIG`,
or a per-invocation `--config`). Paths in the config are resolved relative to the config
file's directory, so a project works from any working directory. `targoo init` writes a
fresh starter file.

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
    base_url: https://ollama.com         # Ollama Cloud endpoint (bake-off only)
    model: gemma4:31b-cloud
    api_key_env: OLLAMA_API_KEY          # name of the env var holding the key
    timeout_seconds: 180
  dicta-local:
    kind: ollama
    base_url: http://127.0.0.1:11434     # local daemon (bake-off only)
    model: dicta-il/DictaLM-3.0-1.7B-Thinking:latest    # exact tag from `ollama list`
    timeout_seconds: 900

final: bedrock            # provider that renders final translations via prompts/final.md
judge: bedrock            # provider that grades blind bake-off drafts
```

The pipeline itself needs only the `final:` provider; the Ollama blocks matter for
bake-offs. `judge:` is only consulted by `targoo judge`.

**Secrets are environment-only:** Ollama Cloud keys come from the env var named by
`api_key_env`; Bedrock auth uses the standard AWS chain (`AWS_PROFILE`, SSO, or explicit keys),
so run `aws sso login` first or export keys. See `.env.example` for the full list.

**Verifying Bedrock:** `aws bedrock list-inference-profiles --region <your-region>` shows
the Claude profile ids your account can invoke. Bedrock accounts normally invoke Claude
through cross-region inference profiles (`us.anthropic.claude-*` or `eu.anthropic.claude-*`):
the plain `anthropic.*` model id fails on-demand throughput validation, and the 5.x/Fable ids
can additionally 403 if access wasn't granted to your account. targoo's Bedrock leg talks to
bedrock-runtime, so pass the inference-profile id.

**Adding another provider** is any `kind: ollama` block pointing at a reachable base URL, or
a `kind: bedrock` block with another model id — then set it in `final:` or name it in
`--models`.

## Project layout

```
src/targoo/
├── cli.py            # commands: translate, freeze, status + bake-off suite
├── config.py         # targoo.yaml loading + validation
├── corpus.py         # texts/*.txt → passages with stable ids
├── prompts.py        # Jinja2 rendering of prompts/
├── finalize.py       # final-translation orchestration (draft → edit → freeze)
├── tm.py             # translation-memory documents under tm/
├── bakeoff.py        # blind model-comparison orchestration (appendix)
├── judge.py          # judge pass, JSON parsing, mean-score summary (appendix)
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
docs/bakeoff.md       # appendix: blind bake-off workflow
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