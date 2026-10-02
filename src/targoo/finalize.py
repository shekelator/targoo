"""Final-translation orchestration: draft → human post-edit → freeze.

One provider (by default the one named by ``config.final``) renders each
corpus passage through ``prompts/final.md`` into a translation-memory
document under ``tm/``, plus a plain-text export under ``translations/``
for the human post-edit. ``freeze`` imports the (possibly edited) export
back into the TM record. Everything is written incrementally: a provider
timeout costs its own passage, never the run.
"""

from __future__ import annotations

import datetime as _dt
import sys
from collections.abc import Callable
from pathlib import Path

from .config import Config
from .corpus import load_passages
from .prompts import render
from .providers import Provider, ProviderError
from .tm import load_all_tm, load_tm, make_document, prompt_fingerprint, write_tm

_DRAFT_ERROR = "provider call failed (see terminal output)"


def export_path(config: Config, passage_id: str) -> Path:
    return Path(config.translations_dir) / f"{passage_id}.txt"


def _current_text(doc: dict) -> str | None:
    """The English text to export: frozen when frozen, else the draft."""
    if doc.get("english_frozen"):
        return doc["english_frozen"]
    return None if "error" in (doc.get("draft") or {}) else (doc["draft"].get("text"))


def _write_text(config: Config, doc: dict) -> None:
    """Export the current English text for reading and for post-editing."""
    text = _current_text(doc)
    if text is None:
        return
    path = export_path(config, doc["passage_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def run_translate(
    config: Config,
    provider: Provider,
    progress: Callable[[str], None] | None = None,
    ids: str | None = None,
    force: bool = False,
) -> dict:
    """Draft every untranslated passage through the final prompt into ``tm/``.

    Already-drafted passages are skipped unless ``force``; frozen passages are
    always skipped (the freeze rule: re-drafting an approved text requires
    ``--reopen`` first). A provider failure is recorded for that passage and
    the run continues.
    """
    progress = progress or (lambda _message: None)

    wanted = [item.strip() for item in ids.split(",") if item.strip()] if ids else None
    passages = load_passages(config.texts_dir)
    if wanted:
        known = {passage.id: passage for passage in passages}
        unknown = sorted(set(wanted) - set(known))
        if unknown:
            raise ValueError(
                f"unknown passage id(s) {sorted(unknown)} — passages available: {sorted(known)}"
            )
        passages = [known[wanted_id] for wanted_id in wanted]

    prompt_path = Path(config.prompts_dir) / "final.md"
    fingerprint = prompt_fingerprint(prompt_path)

    stats = {"drafted": 0, "redrafted": 0, "skipped": 0, "failed": 0, "frozen": 0}
    for passage in passages:
        existing = load_tm(config.tm_dir, passage.id)
        if existing is not None:
            if existing.get("english_frozen") is not None:
                stats["frozen"] += 1
                progress(f"skipping {passage.id} (frozen)")
                continue
            if existing.get("draft", {}).get("text") is not None and not force:
                stats["skipped"] += 1
                progress(f"skipping {passage.id} (already drafted; rerun with --force)")
                continue

        progress(f"translating {passage.id}")
        user_prompt = render(prompt_path, source=passage.source)
        try:
            completion = provider.complete(system="", user=user_prompt)
        except ProviderError as e:
            # Failures go to stderr; the TM record stores only the opaque marker.
            print(f"warning: translation {passage.id} failed: {e}", file=sys.stderr)
            stats["failed"] += 1
            doc = existing if existing is not None else make_document(
                passage, provider.name, provider.model, fingerprint, ""
            )
            doc["draft"] = {
                "provider": provider.name,
                "model": provider.model,
                "prompt": dict(fingerprint),
                "error": _DRAFT_ERROR,
            }
            write_tm(config.tm_dir, doc)
            continue

        if existing is not None:
            doc = existing
            doc.setdefault("draft", {})
            stats["redrafted"] += 1
        else:
            doc = make_document(
                passage, provider.name, provider.model, fingerprint, completion.text
            )
            stats["drafted"] += 1
        doc["draft"] = {
            "provider": provider.name,
            "model": provider.model,
            "prompt": dict(fingerprint),
            "text": completion.text,
        }
        write_tm(config.tm_dir, doc)
        _write_text(config, doc)
        progress(f"  ok: {len(completion.text)} chars -> {export_path(config, passage.id)}")

    progress(
        f"done: {stats['drafted']} drafted, {stats['redrafted']} redrafted, "
        f"{stats['skipped']} skipped, {stats['failed']} failed, {stats['frozen']} frozen"
    )
    return stats


def freeze(config: Config, passage_id: str, editor: str = "dave", reopen: bool = False) -> dict:
    """Import the (possibly edited) ``translations/<id>.txt`` into the TM as approved.

    Requires the passage to have a draft and a txt export. Refuses to re-freeze
    without ``--reopen``; reopening records an entry in ``edit_history`` so the
    approved-then-reopened history stays visible. Never touches the txt itself.
    """
    doc = load_tm(config.tm_dir, passage_id)
    if doc is None:
        raise ValueError(
            f"no translation for {passage_id!r} — run `targoo translate --ids {passage_id}` first"
        )
    txt_file = export_path(config, passage_id)
    if not txt_file.is_file():
        raise FileNotFoundError(
            f"{txt_file} not found — the .txt export is the review surface; "
            f"restore or export it before freezing"
        )

    today = _dt.date.today().isoformat()
    history = doc.setdefault("edit_history", [])
    if reopen:
        history.append({"date": today, "editor": editor, "change": "reopened for editing"})
        doc["english_frozen"] = None
        write_tm(config.tm_dir, doc)
        return doc

    if doc.get("english_frozen") is not None:
        raise ValueError(f"{passage_id!r} is already frozen — rerun with --reopen to unfreeze")

    edited = txt_file.read_text(encoding="utf-8").strip()
    if not edited:
        raise ValueError(f"{txt_file} is empty — nothing to freeze")
    doc["english_frozen"] = edited
    previous = (doc.get("draft") or {}).get("text") or ""
    change = "frozen with edits" if edited != previous.strip() else "frozen unchanged"
    history.append({"date": today, "editor": editor, "change": change})
    write_tm(config.tm_dir, doc)
    return doc


def status(config: Config) -> list[dict]:
    """Per-passage state: untranslated / drafted / draft-error / frozen."""
    rows = []
    tm_docs = load_all_tm(config.tm_dir)
    for passage in load_passages(config.texts_dir):
        doc = tm_docs.get(passage.id)
        if doc is None:
            state = "untranslated"
        elif doc.get("english_frozen") is not None:
            state = "frozen"
        elif (doc.get("draft") or {}).get("error"):
            state = "draft-error"
        elif (doc.get("draft") or {}).get("text"):
            state = "drafted"
        else:
            state = "untranslated"
        rows.append({"id": passage.id, "state": state})
    return rows