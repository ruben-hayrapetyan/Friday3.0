"""Which should win? (COMBINED.md 66): a rule the plan bends is planned once more weighed far higher, and the rule that
then gives way on the same days is what it clashes with. Your answer is kept for that pair: the winner weighs ×3 and
the other ÷3 from then on, and a new answer for the same two replaces it."""

import json
from datetime import date
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.learning import learnable
from friday.planner.service import replan
from friday.planner.snapshot import WIN, take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 October, 09:00


@pytest.fixture
def heavy(app: App) -> App:
    """Sixty hours due on Sunday: something has to give."""
    for n in range(12):
        app.do("add", text=f"problem set {n} ~5h due sun 23:59")
    replan(app.conn, app.now_utc)
    return app


def weight(app: App, name: str) -> float:
    return next(r.weight for r in take_snapshot(app.conn, app.now_utc).settings["rules"] if r.name == name)


def test_a_bent_rule_names_what_it_clashes_with_and_where(heavy: App) -> None:
    out = heavy.do("rule_clash", name="deep_run")
    assert out["other"] in learnable(take_snapshot(heavy.conn, heavy.now_utc).settings)
    assert out["other"] != "deep_run"
    assert out["days"] and all(date(2026, 10, 19) <= date.fromisoformat(d) <= date(2026, 10, 25) for d in out["days"])
    assert out["sentence"] and out["other_sentence"]


def test_a_rule_the_plan_keeps_clashes_with_nothing(app: App) -> None:
    app.do("add", text="essay ~2h due fri")
    replan(app.conn, app.now_utc)
    assert app.do("rule_clash", name="weekends")["other"] is None


def test_deadlines_never_clash(heavy: App) -> None:
    out = heavy.do("rule_clash", name="late_work")
    assert out["other"] is None and out["days"] == [] and out["sentence"]
    with pytest.raises(FieldError, match="no rule"):
        heavy.do("rule_clash", name="nonsense")


def test_no_plan_yet_no_clash(app: App) -> None:
    assert app.do("rule_clash", name="deep_run")["other"] is None


def test_your_answer_weighs_the_winner_up_and_the_other_down(app: App) -> None:
    deep, chunk = weight(app, "deep_run"), weight(app, "chunk_cost")
    out = app.do("rule_win", winner="deep_run", loser="chunk_cost")
    assert out["message"].count("wins over") == 1
    assert weight(app, "deep_run") == pytest.approx(deep * WIN)
    assert weight(app, "chunk_cost") == pytest.approx(chunk / WIN)
    rules = {r["name"]: r for r in app.do("rules")}
    assert rules["deep_run"]["wins_over"] == ["chunk_cost"] and rules["chunk_cost"]["gives_way_to"] == ["deep_run"]
    assert rules["daily_load"]["wins_over"] == [] and rules["daily_load"]["gives_way_to"] == []


def test_a_new_answer_for_the_same_two_replaces_the_old(app: App) -> None:
    deep = weight(app, "deep_run")
    app.do("rule_win", winner="deep_run", loser="chunk_cost")
    app.do("rule_win", winner="chunk_cost", loser="deep_run")  # clicked the result to change it
    kept = json.loads(next(r["value"] for r in app.table("kv") if r["key"] == "rule_wins"))
    assert kept == [{"winner": "chunk_cost", "loser": "deep_run"}]
    assert weight(app, "deep_run") == pytest.approx(deep / WIN)


def test_answers_for_different_pairs_add_up(app: App) -> None:
    deep = weight(app, "deep_run")
    app.do("rule_win", winner="deep_run", loser="chunk_cost")
    app.do("rule_win", winner="deep_run", loser="daily_load")
    assert weight(app, "deep_run") == pytest.approx(deep * WIN * WIN)


def test_an_answer_about_a_deleted_rule_is_ignored(app: App) -> None:
    app.do("rule_add", text="no work before 10am")
    mine = next(r["name"] for r in app.do("rules") if r["source"] == "you")
    chunk = weight(app, "chunk_cost")
    app.do("rule_win", winner=mine, loser="chunk_cost")
    app.do("rule_remove", name=mine)
    assert weight(app, "chunk_cost") == pytest.approx(chunk)


def test_what_cant_be_answered(app: App) -> None:
    with pytest.raises(FieldError, match="itself"):
        app.do("rule_win", winner="deep_run", loser="deep_run")
    with pytest.raises(FieldError, match="no rule"):
        app.do("rule_win", winner="deep_run", loser="nonsense")
    with pytest.raises(FieldError, match="isn't a rule that can give way"):
        app.do("rule_win", winner="deep_run", loser="late_work")


def test_an_answer_can_be_undone(app: App) -> None:
    deep = weight(app, "deep_run")
    said = app.full("rule_win", payload={"winner": "deep_run", "loser": "chunk_cost"}, provisional=False)
    app.do("undo", command_id=said.command_id)
    assert weight(app, "deep_run") == pytest.approx(deep)


def test_the_winner_is_kept_at_least_as_well_after_the_answer(heavy: App) -> None:
    clash = heavy.do("rule_clash", name="deep_run")
    assert clash["other"]

    def bent(rule: str) -> float:
        report = json.loads(heavy.table("plans")[-1]["report"])
        return sum(t.get(rule, 0) for d, t in report["rule_totals_by_day"].items() if d != "other")

    before = bent("deep_run")
    heavy.do("rule_win", winner="deep_run", loser=clash["other"])
    heavy.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'next_cold', 'true')")
    replan(heavy.conn, heavy.now_utc)
    assert bent("deep_run") / WIN <= before  # weighed ×3 now, so its points are compared unweighted
