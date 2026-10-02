"""LLM-as-judge pass over a blind bake-off run.

Judging happens letter-blind as well: the judge prompt and the output below
only ever carry the letters assigned in the bake-off, never model names. Use
``targoo inspect-key`` only after judging (and your own review) is done.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .config import Config
from .prompts import render
from .providers import Provider

SCORE_KEYS = ("faithfulness", "fluency", "accuracy")


def render_judge_prompt(config: Config, source: str, draft: str) -> str:
    return render(
        Path(config.prompts_dir) / "judge.md",
        source=source,
        draft=draft,
    )


def parse_judgment(raw: str) -> dict | None:
    """Parse the judge's JSON answer; None when the answer is unusable."""
    text = raw.strip()
    # Tolerate a fenced code block, even with a language tag.
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"```\s*$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    judgment: dict = {}
    for key in SCORE_KEYS:
        try:
            value = int(data[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not 1 <= value <= 5:
            return None
        judgment[key] = value
    notes = data.get("notes")
    judgment["notes"] = notes.strip() if isinstance(notes, str) else ""
    return judgment


def run_judge(config: Config, run_dir: str | Path, judge_provider: Provider) -> dict:
    run_dir = Path(run_dir)
    drafts_file = run_dir / "drafts.yaml"
    if not drafts_file.is_file():
        raise FileNotFoundError(
            f"no drafts.yaml in {run_dir} — point --run at a bake-off run directory"
        )
    drafts = yaml.safe_load(drafts_file.read_text(encoding="utf-8"))
    scored: dict[str, dict] = {}
    failures: list[str] = []

    for passage_id, entry in drafts["passages"].items():
        scored[passage_id] = {}
        for letter, draft in sorted(entry["drafts"].items()):
            prompt = render_judge_prompt(config, entry["source"], draft["text"])
            completion = judge_provider.complete(system="", user=prompt)
            judgment = parse_judgment(completion.text)
            if judgment is None:
                failures.append(f"{passage_id}/{letter}")
            scored[passage_id][letter] = judgment or {"error": "unparseable judge output"}

    judgment_doc = {"judge": f"{judge_provider.name} ({judge_provider.model})", "scored": scored}
    (run_dir / "judgments.yaml").write_text(
        yaml.safe_dump(judgment_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    summary = summarize(scored)
    return summary


def summarize(scored: dict[str, dict]) -> list[dict]:
    """Per-letter mean scores across passages; returns rows for CLI printing."""
    rows = []
    for letter in sorted({letter for passage in scored.values() for letter in passage}):
        values: dict[str, list[float]] = {}
        counted = 0
        for entry in scored.values():
            judgment = entry.get(letter)
            if not judgment or "error" in judgment:
                continue
            counted += 1
            for key in SCORE_KEYS:
                values.setdefault(key, []).append(judgment[key])
        means = {key: round(sum(v) / len(v), 2) for key, v in values.items()}
        overall = round(sum(means.values()) / len(means), 2) if means else 0.0
        rows.append(
            {
                "letter": letter,
                "passages": counted,
                **{key: means.get(key, 0.0) for key in SCORE_KEYS},
                "average": overall,
            }
        )
    return rows