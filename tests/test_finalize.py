import pytest
import yaml

from targoo.config import Config
from targoo.finalize import export_path, freeze, run_translate, status
from targoo.providers.base import Completion, ProviderError

from .test_bakeoff import FakeProvider, make_texts

PROMPT_MARKER = "final translation"  # stable phrase from prompts/final.md


def make_config(tmp_path, with_prompts=True):
    """Config pointing at the repo's real prompts/ so the final template renders."""
    config = Config(
        texts_dir=str(tmp_path / "texts"),
        tm_dir=str(tmp_path / "tm"),
        translations_dir=str(tmp_path / "translations"),
        prompts_dir="prompts",
    )
    return config


def test_run_translate_drafts_every_passage(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    provider = FakeProvider("bedrock", "us.anthropic.claude-sonnet-4-6")

    run_translate(config, provider, ids="a,b")

    doc = yaml.safe_load((tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8"))
    assert doc["passage_id"] == "a"
    assert (tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8").count("א א")
    assert (tmp_path / "translations" / "a.txt").read_text(encoding="utf-8").startswith(
        "fake draft"
    )
    assert doc["draft"]["provider"] == "bedrock"
    assert doc["draft"]["model"] == "us.anthropic.claude-sonnet-4-6"
    assert doc["english_frozen"] is None
    # The prompt that was rendered is the final prompt, with the source in it.
    (system, user) = provider.calls[0]
    assert system == ""
    assert "א א" in user
    assert PROMPT_MARKER in user


def test_run_translate_skips_existing_drafts_unless_force(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    provider = FakeProvider("bedrock")

    run_translate(config, provider)
    first_yaml = (tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8")

    stats = run_translate(config, provider, force=False)
    assert stats["skipped"] == 2
    # Re-running without --force touches nothing.
    assert (tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8") == first_yaml

    stats = run_translate(config, provider, force=True)
    assert stats["redrafted"] == 2
    assert (tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8") != first_yaml
    assert len(provider.calls) == 4  # two during the first pass, two re-drafts

def test_frozen_passages_never_redrafted(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    provider = FakeProvider("bedrock")

    run_translate(config, provider, ids="a")
    freeze(config, "a")
    provider.calls.clear()

    # --force re-drafts the untranslated b but never the frozen a.
    stats = run_translate(config, provider, force=True)
    assert stats["frozen"] == 1
    assert stats["drafted"] == 1
    assert len(provider.calls) == 1


class _ExplodingProvider:
    """Fails every call the way a timed-out provider would."""

    name = "bedrock"
    model = "m"

    def complete(self, system: str, user: str) -> Completion:
        raise ProviderError("bedrock: request failed: timed out")


def test_run_translate_survives_provider_failure(tmp_path, capsys):
    config = make_config(tmp_path)
    make_texts(tmp_path)

    stats = run_translate(config, _ExplodingProvider())

    assert stats["failed"] == 2
    for pid in ("a", "b"):
        doc = yaml.safe_load((tmp_path / "tm" / f"{pid}.yaml").read_text(encoding="utf-8"))
        assert "error" in doc["draft"]
        assert not (tmp_path / "translations" / f"{pid}.txt").exists()
    # The full detail went to the operator, not the TM record.
    assert "timed out" in capsys.readouterr().err

    # A later healthy run replaces the error draft (counted as a redraft).
    provider = FakeProvider("bedrock")
    stats = run_translate(config, provider)
    assert stats["redrafted"] == 2
    doc = yaml.safe_load((tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8"))
    assert "text" in doc["draft"]


def test_freeze_roundtrip_keeps_edit_history(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    provider = FakeProvider("bedrock")
    run_translate(config, provider)

    # Post-edit: the human changes the exported text.
    export_file = export_path(config, "a")
    export_file.write_text("edited English text\n", encoding="utf-8")

    doc = freeze(config, "a")
    assert doc["english_frozen"] == "edited English text"
    assert doc["edit_history"][0]["change"] == "frozen with edits"
    assert doc["edit_history"][0]["date"]
    assert yaml.safe_load((tmp_path / "tm" / "a.yaml").read_text(encoding="utf-8")) == doc


def test_freeze_unchanged_remarks_it(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    run_translate(config, FakeProvider("bedrock"))

    doc = freeze(config, "a")
    assert doc["edit_history"][0]["change"] == "frozen unchanged"


def test_freeze_requires_passage_and_rejects_refreeze(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    run_translate(config, FakeProvider("bedrock"))

    freeze(config, "a")
    with pytest.raises(ValueError, match="--reopen"):
        freeze(config, "a")

    with pytest.raises(ValueError, match="no translation"):
        freeze(config, "missing")

    (tmp_path / "tm" / "b.yaml").unlink()
    (tmp_path / "translations" / "b.txt").unlink()
    with pytest.raises(ValueError, match="no translation"):
        freeze(config, "b")


def test_reopen_clears_freeze_and_logs_it(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    run_translate(config, FakeProvider("bedrock"))
    freeze(config, "a")

    doc = freeze(config, "a", reopen=True)
    assert doc["english_frozen"] is None
    assert doc["edit_history"][-1]["change"] == "reopened for editing"
    states = {row["id"]: row["state"] for row in status(config)}
    assert states["a"] == "drafted"


def test_status_states(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)
    provider = FakeProvider("bedrock")

    states = {row["id"]: row["state"] for row in status(config)}
    assert states == {"a": "untranslated", "b": "untranslated"}

    run_translate(config, provider, ids="a")
    states = {row["id"]: row["state"] for row in status(config)}
    assert states["a"] == "drafted"

    (export_path(config, "b")).touch()  # not translated: no TM doc -> untranslated
    freeze(config, "a")
    states = {row["id"]: row["state"] for row in status(config)}
    assert states["a"] == "frozen"
    assert states["b"] == "untranslated"