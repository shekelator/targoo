
import yaml

from targoo.bakeoff import run_bakeoff
from targoo.config import Config
from targoo.providers.base import Completion


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