"""A to-do you locked in place that waits on another (26 Nov, the random worlds: "Slides" locked at 7pm was made to
wait for a 4-hour "Step 0"; the day had two hours free before 7pm, and Friday planned the 4 hours a week later, after
the slides, without a word). A lock is fixed in time as an event is: what it waits on is due by it, and when there's
no room for that, Friday says so."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)  # Monday 19 Oct, 9am


def blocks(app: App, item_id: int) -> list[tuple[str, str]]:
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-11-02T00:00")
    return [(b["start"], b["end"]) for b in plan["blocks"] if b["item_id"] == item_id]


def locked_waiting(app: App, at: str, hours: int, lock_hours: int = 1) -> tuple[int, int]:
    slides = app.do("add", title="Slides", duration_min=lock_hours * 60, due="2026-10-30T17:00")["item"]["id"]
    step = app.do("add", title="Step 0", duration_min=hours * 60, shape="one_sitting")["item"]["id"]
    app.do("pin", id=slides, start=at, kind="locked")
    app.do("depend", item_id=slides, depends_on_id=step)
    app.do("replan")
    return slides, step


def test_what_a_locked_to_do_waits_on_is_planned_before_the_lock(app: App) -> None:
    # Weeks of work with later dues, which Friday would start first; Step 0 has none of its own
    for n in range(4):
        app.do("add", title=f"Essay {n}", duration_min=8 * 60, due=f"2026-10-2{3 + n}T17:00", firmness="hard")
    slides, step = locked_waiting(app, "2026-10-21T19:00", hours=3)
    planned = blocks(app, step)
    assert planned and max(end for _, end in planned) <= "2026-10-21T19:00", planned
    assert blocks(app, slides)[0][0] == "2026-10-21T19:00"  # your lock stands
    assert not [n for n in app.do("status")["notices"] if n.startswith("Your lock on Slides")]


def test_a_lock_with_no_room_before_it_for_what_it_waits_on_is_said(app: App) -> None:
    slides, step = locked_waiting(app, "2026-10-19T10:00", hours=4)  # an hour from now; Step 0 is 4 hours at once
    assert blocks(app, slides)[0][0] == "2026-10-19T10:00"  # your lock stands
    assert min(start for start, _ in blocks(app, step)) >= "2026-10-19T11:00"
    assert [n for n in app.do("status")["notices"] if n.startswith("Your lock on Slides")] == [
        "Your lock on Slides (Mon 10am) comes before Step 0 is done, and it waits on Step 0: move the lock, "
        "or let it stop waiting"
    ]


def test_what_waits_on_a_locked_to_do_starts_after_the_lock(app: App) -> None:
    first = app.do("add", title="Outline", duration_min=60)["item"]["id"]
    then = app.do("add", title="Draft", duration_min=2 * 60, due="2026-10-30T17:00")["item"]["id"]
    app.do("pin", id=first, start="2026-10-22T14:00", kind="locked")
    app.do("depend", item_id=then, depends_on_id=first)
    app.do("replan")
    assert min(start for start, _ in blocks(app, then)) >= "2026-10-22T15:00", blocks(app, then)
