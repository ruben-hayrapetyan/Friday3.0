"""Violated, and why in words (14 Nov): a rule this plan doesn't keep says "Violated on Tue, Thu" (the user's word, not
"gives way"), and its Why? says plainly what took the time, from the plan itself: the work and what it's due by, or
the other rule it clashes with. Never the old "Weighed far higher, it bends no less…"."""

from datetime import date
from pathlib import Path

import pytest

from friday.commands.rules import day_names, days_and, violated_said
from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture(scope="module")
def heavy(tmp_path_factory: pytest.TempPathFactory) -> App:
    """Fifty hours due Wednesday and an essay due Thursday, with no work after 6pm: something has to give."""
    app = new_app(tmp_path_factory.mktemp("why"))  # Monday 19 October, 09:00
    for n in range(10):
        app.do("add", text=f"problem set {n} ~5h due wed 23:59")
    app.do("add", text="CS essay ~6h due thu 17:00")
    app.do("rule_add", text="no work after 6pm")
    replan(app.conn, app.now_utc)
    return app


def rule(app: App, name: str) -> dict:
    return next(r for r in app.do("rules") if r["name"] == name)


def test_a_violated_rule_says_on_which_days(heavy: App) -> None:
    mine = rule(heavy, "you:no-work-after-6pm")
    assert mine["violated"] and all(date.fromisoformat(d) >= date(2026, 10, 19) for d in mine["violated"])
    names = [f"{date.fromisoformat(d):%a}" for d in mine["violated"]]
    assert mine["effect"] == "Violated on " + ", ".join(names)
    kept, of = (int(x) for x in mine["kept"].removeprefix("kept ").removesuffix(" days").split(" of "))
    assert of - kept == len(mine["violated"])  # days only: what no one day carries isn't a day
    for r in heavy.do("rules"):
        assert "Gives way" not in r["effect"]
        assert r["effect"].startswith(("Violated", "Kept throughout", "Off"))


def test_why_names_the_work_and_its_due(heavy: App) -> None:
    out = heavy.do("rule_why", name="you:no-work-after-6pm")
    assert out["sentence"] == "No work after 6pm" and out["lines"]
    said = " ".join(line["said"] for line in out["lines"])
    assert "needed those hours" in said and "(due Wed)" in said and "problem set" in said
    days = [d for line in out["lines"] for d in line["days"]]
    assert sorted(days) == rule(heavy, "you:no-work-after-6pm")["violated"]
    assert all(line["items"] for line in out["lines"])
    first = out["lines"][0]
    assert first["said"].startswith(f"{date.fromisoformat(first['days'][0]):%a}")


def test_work_planned_after_its_due_is_said_to_be_late(heavy: App) -> None:
    said = " ".join(line["said"] for line in heavy.do("rule_why", name="deep_run")["lines"])
    assert "late: due" in said or "(due" in said


def test_a_kept_rule_has_no_reason_to_give(heavy: App) -> None:
    kept = next(r for r in heavy.do("rules") if r["enabled"] and not r["violated"] and r["effect"] != "Off")
    assert kept["effect"] == "Kept throughout this plan"
    assert heavy.do("rule_why", name=kept["name"])["lines"] == []
    with pytest.raises(FieldError, match="no rule"):
        heavy.do("rule_why", name="nonsense")


def test_no_plan_no_reasons(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert app.do("rule_why", name="deep_run")["lines"] == []


def test_days_are_named_as_people_say_them() -> None:
    today = date(2026, 10, 19)  # a Monday
    assert day_names(["2026-10-20", "2026-10-22"], today) == ["Tue", "Thu"]
    assert day_names(["2026-10-20", "2026-10-27"], today) == ["Tue 20", "Tue 27"]  # two Tuesdays aren't one
    assert days_and(["2026-10-20", "2026-10-22"], today) == "Tue and Thu"
    assert days_and(["2026-10-20", "2026-10-21", "2026-10-22"], today) == "Tue, Wed and Thu"
    many = [f"2026-10-{d}" for d in range(19, 25)]
    assert violated_said(many, False, today) == "Violated on Mon, Tue, Wed, Thu and 2 more"
    assert violated_said([], True, today) == "Violated in this plan"
    assert violated_said([], False, today) == "Kept throughout this plan"
