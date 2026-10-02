"""Translation-memory records: one YAML file per passage under ``tm/``.

The TM is the record of truth for a passage's English text and its provenance.
Unlike ``outputs/`` these files are committed to git and their history is the
authorship trail — don't rewrite history on frozen documents.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .config import ConfigError
from .corpus import Passage

STYLE_VERSION = 1


def prompt_fingerprint(prompt_path: str | Path) -> dict:
    """Name/sha256/path of a prompt template, for provenance in TM records."""
    path = Path(prompt_path)
    if not path.is_file():
        raise ConfigError(f"prompt template not found: {path}")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"name": path.stem, "sha256": sha, "path": str(path)}


def make_document(
    passage: Passage,
    provider_name: str,
    provider_model: str,
    prompt: dict,
    text: str,
    source: dict | None = None,
) -> dict:
    """A fresh TM document for a passage that has just been drafted."""
    return {
        "passage_id": passage.id,
        "style_version": STYLE_VERSION,
        "hebrew": passage.source,
        "draft": {
            "provider": provider_name,
            "model": provider_model,
            "prompt": dict(prompt),
            "text": text,
        },
        "english_frozen": None,
        "edit_history": [],
        "source": dict(source or {}),
    }


def write_tm(tm_dir: str | Path, doc: dict) -> Path:
    directory = Path(tm_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / f"{doc['passage_id']}.yaml"
    file.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return file


def load_tm(tm_dir: str | Path, passage_id: str) -> dict | None:
    """One TM document, or ``None`` when the passage hasn't been translated yet."""
    file = Path(tm_dir) / f"{passage_id}.yaml"
    if not file.is_file():
        return None
    try:
        doc = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"could not parse {file}: {e}") from e
    if not isinstance(doc, dict) or "passage_id" not in doc:
        raise ConfigError(f"{file} is not a translation-memory document (need passage_id)")
    return doc


def load_all_tm(tm_dir: str | Path) -> dict[str, dict]:
    """All TM documents, keyed and sorted by passage id."""
    directory = Path(tm_dir)
    docs: dict[str, dict] = {}
    if not directory.is_dir():
        return docs
    for file in sorted(directory.glob("*.yaml")):
        try:
            doc = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ConfigError(f"could not parse {file}: {e}") from e
        if not isinstance(doc, dict) or "passage_id" not in doc:
            raise ConfigError(f"{file} is not a translation-memory document (need passage_id)")
        docs[str(doc["passage_id"])] = doc
    return docs