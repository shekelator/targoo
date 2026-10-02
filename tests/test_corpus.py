import pytest

from targoo.corpus import load_passages


@pytest.fixture
def texts_dir(tmp_path):
    path = tmp_path / "texts"
    return path


def test_load_passages_maps_filenames_to_ids(texts_dir):
    texts_dir.mkdir()
    (texts_dir / "genesis-1.txt").write_text("content", encoding="utf-8")
    (texts_dir / "psalm-23.txt").write_text(" אדם ", encoding="utf-8")

    passages = load_passages(texts_dir)

    assert [p.id for p in passages] == ["genesis-1", "psalm-23"]
    assert passages[0].source == "content"
    assert passages[1].source == "אדם"


def test_load_passages_sorted_stable(texts_dir):
    texts_dir.mkdir()
    (texts_dir / "b.txt").write_text("two", encoding="utf-8")
    (texts_dir / "a.txt").write_text("one", encoding="utf-8")

    assert [p.id for p in load_passages(texts_dir)] == ["a", "b"]


def test_load_passages_rejects_empty_file(texts_dir):
    texts_dir.mkdir()
    (texts_dir / "empty.txt").write_text("", encoding="utf-8")

    with pytest.raises(Exception, match="empty source text"):
        load_passages(texts_dir)


def test_load_passages_missing_dir_raises():
    with pytest.raises(Exception, match="texts directory not found"):
        load_passages("does-not-exist")


def test_hebrew_flag(texts_dir):
    texts_dir.mkdir()
    (texts_dir / "he.txt").write_text("בְּרֵאשִׁית", encoding="utf-8")
    (texts_dir / "en.txt").write_text("hello", encoding="utf-8")

    by_id = {p.id: p for p in load_passages(texts_dir)}
    assert by_id["he"].hebrew
    assert not by_id["en"].hebrew