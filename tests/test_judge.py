import json
from pathlib import Path

import pytest
import yaml

from targoo.bakeoff import run_bakeoff
from targoo.judge import parse_judgment, run_judge
from targoo.providers.base import Completion

from .test_bakeoff import FakeProvider, make_config, make_texts


def test_parse_judgment_plain():
    assert parse_judgment('{"faithfulness": 4, "fluency": 5, "accuracy": 3, "notes": "ok"}') == {
        "faithfulness": 4,
        "fluency": 5,
        "accuracy": 3,
        "notes": "ok",
    }


def test_parse_judgment_fenced():
    raw = '```json\n{"faithfulness": 1, "fluency": 2, "accuracy": 3, "notes": "x"}\n```'
    assert parse_judgment(raw)["accuracy"] == 3


def test_parse_judgment_prose_around_json():
    raw = (
        'Here is my evaluation: {"faithfulness": 5, "fluency": 5, '
        '"accuracy": 5, "notes": ""} thanks'
    )
    assert parse_judgment(raw)["faithfulness"] == 5


@pytest.mark.parametrize(
    "raw",
    [
        "no json here",
        '{"faithfulness": "four", "fluency": 2, "accuracy": 3}',
        '{"faithfulness": 9, "fluency": 2, "accuracy": 3}',
        '{"faithfulness": 1, "fluency": 2}',
    ],
)
def test_parse_judgment_rejects_garbage(raw):
    assert parse_judgment(raw) is None


def prepare_run(tmp_path) -> str:
    config = make_config(tmp_path)
    make_texts(tmp_path)
    run_dir = run_bakeoff(
        config,
        {"alpha": FakeProvider("alpha"), "beta": FakeProvider("beta")},
        run_name="r",
    )
    return str(run_dir)


def make_judge(answer: str) -> FakeProvider:
    judge = FakeProvider("judge")
    recorded = []

    def complete(system: str, user: str) -> Completion:
        recorded.append((system, user))
        return Completion(text=answer, seconds=0.1)

    judge.complete = complete
    judge.calls = recorded
    return judge


def test_run_judge_scores_blind_and_writes_summary(tmp_path):
    config = make_config(tmp_path)
    run_dir = prepare_run(tmp_path)
    judge = make_judge(
        json.dumps({"faithfulness": 4, "fluency": 5, "accuracy": 4, "notes": "fine"})
    )

    summary = run_judge(config, run_dir, judge)

    judgments = yaml.safe_load(
        (Path(run_dir) / "judgments.yaml").read_text(encoding="utf-8")
    )
    assert set(judgments["scored"]["a"]) == {"A", "B"}
    for entry in judgments["scored"]["a"].values():
        assert entry["faithfulness"] == 4

    rows = {row["letter"]: row for row in summary}
    assert set(rows) == {"A", "B"}
    assert rows["A"]["average"] == 4.33
    assert rows["B"]["average"] == 4.33

    # The judge prompt carried the source and the draft, never a model name.
    (system, user) = judge.calls[0]
    assert "א א" in user
    assert "alpha" not in user and "beta" not in user


def test_run_judge_records_unparseable(tmp_path):
    config = make_config(tmp_path)
    run_dir = prepare_run(tmp_path)
    judge = make_judge("I refuse.")

    summary = run_judge(config, run_dir, judge)

    judgments = yaml.safe_load(
        (Path(run_dir) / "judgments.yaml").read_text(encoding="utf-8")
    )
    for entry in judgments["scored"]["a"].values():
        assert entry == {"error": "unparseable judge output"}
    for row in summary:
        assert row["passages"] == 0
        assert row["average"] == 0


def test_run_judge_missing_run_raises(tmp_path):
    config = make_config(tmp_path)
    judge = make_judge("{}")

    with pytest.raises(FileNotFoundError, match="drafts.yaml"):
        run_judge(config, tmp_path / "no-run", judge)