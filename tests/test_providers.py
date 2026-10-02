import json
from types import SimpleNamespace

import httpx
import pytest

from targoo.config import BedrockProviderConfig, OllamaProviderConfig
from targoo.providers.base import ProviderError
from targoo.providers.bedrock import BedrockProvider
from targoo.providers.ollama import OllamaProvider

OLLAMA_CFG = OllamaProviderConfig(
    base_url="https://ollama.com", model="gemma4:cloud", api_key_env="TEST_KEY"
)


def ollama_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://ollama.com")


def test_ollama_sends_chat_payload(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"message": {"content": "hello"}})

    provider = OllamaProvider("cloud", OLLAMA_CFG, temperature=0.2, client=ollama_client(handler))
    completion = provider.complete(system="sys", user="usr")

    assert completion.text == "hello"
    assert completion.seconds >= 0
    request = captured["request"]
    assert request.url.path == "/api/chat"
    assert "authorization" not in request.headers
    assert captured["payload"]["model"] == "gemma4:cloud"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"]["temperature"] == 0.2
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_ollama_bearer_key_from_env(monkeypatch):
    monkeypatch.setenv("TEST_KEY", " secret ")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"message": {"content": "ok"}})

    provider = OllamaProvider("cloud", OLLAMA_CFG, temperature=0.0, client=ollama_client(handler))
    provider.complete(system="", user="hi")

    assert captured["request"].headers["authorization"] == "Bearer secret"


def test_ollama_empty_system_omitted(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    provider = OllamaProvider("local", OLLAMA_CFG, temperature=0.0, client=ollama_client(handler))
    provider.complete(system="", user="hi")

    assert [m["role"] for m in captured["payload"]["messages"]] == ["user"]


def test_ollama_http_error_raised(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    handler = lambda request: httpx.Response(500, text="boom")  # noqa: E731

    provider = OllamaProvider("cloud", OLLAMA_CFG, temperature=0.0, client=ollama_client(handler))
    with pytest.raises(ProviderError, match="returned 500"):
        provider.complete(system="", user="hi")


def test_ollama_bad_shape_raised(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    handler = lambda request: httpx.Response(200, json={"unexpected": True})  # noqa: E731

    provider = OllamaProvider("local", OLLAMA_CFG, temperature=0.0, client=ollama_client(handler))
    with pytest.raises(ProviderError, match="response shape"):
        provider.complete(system="", user="hi")


# --- bedrock ---


class FakeBedrockMessages:
    def __init__(self, holder, response):
        self._holder = holder
        self._response = response

    def stream(self, **kwargs):
        self._holder.update(kwargs)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._response


TEXT_BLOCK = SimpleNamespace(type="text", text=" translation")

BEDROCK_CFG = BedrockProviderConfig(model="anthropic.claude-opus-5-5", aws_region="us-east-1")


def bedrock_provider(holder=None, response=None, cfg=BEDROCK_CFG) -> BedrockProvider:
    holder = holder if holder is not None else {}
    message = response or SimpleNamespace(content=[TEXT_BLOCK], stop_reason="end_turn")
    factory_count = {"n": 0}

    def factory():
        factory_count["n"] += 1
        return SimpleNamespace(messages=FakeBedrockMessages(holder, message))

    provider = BedrockProvider(
        "bedrock", cfg, max_tokens=8000, client_factory=factory
    )
    provider._factory_count = factory_count  # exposed for laziness assertions
    return provider


def test_bedrock_sends_messages_request():
    holder: dict = {}
    provider = bedrock_provider(holder)

    completion = provider.complete(system="be an expert", user="translate this")

    assert completion.text == " translation"
    assert holder["model"] == "anthropic.claude-opus-5-5"
    assert holder["max_tokens"] == 8000
    # Current Claude families removed temperature from the Messages API.
    assert "temperature" not in holder
    assert holder["messages"] == [{"role": "user", "content": "translate this"}]
    assert holder["system"] == "be an expert"
    assert "output_config" not in holder


def test_bedrock_effort_included_when_configured():
    holder: dict = {}
    cfg = BedrockProviderConfig(
        model="anthropic.claude-opus-5-5", aws_region="us-east-1", effort="high"
    )
    provider = bedrock_provider(holder, cfg=cfg)

    provider.complete(system="", user="translate this")

    assert holder["output_config"] == {"effort": "high"}


def test_bedrock_client_created_lazily():
    provider = bedrock_provider()

    assert provider._factory_count["n"] == 0
    provider.complete(system="", user="hi")
    assert provider._factory_count["n"] == 1
    provider.complete(system="s", user="hi")
    assert provider._factory_count["n"] == 1


def test_bedrock_empty_system_omitted():
    holder: dict = {}
    provider = bedrock_provider(holder)

    provider.complete(system="", user="translate this")

    assert "system" not in holder


def test_bedrock_failure_wrapped():
    def explode():
        raise RuntimeError("boom")

    provider = BedrockProvider(
        "bedrock", BEDROCK_CFG, max_tokens=99, client_factory=explode
    )
    with pytest.raises(ProviderError, match="bedrock call failed"):
        provider.complete(system="", user="hi")


def test_build_providers_unknown_name():
    from targoo.config import Config
    from targoo.providers import build_providers

    config = Config()
    with pytest.raises(ValueError, match="unknown provider"):
        build_providers(config, ["nope"])