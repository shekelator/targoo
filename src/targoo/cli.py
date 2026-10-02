"""targoo CLI — bake-off, judge, texts, inspect-key, init."""

from __future__ import annotations

from pathlib import Path

import typer

from . import bakeoff as bakeoff_mod
from . import judge as judge_mod
from .config import DEFAULT_PROFILES, ConfigError, load_config
from .corpus import load_passages
from .providers import ProviderError, build_providers

app = typer.Typer(
    help="Bake-off harness for Hebrew→English LLM translation.",
    no_args_is_help=True,
)


def _config(path_option: str):
    try:
        return load_config(path_option or None)
    except (ConfigError, FileNotFoundError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing targoo.yaml."),
) -> None:
    """Write a starter targoo.yaml in the current directory."""
    file = Path.cwd() / "targoo.yaml"
    if file.is_file() and not force:
        typer.echo(f"{file} already exists — rerun with --force to overwrite", err=True)
        raise typer.Exit(code=1)
    file.write_text(DEFAULT_PROFILES, encoding="utf-8")
    typer.echo(f"wrote {file} — edit it to match your providers, then run `targoo texts`")


@app.command()
def texts(
    config_path: str = typer.Option(
        "", "--config", help="Path to targoo.yaml (default: ./targoo.yaml or $TARGOO_CONFIG)."
    ),
) -> None:
    """List the source texts that would be translated, one per .txt file."""
    config = _config(config_path)
    try:
        passages = load_passages(config.texts_dir)
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    for passage in passages:
        lines = passage.source.count("\n") + 1
        lang = "he" if passage.hebrew else "??"
        typer.echo(f"{passage.id}\t{lang}\t{lines} lines\t{len(passage.source)} chars")


@app.command()
def bakeoff(
    models: str = typer.Option(
        "", "--models", help="Comma-separated providers to run (default: all in targoo.yaml)."
    ),
    run_name: str = typer.Option("", "--run-name", help="Run directory name under outputs/."),
    seed: int = typer.Option(None, "--seed", help="Seed the letter shuffle for reproducible runs."),
    config_path: str = typer.Option(
        "", "--config", help="Path to targoo.yaml (default: ./targoo.yaml or $TARGOO_CONFIG)."
    ),
) -> None:
    """Translate every source text with every provider and write drafts anonymized as A/B/C."""
    config = _config(config_path)
    names = [name.strip() for name in models.split(",") if name.strip()] or None
    try:
        providers = build_providers(config, names)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"models selected: {sorted(providers)}")
    try:
        run_dir = bakeoff_mod.run_bakeoff(
            config,
            providers,
            run_name or None,
            seed,
            progress=lambda message: typer.echo(message),
        )
    except (ConfigError, FileNotFoundError, ValueError, ProviderError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"\nwrote {run_dir}")
    typer.echo("review the drafts blind; the letter→model map is in bakeoff-key.yaml "
               "(don't peek yet)")


@app.command()
def judge(
    run: str = typer.Option(..., "--run", help="Bake-off run directory under outputs/."),
    judge_provider: str = typer.Option(
        "", "--judge", help="Provider to judge with (default: config.judge)."
    ),
    config_path: str = typer.Option(
        "", "--config", help="Path to targoo.yaml (default: ./targoo.yaml or $TARGOO_CONFIG)."
    ),
) -> None:
    """Score each blind draft against its source; writes judgments.yaml and prints means."""
    config = _config(config_path)
    provider_name = judge_provider or config.judge
    if not provider_name:
        typer.echo(
            "error: no judge configured — set `judge:` in targoo.yaml or pass --judge <provider>",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        providers = build_providers(config, [provider_name], temperature=0.0)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    try:
        summary = judge_mod.run_judge(config, run, providers[provider_name])
    except (FileNotFoundError, ConfigError, ProviderError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e

    header = f"{'letter':<8}{'passages':<10}" + "".join(
        f"{key:<14}" for key in ("faithfulness", "fluency", "accuracy")
    ) + "average"
    typer.echo("")
    typer.echo("Mean scores across the run (blind: letters, judge only saw letters):\n")
    typer.echo(header)
    for row in summary:
        typer.echo(
            f"{row['letter']:<8}{row['passages']:<10}"
            f"{row['faithfulness']:<14}{row['fluency']:<14}{row['accuracy']:<14}{row['average']:<8}"
        )
    typer.echo("\nfull judgments in judgments.yaml; reveal letters with `targoo inspect-key`")


@app.command()
def inspect_key(
    run: str = typer.Argument(..., help="Bake-off run directory under outputs/."),
) -> None:
    """Reveal the letter→model mapping for a finished bake-off run."""
    key_file = Path(run) / "bakeoff-key.yaml"
    if not key_file.is_file():
        typer.echo(f"error: {key_file} not found", err=True)
        raise typer.Exit(code=1)
    typer.echo(key_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()