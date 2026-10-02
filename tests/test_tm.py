import pytest
import yaml

from targoo.config import ConfigError
from targoo.corpus import Passage
from targoo.tm import (
    STYLE_VERSION,
    load_all_tm,
    load_tm,
    make_document,
    prompt_fingerprint,
    write_tm,
)

from .test_bakeoff import make_texts


def test_make_document_shape(tmp_path):
    passage = Passage(id="amidah", source="בָּרוּךְ")
    prompt = {"name": "final", "sha256": "abc123", "path": "prompts/final.md"}
    doc = make_document(passage, "bedrock", "us.anthropic.claude-sonnet-4-6", prompt, "Blessed")
    assert doc["passage_id"] == "amidah"
    assert doc["style_version"] == STYLE_VERSION
    assert doc["hebrew"] == "בָּרוּךְ"
    assert doc["english_frozen"] is None
    assert doc["edit_history"] == []
    assert doc["source"] == {}
    assert doc["draft"]["provider"] == "bedrock"
    assert doc["draft"]["model"] == "us.anthropic.claude-sonnet-4-6"
    assert doc["draft"]["prompt"] == prompt
    assert doc["draft"]["text"] == "Blessed"


def test_prompt_fingerprint_stable(tmp_path):
    file = tmp_path / "final.md"
    file.write_text("Hello {{ source }}", encoding="utf-8")
    first = prompt_fingerprint(file)
    second = prompt_fingerprint(file)
    assert first == second
    assert first["name"] == "final"
    assert len(first["sha256"]) == 64
    file.write_text("Changed", encoding="utf-8")
    assert prompt_fingerprint(file)["sha256"] != first["sha256"]


def test_prompt_fingerprint_missing(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        prompt_fingerprint(tmp_path / "nope.md")


def test_write_load_roundtrip(tmp_path):
    make_texts(tmp_path)
    texts_dir = tmp_path / "texts"
    passage = Passage(id="a", source=(texts_dir / "a.txt").read_text(encoding="utf-8"))
    doc = make_document(passage, "bedrock", "m", {"name": "final"}, "English text")
    file = write_tm(tmp_path / "tm", doc)

    loaded = load_tm(tmp_path / "tm", "a")
    assert loaded == yaml.safe_load(file.read_text(encoding="utf-8"))
    assert loaded["draft"]["text"] == "English text"
    assert load_tm(tmp_path / "tm", "b") is None


def test_load_all_tm_sorted_and_validated(tmp_path):
    make_texts(tmp_path)
    for pid in ("b", "a"):
        write_tm(tmp_path / "tm", make_document(Passage(id=pid, source="x"), "p", "m", {}, "t"))
    docs = load_all_tm(tmp_path / "tm")
    assert list(docs) == ["a", "b"]

    (tmp_path / "tm" / "broken.yaml").write_text("just a string", encoding="utf-8")
    with pytest.raises(ConfigError, match="passage_id"):
        load_all_tm(tmp_path / "tm")