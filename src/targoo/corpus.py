"""Loading the source-text corpus from a plain directory of .txt files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError


@dataclass(frozen=True)
class Passage:
    id: str
    source: str

    @property
    def hebrew(self) -> bool:
        """True when the source contains Hebrew-script characters."""
        return any("֐" <= char <= "׿" for char in self.source)


def load_passages(texts_dir: str | Path) -> list[Passage]:
    """Load one passage per ``<texts_dir>/*.txt`` file, sorted by passage id.

    The filename stem is the stable passage id, so renaming a file changes its
    id. Empty files are rejected: they would silently produce empty drafts.
    """
    directory = Path(texts_dir)
    if not directory.is_dir():
        raise ConfigError(
            f"texts directory not found: {directory} "
            f"(create it and add one .txt file per passage — see README)"
        )
    files = sorted(directory.glob("*.txt"))
    if not files:
        raise ConfigError(
            f"no .txt files in {directory} — add one file per passage, "
            f"e.g. texts/genesis-1.txt (the filename becomes the passage id)"
        )
    passages = []
    for file in files:
        source = file.read_text(encoding="utf-8").strip()
        if not source:
            raise ConfigError(f"empty source text: {file}")
        passages.append(Passage(id=file.stem, source=source))
    return passages