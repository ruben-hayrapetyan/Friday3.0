"""Where work with no due date goes, said by rules (3 Nov: "the undated time slots thing should be completely
learned/dictated by rules"): one you write, and one Friday learns from when you do it and asks you to keep.

Monday 19 Oct 2026, 9am, New York (tests/commands/helpers.py)."""

from pathlib import Path

import pytest

from friday.commands.undated import offer
from friday.engine.rules import Scope
from friday.learn.undated import Habit
from tests.commands.helpers import App, new_app

WEEK = {"start": "2026-10-19T00:00", "end": "2026-10-26T00:00"}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def blocks_of(app: App, title: str) -> list[dict]:
    return [b for b in app.do("plan", **WEEK)["blocks"] if b["title"] == title]


def asked(app: App) -> dict[str, dict]:
    return {d["key"]: d for d in app.do("status")["decisions"] if d["kind"] == "learned"}


def worked_afternoons(app: App, days: int = 5) -> None:
    """Two hours each afternoon, 2–4pm, on an errand with no due date, logged after the fact."""
    item = app.do("add", title="Clean out inbox", preset="Errand", duration_min=20 * 60)["item"]["id"]
    for d in range(days):
        app.do("log", id=item, start=f"2026-10-{12 + d}T14:00", end=f"2026-10-{12 + d}T16:00")


# glass box: the scope, the gate, the question


class TestGlassBox:
    def test_a_dated_scope_matches_on_whether_there_is_a_due(self) -> None:
        class Item:
            preset, area, energy, firmness, amount, tags, title, norm_title = (
                "Errand",
                None,
                None,
                "none",
                "fixed",
                (),
                "x",
                "x",
            )

        undated, dated = Item(), Item()
        undated.due_utc, dated.due_utc = None, 100  # type: ignore[attr-defined]
        assert Scope(dated=False).matches(undated, None)  # type: ignore[arg-type]
        assert not Scope(dated=False).matches(dated, None)  # type: ignore[arg-type]
        assert Scope(dated=True).matches(dated, None)  # type: ignore[arg-type]
        assert Scope().matches(undated, None) and Scope().matches(dated, None)  # type: ignore[arg-type]

    def test_the_question_offers_only_then_mostly_then_or_no(self) -> None:
        clash = offer(Habit(14, 16, 10, 1, 5))
        assert clash.key == "undated:window" and clash.about == "undated work only between 2pm and 4pm"
        assert [o.id for o in clash.options] == ["always", "prefer", "no"]
        assert clash.title == "You do work with no due date between 2pm and 4pm"

    def test_nothing_is_asked_while_a_rule_of_yours_says_where_undated_work_goes(self, app: App) -> None:
        worked_afternoons(app)
        assert "learned:undated:window" in asked(app)
        app.do("rule_add", text="no undated work after 9pm")
        assert "learned:undated:window" not in asked(app)


# black box: what you see and what the plan does


def test_a_rule_you_write_keeps_undated_work_out_of_its_hours_and_leaves_dated_work_alone(app: App) -> None:
    app.do("add", title="Tidy notes", preset="Errand", duration_min=2 * 60)  # planned 9–11am without the rule
    app.do("add", title="Essay", preset="Assignment", duration_min=3 * 60, due="2026-10-21T23:59")
    app.do("rule_add", text="undated work only between 2pm and 6pm", strength="Always")
    app.do("replan")
    tidy = blocks_of(app, "Tidy notes")
    assert tidy and all(b["start"][11:] >= "14:00" and b["end"][11:] <= "18:00" for b in tidy)
    assert any(b["start"][11:] < "14:00" for b in blocks_of(app, "Essay"))  # the rule is about undated work only


def test_friday_learns_when_you_do_undated_work_and_asks_before_it_is_a_rule(app: App) -> None:
    worked_afternoons(app)
    question = asked(app)["learned:undated:window"]
    assert "between 2pm and 4pm" in question["title"]
    message = app.do("conflict_resolve", key="undated:window", option="always")["message"]
    assert message == "Added: Undated work between 2pm and 4pm"
    (rule,) = [r for r in app.do("settings")["rules"] if (r.get("scope") or {}).get("dated") is False]
    assert rule["params"]["price"] == "forbid"
    assert "learned:undated:window" not in asked(app)  # yours now: on the Rules page to change


def test_mostly_then_is_a_preference_not_a_wall(app: App) -> None:
    worked_afternoons(app)
    app.do("conflict_resolve", key="undated:window", option="prefer")
    (rule,) = [r for r in app.do("settings")["rules"] if (r.get("scope") or {}).get("dated") is False]
    assert rule["params"]["price"] == 2.0


def test_no_leaves_no_rule_and_isnt_asked_again_for_the_same_habit(app: App) -> None:
    worked_afternoons(app)
    assert app.do("conflict_resolve", key="undated:window", option="no")["message"] == "No rule for undated work"
    assert not [r for r in app.do("settings")["rules"] if (r.get("scope") or {}).get("dated") is False]
    assert "learned:undated:window" not in asked(app)


def test_too_little_undated_work_asks_nothing(app: App) -> None:
    worked_afternoons(app, days=2)
    assert "learned:undated:window" not in asked(app)
