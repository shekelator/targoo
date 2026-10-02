"""Draft and judge provider protocol plus shared error type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised when a provider call fails (HTTP error, bad payload, timeout)."""


@dataclass(frozen=True)
class Completion:
    text: str
    seconds: float


@runtime_checkable
class Provider(Protocol):
    """A minimal text-in / text-out LLM call.

    Two implementations ship: OllamaProvider (local daemon or Ollama Cloud)
    and BedrockProvider (Claude via AWS Bedrock).
    """

    name: str
    model: str

    def complete(self, system: str, user: str) -> Completion: ...