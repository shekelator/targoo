"""Provider settings for the bake-off.

Secrets never live in the config file: the Ollama Cloud key comes from the
environment (see ``api_key_env``) and Bedrock uses the standard AWS credential
chain (``AWS_PROFILE``/``AWS_ACCESS_KEY_ID``/``aws sso login``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_FILE = "targoo.yaml"

DEFAULT_PROFILES = """\
# Provider settings for the bake-off. Never put secrets in this file.
temperature: 0.2          # draft sampling temperature (kept at or below 0.2)
max_tokens: 8000          # draft output ceiling per passage

providers:
  bedrock:
    kind: bedrock         # Claude on AWS via Bedrock
    model: anthropic.claude-opus-5-5
    aws_region: us-east-1 # set to a region where Claude is enabled for your account

  ollama-cloud:
    kind: ollama          # Ollama Cloud (https://ollama.com / https://ollama.org)
    base_url: https://ollama.com
    model: gemma4:cloud
    api_key_env: OLLAMA_API_KEY
    timeout_seconds: 180

  dicta-local:
    kind: ollama          # local Ollama daemon
    base_url: http://127.0.0.1:11434
    model: dictalm-3.0    # run `ollama list` and use the exact tag here
    timeout_seconds: 300

# Provider that judges the drafts. It only ever sees letter labels (A/B/C),
# never model names, so the judge stays blind too.
judge: bedrock
"""


@dataclass
class OllamaProviderConfig:
    base_url: str = ""
    model: str = ""
    api_key_env: str = "OLLAMA_API_KEY"
    timeout_seconds: int = 120

    kind = "ollama"


@dataclass
class BedrockProviderConfig:
    model: str = ""
    aws_region: str = "us-east-1"
    aws_profile: str = ""

    kind = "bedrock"


@dataclass
class Config:
    temperature: float = 0.2
    max_tokens: int = 8000
    judge: str | None = None
    texts_dir: str = "texts"
    prompts_dir: str = "prompts"
    outputs_dir: str = "outputs"
    providers: dict[str, OllamaProviderConfig | BedrockProviderConfig] = field(
        default_factory=dict
    )


class ConfigError(ValueError):
    pass


def config_path(path: str | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("TARGOO_CONFIG", "").strip()
    if env:
        return Path(env)
    return Path.cwd() / DEFAULT_CONFIG_FILE


def load_config(path: str | None = None) -> Config:
    file = config_path(path)
    if not file.is_file():
        raise ConfigError(
            f"config file not found: {file}\n"
            f"Run `targoo init` to write a starter targoo.yaml, or point "
            f"TARGOO_CONFIG at an existing one."
        )
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"could not parse {file}: {e}") from e

    config = Config()

    if "temperature" in raw:
        config.temperature = float(raw["temperature"])
    if "max_tokens" in raw:
        config.max_tokens = int(raw["max_tokens"])
    if "judge" in raw:
        config.judge = raw["judge"] or None
    if "texts_dir" in raw:
        config.texts_dir = raw["texts_dir"]
    if "prompts_dir" in raw:
        config.prompts_dir = raw["prompts_dir"]
    if "outputs_dir" in raw:
        config.outputs_dir = raw["outputs_dir"]

    for name, entry in (raw.get("providers") or {}).items():
        config.providers[str(name)] = _parse_provider(name, entry or {})

    if not config.providers:
        raise ConfigError("no providers configured in targoo.yaml")

    if config.judge and config.judge not in config.providers:
        raise ConfigError(
            f"config.judge names {config.judge!r} but providers only have "
            f"{sorted(config.providers)}"
        )

    return config


def _parse_provider(name: str, entry: dict) -> OllamaProviderConfig | BedrockProviderConfig:
    kind = str(entry.get("kind") or "").lower()
    if kind == "ollama":
        cfg = OllamaProviderConfig(
            base_url=str(entry.get("base_url") or ""),
            model=str(entry.get("model") or ""),
            api_key_env=str(entry.get("api_key_env") or "OLLAMA_API_KEY"),
            timeout_seconds=int(entry.get("timeout_seconds") or 120),
        )
        if not cfg.base_url:
            raise ConfigError(f"providers.{name}: base_url is required")
        if not cfg.model:
            raise ConfigError(f"providers.{name}: model is required")
        return cfg
    if kind == "bedrock":
        cfg = BedrockProviderConfig(
            model=str(entry.get("model") or ""),
            aws_region=str(entry.get("aws_region") or "us-east-1"),
            aws_profile=str(entry.get("aws_profile") or ""),
        )
        if not cfg.model:
            raise ConfigError(f"providers.{name}: model is required")
        return cfg
    raise ConfigError(
        f"providers.{name}: unsupported kind {entry.get('kind')!r} (want 'ollama' or 'bedrock')"
    )