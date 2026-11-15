"""A calendar you hid never shows in a possible schedule (15 Nov: a client's notes): not in the day comparison, What
if, Other ways, the Rules lab's previews or what accepting an invitation would do. What if is drawn as the calendar
is, so its events come only to the calendar (`with_hidden`), marked for Show, as the plan's do; the rest give no
event of it at all. And the day comparison's day is your planning day, from your day start to the next, not midnight
to midnight.

Black box over Mac calendars posted as the Mac app posts them (tests/commands/test_hidden_calendars.py's), each place
read through its query."""

from pathlib import Path

import pytest

from friday.commands.learning import fixed_on
from friday.planner.service import replan
from tests.commands.helpers import App, new_app
from tests.commands.test_hidden_calendars import CALENDARS, EVENTS, FRIENDS, INVITES, ctx, hide
from tests.sync.test_mac_calendars import mac_event, post

LATE = [
    mac_event("n", "home", "Night shift", "2026-10-20T01:00", "2026-10-20T02:00"),  # the 19th's night, after midnight
    mac_event("e", "home", "Early ferry", "2026-10-21T02:00", "2026-10-21T03:00"),  # the 20th's night
]


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)  # Monday 19 October, 9am; days start at 4am
    post(app, CALENDARS, [])
    for c in (FRIENDS, INVITES):
        app.do("calendar_set", id=c["id"], mac=True, trusted=False)
    post(app, CALENDARS, EVENTS + LATE, minutes_later=1)
    app.do("add", text="essay due fri 17:00 ~4h")
    replan(app.conn, app.now_utc)
    return app


def test_the_day_comparisons_day_runs_from_your_day_start_to_the_next(app: App) -> None:
    assert "Night shift" in {f["title"] for f in fixed_on(ctx(app), "2026-10-19")}  # 1am on the 20th: the 19th's
    tuesday = {f["title"] for f in fixed_on(ctx(app), "2026-10-20")}
    assert "Night shift" not in tuesday and "Early ferry" in tuesday  # 2am on the 21st: the night of the 20th
    assert "Early ferry" not in {f["title"] for f in fixed_on(ctx(app), "2026-10-21")}


def test_what_if_gives_its_events_only_to_the_calendar_marked_for_show(app: App) -> None:
    def tried(with_hidden: bool) -> dict[str, dict]:
        out = app.do("whatif", changes=[{"command": "add", "input": {"text": "dinner with Sam thu 19:00-20:00"}}],
                     start="2026-10-19T00:00", end="2026-10-26T00:00", with_hidden=with_hidden)  # fmt: skip
        return {f["title"]: f for f in out["plan"]["fixed"]}

    assert "Rocketry meeting" in tried(False)
    hide(app)
    assert "Rocketry meeting" not in tried(False) and "Dentist" in tried(False)
    marked = tried(True)  # as the calendar asks, for its Show switch to leave out (web/src/plan/shown.ts)
    assert marked["Rocketry meeting"]["hidden_calendar"] == "Clubs" and marked["Dentist"]["hidden_calendar"] is None


def test_other_ways_and_a_rule_preview_name_no_event_of_it(app: App) -> None:
    hide(app)
    hidden = {"Rocketry meeting", "Rocketry social", "Rocketry launch", "Gym", "Career fair", "Choir"}
    way = app.do("other_way", seed=1)["way"]
    assert way is None or not {b["title"] for b in way["blocks"]} & hidden
    preview = app.do("preview_weights", weights={"late_night": 3.0})
    assert not {m["title"] for m in preview["moved"]} & hidden
    horizon = app.do("plan")  # what a week is drawn with: its fixed times
    assert not {f["title"] for f in horizon["fixed"]} & hidden and "Dentist" in {f["title"] for f in horizon["fixed"]}
