"""Explanations of the plan (DESIGN §16): the `why` sentence (room to spare, pins, the event a block follows, a
day's pace), `why_not` refusals, and the cost per rule in the plan or on one day."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def why_of(app: App, item_id: int) -> str:
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["item_id"] == item_id)
    return app.do("why", key=key)["sentence"]


def test_why_says_how_much_room_work_has_before_its_due(app: App) -> None:
    tight = app.do("add", text="PS due mon 11:00 ~2h")["item"]["id"]
    soon = app.do("add", text="lab due tue 17:00 ~30m")["item"]["id"]
    later = app.do("add", text="essay due thu 17:00 ~30m")["item"]["id"]
    app.do("replan")
    assert why_of(app, tight).startswith("Due Mon 19 Oct 11am; no room to spare: it has to happen as planned")
    assert why_of(app, soon).startswith("Due Tue 20 Oct 5pm; it could all start 31 h later and still be on time")
    assert why_of(app, later).startswith("Due Thu 22 Oct 5pm; it could all start 3 days later and still be on time")


def test_why_names_your_pin_the_event_it_follows_and_the_days_pace(app: App) -> None:
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("add", title="Seminar", when="fixed", start="2026-10-19T13:00", end="2026-10-19T14:00", buffer_after_min=15)
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T14:15", kind="locked")
    app.do("pace", name="easy")
    app.do("replan")
    assert why_of(app, essay) == "You pinned it here. Starts right after Seminar + 15 min. Easy pace that day."


def test_why_after_an_event_with_no_buffer_names_only_the_event(app: App) -> None:
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("add", title="Seminar", when="fixed", start="2026-10-19T13:00", end="2026-10-19T14:00")
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T14:00", kind="locked")
    app.do("replan")
    assert why_of(app, essay) == "You pinned it here. Starts right after Seminar."


def test_why_for_a_block_not_in_the_plan_says_so(app: App) -> None:
    app.do("add", text="essay ~1h")
    app.do("replan")
    with pytest.raises(FieldError, match="no block T1@2026-10-25T03:00 in the current plan"):
        app.do("why", key="T1@2026-10-25T03:00")


def test_why_not_refuses_a_start_outside_the_horizon(app: App) -> None:
    app.do("add", text="essay ~1h")
    app.do("replan")
    key = app.do("plan")["blocks"][0]["key"]
    with pytest.raises(FieldError, match="outside the planning horizon") as refused:
        app.do("why_not", key=key, start="2026-11-30T10:00")
    assert refused.value.field == "start"


def test_rule_totals_for_the_whole_plan_or_one_day(app: App) -> None:
    app.do("add", text="PS due mon 11:00 ~2h")
    app.do("replan")
    whole = app.do("rule_totals")
    assert whole["finish_early"] > 0 and "late_work" in whole
    assert app.do("rule_totals", day="2026-10-19") == {"finish_early": whole["finish_early"]}
    assert app.do("rule_totals", day="2030-01-01") == {}


def test_changes_still_answer_after_an_add_the_plan_placed_is_taken_back(app: App) -> None:
    app.do("add", text="essay ~2h")
    lab = app.full("add", payload={"text": "lab ~1h"})
    app.do("replan")
    app.do("undo", command_id=lab.command_id)
    out = app.do("changes")  # was: FieldError "That item (T2) isn't there any more"
    titles = [b["title"] for b in out["added"]] + [b["title"] for b in out["removed"]]
    assert "essay" in titles
    assert "lab" not in titles  # taken back: not named as if it were still there
