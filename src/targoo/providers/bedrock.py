"""Claude provider running on AWS Bedrock via the Anthropic SDK.

Uses ``AnthropicBedrockMantle`` — Anthropic's Messages-API client for the
Bedrock endpoint. Bedrock model IDs carry an ``anthropic.`` prefix
(e.g. ``anthropic.claude-opus-5-5``); if your account requires a cross-region
inference profile, set model to the profile id instead (e.g.
``us.anthropic.claude-opus-5-5``).

AWS credentials come from the standard chain: env vars, the profile named by
``AWS_PROFILE``, SSO, or instance metadata — never from targoo.yaml.

Sampling note: current Claude families (Opus 5.x, Sonnet 5.x, Fable 5.x)
removed top-level ``temperature`` from the Messages API — requests carrying it
error out. Output depth is controlled with ``effort`` (low…max, default
``medium`` on Opus 5.5) instead, so that is our only per-provider knob. The
global ``temperature`` setting therefore applies to Ollama providers only.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

from ..config import BedrockProviderConfig
from .base import Completion, ProviderError

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


class BedrockProvider:
    name: str
    model: str

    def __init__(
        self,
        name: str,
        cfg: BedrockProviderConfig,
        max_tokens: int,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.name = name
        self.model = cfg.model
        self._cfg = cfg
        self._max_tokens = max_tokens
        self._client = None
        self._client_factory = client_factory or _default_client_factory(cfg)

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def complete(self, system: str, user: str) -> Completion:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if self._cfg.effort:
            request["output_config"] = {"effort": self._cfg.effort}
        if system.strip():
            request["system"] = system

        started = time.monotonic()
        # Streaming keeps long passages under the HTTP timeout; we only need
        # the final concatenated message, not the event stream. Client
        # construction (AWS auth) is inside the try so failures surface as
        # ProviderError too.
        try:
            client = self._ensure_client()
            with client.messages.stream(**request) as stream:
                response = stream.get_final_message()
        except Exception as e:  # noqa: BLE001 — surface any SDK failure to the run log
            raise ProviderError(f"{self.name}: bedrock call failed: {e}") from e
        seconds = time.monotonic() - started

        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        if response.stop_reason not in (None, "end_turn"):
            print(
                f"warning: {self.name} stopped with stop_reason={response.stop_reason!r} "
                f"on a passage — output may be truncated",
                file=sys.stderr,
            )
        return Completion(text=text, seconds=seconds)


def _default_client_factory(cfg: BedrockProviderConfig) -> Callable[[], Any]:
    def factory() -> Any:
        from anthropic import AnthropicBedrockMantle

        if cfg.aws_profile:
            return AnthropicBedrockMantle(aws_region=cfg.aws_region, aws_profile=cfg.aws_profile)
        return AnthropicBedrockMantle(aws_region=cfg.aws_region)

    return factory