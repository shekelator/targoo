"""Jinja2 rendering of the prompt templates under prompts/."""

from __future__ import annotations

from pathlib import Path

import jinja2

_environment = jinja2.Environment(
    undefined=jinja2.StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,
)


def render(template_path: str | Path, **variables: object) -> str:
    file = Path(template_path)
    if not file.is_file():
        raise FileNotFoundError(f"prompt template not found: {file}")
    return _environment.from_string(file.read_text(encoding="utf-8")).render(**variables)