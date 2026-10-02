"""Provider implementations and the factory that builds them from config."""

from __future__ import annotations

from ..config import BedrockProviderConfig, Config, OllamaProviderConfig
from .base import Completion, Provider, ProviderError
from .bedrock import BedrockProvider
from .ollama import OllamaProvider

__all__ = [
    "BedrockProvider",
    "Completion",
    "OllamaProvider",
    "Provider",
    "ProviderError",
    "build_providers",
]


def build_providers(
    config: Config,
    names: list[str] | None = None,
    temperature: float | None = None,
) -> dict[str, Provider]:
    """Build the named providers (all configured ones when ``names`` is None)."""
    wanted = names or list(config.providers)
    temp = config.temperature if temperature is None else temperature
    providers: dict[str, Provider] = {}
    for name in wanted:
        cfg = config.providers.get(name)
        if cfg is None:
            raise ValueError(
                f"unknown provider {name!r} — configured providers: "
                f"{sorted(config.providers)}. Check the name in targoo.yaml or "
                f"your --models list."
            )
        match cfg:
            case OllamaProviderConfig():
                providers[name] = OllamaProvider(name, cfg, temp)
            case BedrockProviderConfig():
                # No temperature: current Claude families removed it from the
                # Messages API. Depth is controlled per provider via `effort`.
                providers[name] = BedrockProvider(name, cfg, config.max_tokens)
    return providers