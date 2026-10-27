"""An event that holds a task's time (27 Oct: "right now a4 dd is meant to serve as a time storage for doing the a4
design doc"): the task is planned in it, for as long as it has left, and other work keeps off all of it."""

from datetime import datetime
from pathlib import Path

import pytest

from friday.core.items import Item
from friday.core.time import format_utc, parse_utc
from friday.planner.holds import held
from friday.planner.service import replan
from friday.planner.snapshot import PinRow
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def blocks(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def within(span: tuple[str, str], lo: str, hi: str) -> bool:
    return lo <= span[0] and span[1] <= hi


def test_the_task_is_planned_in_the_event_and_nothing_else_is(app: App) -> None:
    doc = app.do("add", title="CS A4 Design Doc", duration_min=120, due="2026-10-22T23:59")["item"]["id"]
    other = app.do("add", title="Psych reading", duration_min=60, due="2026-10-22T23:59")["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")["item"]["id"]
    out = app.do("event_hold", id=a4dd, task_id=doc)
    assert out["message"] == "A4dd's time is for CS A4 Design Doc"
    replan(app.conn, app.now_utc)
    assert blocks(app, doc) == [("2026-10-20T21:00", "2026-10-20T23:00")]
    assert not any(b[0] < "2026-10-20T23:00" and b[1] > "2026-10-20T21:00" for b in blocks(app, other))
    event = next(f for f in app.do("plan")["fixed"] if f["id"] == a4dd)
    assert event["holds"] == {"id": doc, "title": "CS A4 Design Doc", "loose": False}  # the event shows as it is
    assert (event["start"], event["end"]) == ("2026-10-20T21:00", "2026-10-20T23:00")


def test_a_task_that_needs_less_takes_the_start_and_the_rest_stays_free_of_other_work(app: App) -> None:
    doc = app.do("add", title="CS A4 Design Doc", duration_min=45, due="2026-10-22T23:59")["item"]["id"]
    other = app.do("add", title="Psych reading", duration_min=60, due="2026-10-20T23:59")["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")["item"]["id"]
    app.do("event_hold", id=a4dd, task_id=doc)
    replan(app.conn, app.now_utc)
    assert blocks(app, doc) == [("2026-10-20T21:00", "2026-10-20T21:45")]
    assert not any(b[0] < "2026-10-20T23:00" and b[1] > "2026-10-20T21:00" for b in blocks(app, other))


def test_a_task_that_needs_more_fills_the_event_and_the_rest_goes_elsewhere(app: App) -> None:
    # Due within the plan's three days, so all of it is planned now.
    doc = app.do("add", title="CS A4 Design Doc", duration_min=180, due="2026-10-21T23:59")["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T22:00")["item"]["id"]
    app.do("event_hold", id=a4dd, task_id=doc)
    replan(app.conn, app.now_utc)
    placed = blocks(app, doc)
    # All of the event, though the calendar joins it to more of the doc planned just before into one block.
    assert any(s <= "2026-10-20T21:00" and e >= "2026-10-20T22:00" for s, e in placed)
    total = sum((datetime.fromisoformat(e) - datetime.fromisoformat(s)).seconds // 60 for s, e in placed)
    assert total == 180


def test_letting_go_makes_it_an_event_again_and_a_done_task_holds_nothing(app: App) -> None:
    doc = app.do("add", title="CS A4 Design Doc", duration_min=60, due="2026-10-22T23:59")["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")["item"]["id"]
    app.do("event_hold", id=a4dd, task_id=doc)
    app.do("event_hold", id=a4dd)
    replan(app.conn, app.now_utc)
    assert not any(b[0] < "2026-10-20T23:00" and b[1] > "2026-10-20T21:00" for b in blocks(app, doc))
    assert next(f for f in app.do("plan")["fixed"] if f["id"] == a4dd)["holds"] is None
    app.do("event_hold", id=a4dd, task_id=doc)
    app.do("done", id=doc)
    assert next(f for f in app.do("plan")["fixed"] if f["id"] == a4dd)["holds"] is None


def test_only_an_event_holds_and_only_a_task_is_held(app: App) -> None:
    doc = app.do("add", title="CS A4 Design Doc", duration_min=60)["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")["item"]["id"]
    with pytest.raises(Exception, match="isn't an event"):
        app.do("event_hold", id=doc, task_id=doc)
    with pytest.raises(Exception, match="isn't a task"):
        app.do("event_hold", id=a4dd, task_id=a4dd)


def test_undo_takes_the_hold_back(app: App) -> None:
    doc = app.do("add", title="CS A4 Design Doc", duration_min=60)["item"]["id"]
    a4dd = app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")["item"]["id"]
    out = app.full("event_hold", payload={"id": a4dd, "task_id": doc})
    app.do("undo", command_id=out.command_id)
    assert next(f for f in app.do("plan")["fixed"] if f["id"] == a4dd)["holds"] is None


# The pure part, case by case: times in minutes from 20 Oct midnight UTC.
H = 60
DAY = parse_utc("2026-10-20T00:00Z")


def at(minute: int) -> str:
    return format_utc(DAY + minute)


def item(
    id: int,
    when: str = "anytime",
    start: int | None = None,
    end: int | None = None,
    minutes: int = 60,
    status: str = "todo",
) -> Item:
    return Item(
        title=f"#{id}", id=id, when=when, start_utc=None if start is None else at(start),  # type: ignore[arg-type]
        end_utc=None if end is None else at(end), amount="fixed", duration_units=minutes // 15, status=status,  # type: ignore[arg-type]
    )  # fmt: skip


def test_held_gives_the_start_of_the_event_and_keeps_the_rest_busy() -> None:
    items, pins = held((item(1, minutes=45), item(9, "fixed", 21 * H, 23 * H)), (), {9: 1}, {}, DAY)
    assert pins == (PinRow(-9, 1, DAY + 21 * H, DAY + 21 * H + 45, "locked"),)
    event = next(i for i in items if i.id == 9)
    assert (event.start_utc, event.end_utc, event.blocks_time, event.buffer_before_min) == (
        at(21 * H + 45), at(23 * H), True, 0)  # fmt: skip


def test_held_counts_what_is_done_and_starts_from_now_in_an_event_under_way() -> None:
    _, pins = held((item(1, minutes=120), item(9, "fixed", 21 * H, 23 * H)), (), {9: 1}, {1: 60}, DAY + 21 * H + 20)
    assert pins == (PinRow(-9, 1, DAY + 21 * H + 15, DAY + 22 * H + 15, "locked"),)


def test_held_takes_all_of_a_short_event_which_then_blocks_nothing() -> None:
    items, pins = held((item(1, minutes=180), item(9, "fixed", 21 * H, 22 * H)), (), {9: 1}, {}, DAY)
    assert pins == (PinRow(-9, 1, DAY + 21 * H, DAY + 22 * H, "locked"),)
    assert next(i for i in items if i.id == 9).blocks_time is False


def test_held_shares_a_task_across_two_events_earliest_first_and_skips_what_is_over_or_done() -> None:
    task = item(1, minutes=90)
    first, second = item(8, "fixed", 9 * H, 10 * H), item(9, "fixed", 21 * H, 23 * H)
    _, pins = held((task, second, first), (), {9: 1, 8: 1}, {}, DAY)
    assert [(p.id, p.end_utc - p.start_utc) for p in pins] == [(-8, 60), (-9, 30)]
    assert held((task, second), (), {9: 1}, {}, DAY + 23 * H)[1] == ()  # over
    assert held((item(1, status="done"), second), (), {9: 1}, {}, DAY)[1] == ()
    assert held((task,), (), {9: 1}, {}, DAY)[1] == ()  # the event isn't in range


def test_a_hold_that_makes_work_late_is_asked_about_and_let_move_when_you_say(app: App) -> None:
    """27 Oct: A4dd held for the design doc made work 8 h late; the plan waited, and letting it move failed ("no
    locked pin -1509"). Letting it move makes the event ask for the task rather than hold it."""
    report = app.do("add", text="report due mon 13:00 ~3h")["item"]["id"]  # needs 10–13, where the doc is held
    doc = app.do("add", title="Design doc", duration_min=120, due="2026-10-21T23:59")["item"]["id"]
    held_at = app.do("add", title="Doc time", when="fixed", start="2026-10-19T10:00", end="2026-10-19T12:00")["item"][
        "id"
    ]
    app.do("event_hold", id=held_at, task_id=doc)
    out = app.do("replan")
    assert out["status"] == "waiting" and "locked Design doc" in out["message"]
    app.do("resolve", unlock_pin_ids=[-held_at])
    assert app.do("replan")["status"] == "current"
    assert all(e <= "2026-10-19T13:00" for _, e in blocks(app, report))  # on time again
    assert next(f for f in app.do("plan")["fixed"] if f["id"] == held_at)["holds"]["loose"] is True
    app.do("event_hold", id=held_at, task_id=doc)  # yes again: it holds
    assert next(f for f in app.do("plan")["fixed"] if f["id"] == held_at)["holds"]["loose"] is False


def test_held_asks_rather_than_holds_for_a_loosened_event() -> None:
    _, pins = held((item(1, minutes=45), item(9, "fixed", 21 * H, 23 * H)), (), {9: 1}, {}, DAY, frozenset({9}))
    assert [p.kind for p in pins] == ["preferred"]
