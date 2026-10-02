
from pathlib import Path

import pytest
import yaml

from targoo.bakeoff import run_bakeoff
from targoo.config import Config
from targoo.providers.base import Completion, ProviderError


class FakeProvider:
    def __init__(self, name: str, model: str = "fake-model"):
        self.name = name
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> Completion:
        self.calls.append((system, user))
        # The reply text must not embed the provider name: blind-file checks
        # scan for it, exactly as a real reviewer would.
        return Completion(text=f"fake draft {len(self.calls)}", seconds=0.1)


def make_texts(tmp_path):
    texts_dir = tmp_path / "texts"
    texts_dir.mkdir()
    (texts_dir / "a.txt").write_text("א א", encoding="utf-8")
    (texts_dir / "b.txt").write_text("ב ב", encoding="utf-8")
    return texts_dir


def make_config(tmp_path):
    return Config(texts_dir=str(tmp_path / "texts"), outputs_dir=str(tmp_path / "outputs"))


def test_run_bakeoff_writes_blind_outputs(tmp_path):
    providers = {
        "alpha": FakeProvider("alpha"),
        "beta": FakeProvider("beta"),
        "gamma": FakeProvider("gamma"),
    }
    config = make_config(tmp_path)
    make_texts(tmp_path)

    run_dir = run_bakeoff(config, providers, run_name="test-run", seed=1)

    drafts = yaml.safe_load((run_dir / "drafts.yaml").read_text(encoding="utf-8"))
    key = yaml.safe_load((run_dir / "bakeoff-key.yaml").read_text(encoding="utf-8"))["key"]

    for passage_id in ("a", "b"):
        letters = set(drafts["passages"][passage_id]["drafts"])
        assert letters == {"A", "B", "C"}
        # Every provider appears exactly once, under its own letter.
        assert sorted(key[passage_id]) == ["A", "B", "C"]
        assert set(key[passage_id].values()) == {"alpha", "beta", "gamma"}


def test_run_bakeoff_seed_reproduces_letters(tmp_path):
    providers = {"alpha": FakeProvider("alpha"), "beta": FakeProvider("beta")}
    config = make_config(tmp_path)
    make_texts(tmp_path)

    dir1 = run_bakeoff(config, providers, run_name="r1", seed=7)
    dir2 = run_bakeoff(config, providers, run_name="r2", seed=7)

    key1 = yaml.safe_load((dir1 / "bakeoff-key.yaml").read_text(encoding="utf-8"))["key"]
    key2 = yaml.safe_load((dir2 / "bakeoff-key.yaml").read_text(encoding="utf-8"))["key"]
    assert key1 == key2


def test_run_bakeoff_passage_markdown_is_blind(tmp_path):
    providers = {"alpha": FakeProvider("alpha"), "beta": FakeProvider("beta")}
    config = make_config(tmp_path)
    make_texts(tmp_path)

    run_dir = run_bakeoff(config, providers, run_name="r", seed=3)

    for file in (run_dir / "passages").glob("*.md"):
        text = file.read_text(encoding="utf-8")
        assert "alpha" not in text and "beta" not in text
        assert "## Source" in text
        assert "## Draft A" in text
        assert "## Draft B" in text

    # The drafts file itself stays blind too; only the key carries names.
    drafts_text = (run_dir / "drafts.yaml").read_text(encoding="utf-8")
    assert "alpha" not in drafts_text and "beta" not in drafts_text
    key_text = (run_dir / "bakeoff-key.yaml").read_text(encoding="utf-8")
    assert "alpha" in key_text and "beta" in key_text


def test_run_bakeoff_sends_rendered_draft_prompt(tmp_path):
    provider = FakeProvider("alpha")
    config = make_config(tmp_path)
    make_texts(tmp_path)

    run_bakeoff(config, {"alpha": provider}, run_name="r", seed=1)

    (system, user) = provider.calls[0]
    assert system == ""
    assert "א א" in user


def test_run_bakeoff_allows_one_provider(tmp_path):
    config = make_config(tmp_path)
    make_texts(tmp_path)

    run_dir = run_bakeoff(config, {"solo": FakeProvider("solo", "solo-model")}, run_name="r-solo")
    key = yaml.safe_load((run_dir / "bakeoff-key.yaml").read_text(encoding="utf-8"))["key"]
    assert key == {"a": {"A": "solo"}, "b": {"A": "solo"}}


class _ExplodingProvider:
    """Fails every call the way a timed-out provider would."""

    name = "explode"
    model = "explode-model"

    def complete(self, system: str, user: str) -> Completion:
        raise ProviderError("explode: request failed: timed out")


def test_run_bakeoff_survives_provider_failure(tmp_path, capsys):
    providers = {
        "healthy": FakeProvider("healthy"),
        "explode": _ExplodingProvider(),
    }
    config = make_config(tmp_path)
    make_texts(tmp_path)

    run_dir = run_bakeoff(config, providers, run_name="r-partial", seed=5)

    drafts = yaml.safe_load((run_dir / "drafts.yaml").read_text(encoding="utf-8"))
    key = yaml.safe_load((run_dir / "bakeoff-key.yaml").read_text(encoding="utf-8"))["key"]
    for passage_id in ("a", "b"):
        passage_drafts = drafts["passages"][passage_id]["drafts"]
        assert len(passage_drafts) == 2
        failed = [d for d in passage_drafts.values() if "text" not in d]
        ok = [d for d in passage_drafts.values() if "text" in d]
        assert len(failed) == 1 and len(ok) == 1
        # The stored error is opaque; the traceback detail went to stderr only.
        assert failed[0]["error"] == "provider call failed (see terminal output)"
        assert "explode" not in yaml.safe_dump(drafts["passages"], allow_unicode=True)
        # The key still maps every letter, failed drafts included.
        assert set(key[passage_id].values()) == {"healthy", "explode"}

    # The error detail reached the operator, not the artifacts.
    captured = capsys.readouterr()
    assert "timed out" in captured.err

    # The markdown page marks the missing draft instead of crashing or lying.
    for file in (run_dir / "passages").glob("*.md"):
        text = file.read_text(encoding="utf-8")
        assert "this draft is missing" in text
        assert "explode" not in text


def test_run_bakeoff_writes_incrementally(tmp_path):
    """drafts.yaml for passage 'a' survives a hard crash during passage 'b'."""
    config = make_config(tmp_path)
    make_texts(tmp_path)

    class CrashOnSecondProvider(FakeProvider):
        def complete(self, system: str, user: str) -> Completion:
            if len(self.calls) >= 1:  # first call (passage a) ok, then die hard
                raise RuntimeError("boom")
            return super().complete(system, user)

    with pytest.raises(RuntimeError, match="boom"):
        run_bakeoff(config, {"crash": CrashOnSecondProvider("crash")}, run_name="r-incr")

    # The crash happened during passage b, yet passage a's artifacts are on disk.
    run_dir = Path(config.outputs_dir) / "r-incr"
    drafts = yaml.safe_load((run_dir / "drafts.yaml").read_text(encoding="utf-8"))
    assert set(drafts["passages"]) == {"a"}
    assert (run_dir / "passages" / "a.md").is_file()