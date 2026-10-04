# Appendix: the blind bake-off

The main pipeline needs exactly one good provider; the bake-off is for deciding *which*
one, and for re-checking that decision later (new provider, revised prompt, a new model
release). It is kept as a secondary tool — commands unchanged, fully tested.

The bake-off ran once, in 2026-10, over eight passages: Bedrock (Claude sonnet-4-6) won
decisively against ollama-cloud (Gemma 31B) and dicta-local (DictaLM 3.0), confirmed by
both the blind LLM judge and a blind human review.

## How it stays blind

For every passage, the providers are assigned letters `A`/`B`/`C` in random order. The
mapping lives only in `outputs/<run>/bakeoff-key.yaml`: outputs, judge prompts, and even
terminal progress carry letters only. `outputs/` is gitignored so the key can't leak into
a commit by accident. Letters are freshly shuffled per passage (unless seeded with
`--seed`), so "A" is not the same model in every file.

## Running one

```bash
export OLLAMA_API_KEY=sk-...          # only if an ollama-cloud provider participates
targoo bakeoff                                  # all configured providers
targoo bakeoff --models dicta-local,ollama-cloud
targoo bakeoff --run-name amidah-avot --seed 42 # reproducible letter assignment
set -a; source .env; set +a                     # AWS + key env vars, if kept in .env
```

Each run writes:

```
outputs/<run-name>/
├── bakeoff-key.yaml    # letter → model map — DON'T open while reviewing
├── drafts.yaml         # machine-readable blind drafts (letter-keyed)
├── judgments.yaml      # written by `targoo judge`
└── passages/
    └── genesis-1.1-4.md   # the source + Draft A / Draft B / Draft C
```

Per-passage artifacts are written after each passage and a failing provider call costs
only its own draft (recorded as a missing draft), so a slow local model timing out never
destroys the rest of the run.

## Reviewing and judging

1. `targoo bakeoff` → read `outputs/<run>/passages/*.md` and rank the drafts per passage
   while still blind (add a `## My review` section to the file — ranks plus concrete
   notes like "added a phrase", "dropped a clause").
2. Run the judge with the provider named by `judge:`:

   ```bash
   targoo judge --run outputs/<run>
   ```

   It scores each blind draft on **faithfulness**, **fluency**, and **accuracy** (1–5)
   with written notes, and prints a mean table per letter. Unparseable judge output is
   recorded as an error, not scores.
3. `targoo inspect-key outputs/<run>` — only now reveal the letter→model map and reconcile
   the judge's letters with your own rankings.

Two things to know about the judge:

- It is blind by construction (it receives letters, never provider names) — but it is
  still another LLM. If it judges its own provider family, there's a self-preference risk;
  the mitigation that matters is your own blind read, which is the deciding vote.
- Judge means over only a handful of passages are noisy; treat them as triage, not a
  verdict.

## When to re-run

- A new provider or a promising model you want to try before adding to the pipeline.
- A revised `prompts/draft.md` — compare prompt revisions the same way.
- Any time the "which model" decision needs fresh evidence instead of a vibe.