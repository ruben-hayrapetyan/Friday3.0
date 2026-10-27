"""What only you can decide, in the Inbox (27 Oct: "remove notifications and put that under review… decisions but in
the inbox with a notification symbol"): late work and locks that make work late, each answered once, asked again
only when it gets an hour worse. Monday 2026-10-19, 9am, in New York."""

from pathlib import Path

import pytest

from friday.commands.decisions import answered, spoken
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def wall(app: App, start: str, end: str) -> None:
    app.do("add", title="busy", when="fixed", start=start, end=end)


def asked(app: App, kind: str) -> list[dict]:
    return [d for d in app.do("status")["decisions"] if d["kind"] == kind]


def locked(app: App, title: str, start: str, end: str, minutes: int = 60) -> int:
    chore = app.do("add", title=title, duration_min=minutes)["item"]["id"]
    app.full("pin", payload={"id": chore, "start": start, "end": end}, provisional=False)
    app.do("replan")
    return next(p["id"] for p in app.table("pins") if p["item_id"] == chore)


def test_work_that_will_be_late_is_one_decision_naming_each_thing(app: App) -> None:
    wall(app, "2026-10-19T09:00", "2026-10-19T23:30")
    essay = app.do("add", text="essay due mon 18:00 ~2h")["item"]["id"]
    lab = app.do("add", text="lab report due mon 20:00 ~1h")["item"]["id"]
    app.do("replan")
    late = asked(app, "late")
    assert [d["key"] for d in late] == ["late"]
    assert late[0]["title"] == "2 things will be late"
    assert [i["item_id"] for i in late[0]["items"]] == [essay, lab]  # soonest due first
    assert late[0]["hours"] > 0


def test_leaving_work_late_isnt_asked_again_until_it_gets_an_hour_later(app: App) -> None:
    wall(app, "2026-10-19T09:00", "2026-10-19T23:30")
    essay = app.do("add", text="essay due mon 18:00 ~2h")["item"]["id"]
    app.do("replan")
    assert asked(app, "late")[0]["title"] == "essay will be late"
    assert app.do("late_accept", item_ids=[essay])["message"] == "Left it late"
    assert asked(app, "late") == []
    wall(app, "2026-10-20T07:30", "2026-10-20T12:00")  # the morning after goes too: hours later
    app.do("replan")
    assert [i["item_id"] for i in asked(app, "late")[0]["items"]] == [essay]


def test_only_late_work_can_be_left_late(app: App) -> None:
    essay = app.do("add", text="essay due wed ~2h")["item"]["id"]
    app.do("replan")
    with pytest.raises(FieldError, match="isn't late"):
        app.do("late_accept", item_ids=[essay])


def test_the_plan_keeps_a_lock_that_makes_work_late_and_asks(app: App) -> None:
    app.do("add", text="essay due mon 12:00 ~3h one-sitting")
    wall(app, "2026-10-19T12:00", "2026-10-19T23:30")
    pin = locked(app, "call bank", "2026-10-19T10:00", "2026-10-19T11:00")
    assert app.table("plans")[-1]["status"] == "current"  # nothing waits on you
    lock = asked(app, "lock")
    assert [(d["key"], d["pin_id"], d["start"]) for d in lock] == [(f"lock:{pin}", pin, "2026-10-19T10:00")]
    # The essay is one sitting: kept out of 9am–12pm, it waits for the morning after.
    assert lock[0]["detail"].startswith("Locked at Mon 10am, it makes other work 22h")


def test_keeping_a_lock_stops_the_question_and_keeps_the_lock(app: App) -> None:
    app.do("add", text="essay due mon 12:00 ~3h one-sitting")
    wall(app, "2026-10-19T12:00", "2026-10-19T23:30")
    pin = locked(app, "call bank", "2026-10-19T10:00", "2026-10-19T11:00")
    app.do("lock_keep", pin_ids=[pin])
    app.do("replan")
    assert asked(app, "lock") == []
    assert next(p for p in app.table("pins") if p["id"] == pin)["kind"] == "locked"


@pytest.mark.parametrize(("due", "asks"), [("12:20", False), ("12:10", True)])
def test_a_lock_costing_under_a_quarter_hour_isnt_asked_about(app: App, due: str, asks: bool) -> None:
    """27 Oct: A4dd's hold made work a minute later ("+0.02 h") and the plan waited on it. Here the lock pushes the
    essay's last half hour to 12–12:30: 10 minutes late isn't asked about, 20 minutes is."""
    app.do("add", text=f"essay due mon {due} ~3h")
    wall(app, "2026-10-19T12:30", "2026-10-19T23:30")
    locked(app, "call bank", "2026-10-19T11:30", "2026-10-19T12:00", minutes=30)
    assert bool(asked(app, "lock")) is asks


def test_only_a_lock_that_is_asked_about_can_be_kept(app: App) -> None:
    pin = locked(app, "call bank", "2026-10-19T10:00", "2026-10-19T11:00")
    with pytest.raises(FieldError, match="isn't making work late"):
        app.do("lock_keep", pin_ids=[pin])


def test_letting_a_lock_move_needs_a_lock() -> None:
    from friday.api.commands import ResolveInput

    with pytest.raises(ValueError):
        ResolveInput.model_validate({})


@pytest.mark.parametrize(
    ("answers", "key", "hours", "stands"),
    [
        ({}, 5, 2.0, False),  # never answered
        ({"5": 2.0}, 5, 2.0, True),
        ({"5": 2.0}, 5, 2.9, True),  # later, but not an hour later
        ({"5": 2.0}, 5, 3.0, False),  # an hour later: asked again
        ({"5": 2.0}, 5, 0.5, True),  # better since
        ({"-1509": 0.3}, -1509, 0.3, True),  # an event's hold
    ],
)
def test_an_answer_stands_until_it_costs_an_hour_more(answers: dict, key: int, hours: float, stands: bool) -> None:
    assert answered(answers, key, hours) is stands


@pytest.mark.parametrize(("hours", "said"), [(0.02, "1 min"), (0.25, "15 min"), (1, "1h"), (1.17, "1h 10m"), (8, "8h")])
def test_how_much_later_is_said(hours: float, said: str) -> None:
    assert spoken(hours) == said
