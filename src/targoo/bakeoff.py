"""Blind bake-off orchestration.

Runs every passage through every selected provider, then writes the drafts
anonymized: letters (A, B, C, …) assigned per passage in random order. The
mapping lives only in ``bakeoff-key.yaml`` inside the run directory, which the
reviewer deliberately does not open while the reviews are blind.
"""

from __future__ import annotations

import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

import yaml

from .config import Config
from .corpus import Passage, load_passages
from .prompts import render
from .providers import Provider, ProviderError

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Stored in artifacts when a draft call fails. Deliberately opaque so the
# artifacts stay blind; the full error goes to stderr for the operator.
_DRAFT_ERROR = "provider call failed (see terminal output)"


def render_draft_prompt(config: Config, passage: Passage) -> str:
    return render(Path(config.prompts_dir) / "draft.md", source=passage.source)


def run_bakeoff(
    config: Config,
    providers: dict[str, Provider],
    run_name: str | None = None,
    seed: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Translate every passage with every provider; returns the run directory.

    Progress notes print letters only — never provider names — so the terminal
    history stays blind too. Results are written after every passage and a
    failing provider call costs only its own draft, so a slow provider that
    times out doesn't destroys the run's other results.
    """
    progress = progress or (lambda _message: None)
    if not providers:
        raise ValueError("no providers selected")
    if len(providers) > len(LETTERS):
        raise ValueError(f"at most {len(LETTERS)} providers can be anonymized")
    passages = load_passages(config.texts_dir)

    if run_name is None:
        run_name = "bakeoff-" + time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(config.outputs_dir) / run_name

    drafts_prompt = {
        passage.id: render_draft_prompt(config, passage) for passage in passages
    }

    rng = random.Random(seed)
    # Assign all letters up front and write the key file before the first
    # model call: even an abandoned run leaves a mapping to trace later runs.
    assignments: dict[str, dict[str, str]] = {}
    for passage in passages:
        order = list(providers)
        rng.shuffle(order)
        assignments[passage.id] = {
            provider_name: LETTERS[i] for i, provider_name in enumerate(order)
        }
    key = {
        passage_id: {letter: name for name, letter in letters.items()}
        for passage_id, letters in assignments.items()
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    passages_dir = run_dir / "passages"
    passages_dir.mkdir(exist_ok=True)
    (run_dir / "bakeoff-key.yaml").write_text(
        yaml.safe_dump({"seed": seed, "key": key}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    drafts: dict[str, dict] = {
        "seed": seed,
        "temperature": config.temperature,
        "passages": {},
    }
    failures: list[str] = []
    for passage in passages:
        letters = assignments[passage.id]
        progress(f"translating {passage.id} ({'he' if passage.hebrew else '??'})")

        passage_drafts: dict[str, dict] = {}
        for provider_name, letter in letters.items():
            started = time.monotonic()
            try:
                completion = providers[provider_name].complete(
                    system="", user=drafts_prompt[passage.id]
                )
            except ProviderError as e:
                print(
                    f"warning: draft {passage.id}/{letter} failed: {e}",
                    file=sys.stderr,
                )
                passage_drafts[letter] = {"error": _DRAFT_ERROR}
                failures.append(f"{passage.id}/{letter}")
                continue
            seconds = round(time.monotonic() - started, 3)
            passage_drafts[letter] = {
                "text": completion.text,
                "seconds": seconds,
            }
            progress(f"  draft {letter}: {seconds:.1f}s, {len(completion.text)} chars")
        drafts["passages"][passage.id] = {"source": passage.source, "drafts": passage_drafts}

        # Write after every passage so completed work survives a later failure.
        (run_dir / "drafts.yaml").write_text(
            yaml.safe_dump(drafts, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (passages_dir / f"{passage.id}.md").write_text(
            _render_passage_markdown(passage, passage_drafts),
            encoding="utf-8",
        )

    if failures:
        progress(
            f"note: {len(failures)} draft(s) failed — see stderr; completed drafts are in {run_dir}"
        )
    else:
        progress(f"all drafts written to {run_dir}")
    return run_dir


def _render_passage_markdown(passage: Passage, drafts: dict[str, dict]) -> str:
    lines = [f"# {passage.id}", "", "## Source", "", passage.source, ""]
    for letter in sorted(drafts):
        entry = drafts[letter]
        if "text" in entry:
            body = entry["text"].strip()
        else:
            body = f"*(this draft is missing: {entry['error']})*"
        lines += [f"## Draft {letter}", "", body, ""]
    return "\n".join(lines)