import pytest

from targoo.config import ConfigError, load_config


def write(tmp_path, body):
    file = tmp_path / "targoo.yaml"
    file.write_text(body, encoding="utf-8")
    return file


FULL = """
temperature: 0.1
max_tokens: 2048
judge: dicta
providers:
  bedrock:
    kind: bedrock
    model: anthropic.claude-sonnet-5
    aws_region: eu-west-1
  dicta:
    kind: ollama
    base_url: http://127.0.0.1:11434
    model: dicta-il/DictaLM-3.0-1.7B-Thinking:latest
    timeout_seconds: 300
    api_key_env: DUMMY
"""


def test_load_full_config(tmp_path):
    file = write(tmp_path, FULL)

    config = load_config(str(file))

    assert config.temperature == 0.1
    assert config.max_tokens == 2048
    assert config.judge == "dicta"
    assert set(config.providers) == {"bedrock", "dicta"}
    assert config.providers["bedrock"].model == "anthropic.claude-sonnet-5"
    assert config.providers["bedrock"].aws_region == "eu-west-1"
    assert config.providers["dicta"].base_url == "http://127.0.0.1:11434"
    assert config.providers["dicta"].timeout_seconds == 300


def test_missing_file_gives_hint(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(str(tmp_path / "nope.yaml"))


def test_ollama_provider_requires_base_url_and_model(tmp_path):
    file = write(
        tmp_path,
        """
providers:
  dicta:
    kind: ollama
    base_url: http://127.0.0.1:11434
""",
    )

    with pytest.raises(ConfigError, match="model is required"):
        load_config(str(file))


def test_bad_kind_rejected(tmp_path):
    file = write(
        tmp_path,
        """
providers:
  x:
    kind: anthropic
""",
    )

    with pytest.raises(ConfigError, match="unsupported kind"):
        load_config(str(file))


def test_judge_must_be_a_configured_provider(tmp_path):
    file = write(
        tmp_path,
        """
judge: nobody
providers:
  dicta:
    kind: ollama
    base_url: http://127.0.0.1:11434
    model: dicta-il/DictaLM-3.0-1.7B-Thinking:latest
""",
    )

    with pytest.raises(ConfigError, match="judge names"):
        load_config(str(file))


def test_bedrock_aws_profile_optional(tmp_path):
    file = write(
        tmp_path,
        """
providers:
  b:
    kind: bedrock
    model: anthropic.claude-opus-5-5
    aws_profile: my-sso
""",
    )

    config = load_config(str(file))

    assert config.providers["b"].aws_profile == "my-sso"