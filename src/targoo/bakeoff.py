"""Blind bake-off orchestration.

Runs every passage through every selected provider, then writes the drafts
anonymized: letters (A, B, C, …) assigned per passage in random order. The
mapping lives only in ``bakeoff-key.yaml`` inside the run directory, which the
reviewer deliberately does not open while the reviews are blind.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from pathlib import Path

import yaml

from .config import Config
from .corpus import Passage, load_passages
from .prompts import render
from .providers import Provider

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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
    history stays blind too.
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
    key: dict[str, dict[str, str]] = {}
    drafts: dict[str, dict] = {
        "seed": seed,
        "temperature": config.temperature,
        "passages": {},
    }
    for passage in passages:
        progress(f"translating {passage.id} ({passage.hebrew and 'he' or '??'})")
        order = list(providers)
        rng.shuffle(order)
        letters = {provider_name: LETTERS[i] for i, provider_name in enumerate(order)}
        # The key map reads letter → provider so blind artifacts can reference it.
        key[passage.id] = {letter: name for name, letter in letters.items()}

        passage_drafts: dict[str, dict] = {}
        for provider_name in order:
            letter = letters[provider_name]
            started = time.monotonic()
            completion = providers[provider_name].complete(
                system="", user=drafts_prompt[passage.id]
            )
            seconds = round(time.monotonic() - started, 3)
            passage_drafts[letter] = {
                "text": completion.text,
                "seconds": seconds,
            }
            progress(f"  draft {letter}: {seconds:.1f}s, {len(completion.text)} chars")
        drafts["passages"][passage.id] = {"source": passage.source, "drafts": passage_drafts}

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "bakeoff-key.yaml").write_text(
        yaml.safe_dump({"seed": seed, "key": key}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (run_dir / "drafts.yaml").write_text(
        yaml.safe_dump(drafts, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    passages_dir = run_dir / "passages"
    passages_dir.mkdir(exist_ok=True)
    for passage in passages:
        (passages_dir / f"{passage.id}.md").write_text(
            _render_passage_markdown(passage, drafts["passages"][passage.id]["drafts"]),
            encoding="utf-8",
        )
    return run_dir


def _render_passage_markdown(passage: Passage, drafts: dict[str, dict]) -> str:
    lines = [f"# {passage.id}", "", "## Source", "", passage.source, ""]
    for letter in sorted(drafts):
        lines += [f"## Draft {letter}", "", drafts[letter]["text"].strip(), ""]
    return "\n".join(lines)