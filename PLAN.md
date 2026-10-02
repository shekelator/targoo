# targoo — Hebrew→English Translation Engine — Build Plan

> **Goal:** Deterministic, git-versioned translation pipeline for the siddur — translation
> memory (TM) as YAML in git, style guide + glossary + exemplar bank as versioned data,
> frontier LLM via API for drafts only. No agent framework in the core.
>
> **Architecture:** Passage inventory with stable IDs → TM lookup (hit = frozen approved
> text; miss = draft call → David post-edits → approve → freeze). Consistency is a pipeline
> invariant, not a model property. Implements
> [[Translation Engine — Research & Recommendations]] Phases 0–3.
>
> **Tech stack:** Python 3.12 · uv · typer CLI · PyYAML · rapidfuzz · anthropic/openai/
> google-genai SDKs behind a thin provider protocol · pytest · pre-commit · GitHub Actions.
> SQLite intentionally deferred (YAGNI at siddur scale); no Strands/LangChain in the core.

---

## Repo layout

```
targoo/
├── pyproject.toml              # uv-managed; console script: targoo
├── README.md                   # maps each phase → module; quick-start
├── .gitignore                  # .venv, __pycache__, .env (NEVER commit keys)
├── .pre-commit-config.yaml     # ruff + ruff-format + yaml check
├── .github/workflows/ci.yml    # pytest + audit on push
├── style/
│   ├── style.md                # v1: register, Divine Name, You/you, line rules
│   ├── glossary.yaml           # term → rendering + rationale + status
│   └── exemplars/              # approved pairs (seed ~20 at Phase 2)
├── prompts/
│   └── draft.md                # Jinja2 template (style vN + glossary + exemplars)
├── passages/
│   ├── bakeoff-set.yaml        # Phase 0/1: 20–30 passages w/ IDs + hebrew + source
│   └── amidah.avot.weekday.yaml  # TM: one file per passage ID (this shape:)
│       #   passage_id: amidah.avot.weekday
│       #   hebrew: <pointed text>
│       #   english_approved: null        # null = not yet frozen
│       #   style_version: 1
│       #   draft: {model, prompt_version, temperature, raw_output, date}
│       #   edit_history: [{date, editor, change}]
│       #   source: {ref, url, license}   # Sefaria CC-BY preferred over CC-BY-SA
├── src/targoo/
│   ├── cli.py                  # bakeoff | draft | review | audit | assemble
│   ├── tm.py                   # load/lookup/write TM files, schema validation
│   ├── style.py                # assemble style block (guide+glossary versioned)
│   ├── exemplars.py            # rapidfuzz/TF-IDF nearest-approved retrieval
│   ├── providers/
│   │   ├── base.py             # DraftProvider protocol: translate(text, ctx) → str
│   │   ├── anthropic_p.py      # temp ≤ 0.2, no commentary, breaks preserved
│   │   ├── openai_p.py
│   │   └── google_p.py         # paid tier only
│   ├── audit.py                # repeated Hebrew spans → divergent English; report
│   └── assemble.py             # TM export → markup for the book pipeline
└── tests/
    ├── test_tm.py
    ├── test_exemplars.py
    └── test_audit.py
```

## Tasks (in order; TDD where code-bearing, commit after each)

1. **Scaffold** — `uv init targoo`, add deps (`typer pyyaml rapidfuzz jinja2 anthropic
   openai google-genai pytest`), repo layout above, `git init`, first commit.
2. **TM module (TDD)** — `tm.py`: parse/validate a passage YAML; `lookup(id)` returns
   approved English or None; writer round-trips. Test with
   `tests/test_tm.py::test_roundtrip_and_lookup`.
3. **Style assembler** — `style.py`: reads style.md (frontmatter version) + glossary.yaml
   → single prompt block; version bump visible in output. Test: version string appears.
4. **Exemplar retrieval (TDD)** — `exemplars.py`: given Hebrew text, return top-5 similar
   approved passages (rapidfuzz on normalized Hebrew). Test: seeded corpus ordering.
5. **Providers** — `base.py` protocol + 3 adapters; each caps temp ≤ 0.2, strips
   whitespace-only echo, forbids commentary in system prompt. Secrets via env only.
6. **Bake-off CLI** — `targoo bakeoff --set passages/bakeoff-set.yaml --models a,b,c`
   → anonymized blind output (A/B/C labels, model map in `bakeoff-key.yaml` you keep out of the review view). Phase 1 deliverable.
7. **Draft + review CLI** — `targoo draft <id>` skips if TM hit; writes draft + prompt
   fingerprint into the passage file. `targoo review <id> --file edits.md` applies your
   post-edit to `english_approved` + logs edit_history; freeze rule enforced
   (approved passages reject re-draft without `--reopen`).
8. **Audit** — `audit.py`: normalized repeated Hebrew spans across passages → flag
   divergent English; also glossary-violation scan. `targoo audit` exit 1 on findings
   (wired into CI).
9. **Assemble** — export approved TM → the markup format the siddur book pipeline
   consumes (coordinate with mechudeshet plan before coding this).

## Milestone mapping

- Phase 0/1 (corpus probe + bake-off) = Tasks 1–6 → deck the 20–30 picks, run blind.
- Phase 2 (scaffold + style v1 + glossary v0 + exemplars) = Tasks 7 + fill style/.
- Phase 3 (production + post-edit loop) = Tasks 8–9.
- Phase 4 (LoRA fine-tune, Qwen3-8B/DictaLM-3.0) = out of scope; only if TM+prompting
  demonstrably can't hold style. Local model slot-in later via an Ollama provider.

## First commands

```bash
cd ~/source/targoo          # after you've moved this plan in
uv venv && uv sync
git init && git add -A && git commit -m "chore: scaffold targoo translation engine"
gh repo create targoo --private --source=. --push
```

Ownership note carried over: TM git history IS the authorship-evidence trail (USCO Part 2)
— keep edit_history populated, never rewrite history on approved passages.

*Generated 2026-10-01 from `Projects/Ruach Siddur Refresh/Translation Engine — Research & Recommendations.md`. Stack decision: Python + thin adapters over Strands-for-core (Strands acceptable later as interactive wrapper).*