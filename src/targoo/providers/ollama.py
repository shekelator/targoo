"""Ollama provider — covers both a local Ollama daemon and Ollama Cloud.

Both are the same HTTP surface (``POST /api/chat``); the differences are the
base URL and, for the cloud endpoint, a Bearer key resolved from an env var.
"""

from __future__ import annotations

import os
import time

import httpx

from ..config import OllamaProviderConfig
from .base import Completion, ProviderError


class OllamaProvider:
    name: str
    model: str

    def __init__(
        self,
        name: str,
        cfg: OllamaProviderConfig,
        temperature: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.name = name
        self.model = cfg.model
        self._cfg = cfg
        self._temperature = temperature
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(cfg.timeout_seconds, connect=10.0)
        )

    def complete(self, system: str, user: str) -> Completion:
        messages = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "stream": False,
            "messages": messages,
            "options": {"temperature": self._temperature},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        api_key = os.environ.get(self._cfg.api_key_env, "").strip()
        if api_key:
            # Ollama Cloud (and any API-key gateway) rejects unauthenticated
            # calls; local daemons ignore the header, so setting it always is safe.
            headers["Authorization"] = f"Bearer {api_key}"

        started = time.monotonic()
        try:
            response = self._client.post(
                self._cfg.base_url.rstrip("/") + "/api/chat",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as e:
            raise ProviderError(
                f"{self.name}: request to {self._cfg.base_url} failed: {e}"
            ) from e
        if response.status_code != 200:
            raise ProviderError(
                f"{self.name}: ollama API returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError, ValueError) as e:
            raise ProviderError(f"{self.name}: unexpected ollama response shape: {e}") from e
        return Completion(text=content, seconds=time.monotonic() - started)