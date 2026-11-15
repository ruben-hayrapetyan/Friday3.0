"""Which should win?: a rule the plan bends is planned once more weighed far higher, and the rule that
then gives way on the same days is what it clashes with. Your answer is kept for that pair: the winner weighs ×3 and
the other ÷3 from then on, and a new answer for the same two replaces it."""

import json
from datetime import date
from pathlib import Path

import pytest

from friday.commands.rules import find_clashes
from friday.core.db import connect
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


@pytest.fixture
def lab(app: App) -> App:
    """Monday and Tuesday full but for hours between events, Wednesday free, and Lab 9 (3 h) due Wednesday night:
    finishing it a day early means doing it in the hours between."""
    for day in ("2026-10-19", "2026-10-20"):
        for start, end in ((9, 10), (11, 12), (13, 14), (15, 16), (17, 22)):
            app.do("add", title=f"Event {start}", when="fixed", start=f"{day}T{start:02}:00", end=f"{day}T{end:02}:00")
    app.do("add", text="Lab 9 3h due wed 23:59")
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
    # said in words (14 Nov): "Thu: it clashes with “…”: <why>.", never "it bends no less"; asked only when it's
    # a clash your answer decides (15 Nov)
    first = f"{date.fromisoformat(sorted(out['days'])[0]):%a}"
    assert out["said"].startswith(first) and f"clashes with “{out['other_sentence']}”: " in out["said"]
    assert out["because"] and out["said"].endswith(
        f"{out['because'][1:]}." + (" Which should win?" if out["ask"] else "")
    )


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


def test_a_deleted_rule_takes_its_answers_with_it(app: App) -> None:
    """15 Nov: a client's Rules page said "Wins over 'spread'" for a rule long gone."""
    app.do("rule_add", text="no work before 10am")
    mine = next(r["name"] for r in app.do("rules") if r["source"] == "you")
    app.do("rule_win", winner=mine, loser="chunk_cost")
    app.do("rule_win", winner="deep_run", loser="daily_load")
    app.do("rule_remove", name=mine)
    rules = {r["name"]: r for r in app.do("rules")}
    assert rules["chunk_cost"]["gives_way_to"] == [] and rules["deep_run"]["wins_over"] == ["daily_load"]
    kept = json.loads(next(r["value"] for r in app.table("kv") if r["key"] == "rule_wins"))
    assert kept == [{"winner": "deep_run", "loser": "daily_load"}]


def test_rules_never_names_an_answer_about_a_rule_gone(app: App) -> None:
    """Answers saved before rule_remove cleaned them (or about a rule a migration took out) are left unsaid."""
    gone = [{"winner": "spread", "loser": "chunk_cost"}, {"winner": "deep_run", "loser": "cluster"}]
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'rule_wins', ?)", [json.dumps(gone)])
    rules = {r["name"]: r for r in app.do("rules")}
    assert rules["chunk_cost"]["gives_way_to"] == [] and rules["deep_run"]["wins_over"] == []


def test_migration_37_prunes_answers_about_rules_gone(tmp_path: Path) -> None:
    from tests.commands.test_exam_prep_spread import at_version

    wins = [{"winner": "spread", "loser": "chunk_cost"}, {"winner": "deep_run", "loser": "daily_load"},
            {"winner": "you:mine", "loser": "deep_run"}]  # fmt: skip
    saved = [{"type": "deep_run", "name": "deep_run"}, {"type": "daily_load", "name": "daily_load"},
             {"type": "chunk_cost", "name": "chunk_cost"}, {"type": "time_preference", "name": "you:mine"}]  # fmt: skip
    for user, rules in ((1, saved), (2, None)):  # saved rules, and the built-in ones never changed
        path = tmp_path / f"{user}.db"
        old = at_version(path, 36)
        if rules is not None:
            old.execute("INSERT INTO settings (key, value, version, updated_utc) VALUES ('rules', ?, 1, 'x')",
                        [json.dumps(rules)])  # fmt: skip
        old.execute("INSERT INTO kv (key, value) VALUES ('rule_wins', ?)", [json.dumps(wins)])
        old.close()
        conn = connect(path)
        kept = json.loads(conn.execute("SELECT value FROM kv WHERE key = 'rule_wins'").fetchone()[0])
        assert kept == (wins[1:] if rules else [wins[1]])


def test_a_clash_says_why_from_the_two_plans(lab: App) -> None:
    """15 Nov (the user: "if clashes are problematic, ask in inbox about them, else, add the because"): the work whose
    cost under the other rule went up, and what happened to it."""
    out = lab.do("rule_clash", name="finish_early")
    assert out["other"] == "chunk_cost" and out["days"] == ["2026-10-19"] and out["when"] == "Mon"
    assert out["because"] == "Finishing Lab 9 2 days sooner splits it into 3 sittings instead of 1"
    assert out["said"] == (
        "Mon: it clashes with “Fewer, longer sessions”: finishing Lab 9 2 days sooner splits it into 3 sittings "
        "instead of 1. Which should win?"
    )


def test_a_clash_your_answer_decides_is_asked_in_the_inbox_until_answered(lab: App) -> None:
    assert lab.do("rule_clashes") == []  # nothing looked into yet: a night's job does it
    assert find_clashes(lab.conn, lab.now_utc) == 1
    (asked,) = lab.do("rule_clashes")
    assert (asked["rule"], asked["other"], asked["ask"]) == ("finish_early", "chunk_cost", True)
    assert "3 sittings instead of 1" in asked["because"]
    lab.do("rule_win", winner="chunk_cost", loser="finish_early")
    assert lab.do("rule_clashes") == []


def test_a_mild_clash_says_why_and_isnt_asked(heavy: App) -> None:
    """Finishing a problem set a day early would cost "Fewer, longer sessions" more than ten times what it gains: no
    answer would change that, so Friday says why on the Rules page and asks nothing (a dearer trade than
    planner/views.py ASK_MOST); keeping work to 3 hours in a row is a trade your answer decides, and is asked."""
    out = heavy.do("rule_clash", name="finish_early")
    assert out["other"] == "chunk_cost" and out["ask"] is False
    assert out["because"].endswith("into 2 sittings instead of 1") and out["said"].endswith("instead of 1.")
    assert "Which should win?" not in out["said"]
    find_clashes(heavy.conn, heavy.now_utc)
    asked = [c["rule"] for c in heavy.do("rule_clashes")]
    assert "finish_early" not in asked and "deep_run" in asked


def test_the_nightly_job_looks_into_clashes_from_the_second_night(lab: App) -> None:
    from friday.server.events import Hub
    from friday.server.jobs import clashes, record

    settings = take_snapshot(lab.conn, lab.now_utc).settings
    clashes(lab.conn, lab.now_utc, settings, Hub(), None, Path(), 1)  # the first start: not then
    assert lab.do("rule_clashes") == []
    record(lab.conn, "clashes", lab.now_utc, 1, None)
    clashes(lab.conn, lab.now_utc, settings, Hub(), None, Path(), 1)
    assert [c["rule"] for c in lab.do("rule_clashes")] == ["finish_early"]
