"""Random situations for the fixes from "Friday Notes-3" that need a whole Friday (27 Nov: the user asked for
"hundreds + random tests"). Each case is a scratch Friday built from generated choices; the rules are checked, not
answers written down.

- A break day's morning brief is that day's list: the same things, in the same order, no pace, the break named.
- An event on several calendars is hidden only when every one of them is, and shown as one that shows."""

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.planner.hidden import hidden_of
from friday.planner.service import replan
from friday.planner.store import load_settings
from tests.commands.helpers import new_app
from tests.sync.test_mac_calendars import calendar, post

SOME = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
DAYS = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"]  # Mon-Sun

todo = st.tuples(
    st.integers(15, 240),  # minutes
    st.one_of(st.none(), st.integers(-3, 6)),  # due, days from Monday
    st.sampled_from(["hard", "soft"]),
)


@SOME
@given(
    mode=st.sampled_from(["light", "off"]),
    plan_repeating=st.booleans(),
    plan_meals=st.booleans(),
    todos=st.lists(todo, max_size=6),
    errand_from=st.sampled_from([None, 1, 2]),  # a daily errand from Tuesday, Wednesday, or none
    reading=st.booleans(),
    morning=st.sampled_from([2, 3, 4]),  # a morning on the break (Wed-Fri)
    hour=st.integers(5, 20),
)
def test_a_break_days_brief_is_its_list_with_no_pace(
    mode, plan_repeating, plan_meals, todos, errand_from, reading, morning, hour
) -> None:
    app = new_app(Path(tempfile.mkdtemp()), now=f"{DAYS[0]}T08:05", horizon_days=7)
    for n, (minutes, due, firmness) in enumerate(todos):
        more = {}
        if due is not None:
            day = DAYS[0] if due < 0 else DAYS[min(due, 6)]
            more = {"due": f"{day}T17:00" if due >= 0 else "2026-10-16T17:00", "firmness": firmness}
        app.do("add", title=f"Task {n}", duration_min=minutes, **more)
    if errand_from is not None:
        app.do("series_add", title="Groceries", every="day", duration_min=45, release_offset_min=540,
               due_offset_min=1200, start_date=DAYS[errand_from])  # fmt: skip
    if reading:
        app.do("series_add", title="DLI reading", every="tue", duration_min=75, start_date="2026-10-13",
               due_offset_min=1200, firmness="hard")  # fmt: skip
    app.do("vacation_add", name="Fall break", start=DAYS[2], end=DAYS[4], mode=mode, plan_repeating=plan_repeating,
           plan_meals=plan_meals)  # fmt: skip
    app.at(f"{DAYS[morning]}T{hour:02d}:05")
    replan(app.conn, app.now_utc)
    brief = app.do("brief")
    listed = [t["title"] for t in app.do("vacation_day", date=DAYS[morning])["items"]]
    assert brief["vacation"] is not None and brief["vacation"]["mode"] == mode
    assert [r["title"] for r in brief["rocks"]] == listed  # the same things, in the same order
    assert brief["pace"] is None and "pace" not in brief["summary"].lower()


@SOME
@given(mode=st.sampled_from(["light", "off"]), outside=st.sampled_from([0, 5]), hour=st.integers(5, 20))
def test_a_day_outside_the_break_names_no_break(mode, outside, hour) -> None:
    app = new_app(Path(tempfile.mkdtemp()), now=f"{DAYS[0]}T08:05", horizon_days=7)
    app.do("add", title="Essay", duration_min=60, due=f"{DAYS[6]}T17:00", firmness="hard")
    app.do("vacation_add", name="Fall break", start=DAYS[2], end=DAYS[4], mode=mode)
    app.at(f"{DAYS[outside]}T{hour:02d}:05")
    replan(app.conn, app.now_utc)
    assert app.do("brief")["vacation"] is None


@SOME
@given(count=st.integers(2, 4), data=st.data())
def test_an_event_on_several_calendars_is_hidden_only_when_all_are(count, data) -> None:
    cals = [calendar(f"hol-{n}", f"Holidays {n}", color=["#0b8043", "#039be5", "#d50000", "#f6bf26"][n])
            for n in range(count)]  # fmt: skip
    hidden = data.draw(st.sets(st.sampled_from([c["name"] for c in cals])))
    app = new_app(Path(tempfile.mkdtemp()))
    app.do("settings_set", key="gcal", value={"include_all_day": True})
    post(app, cals, [])
    for c in cals:
        app.do("calendar_set", id=c["id"], mac=True, on=True, trusted=True)
    event = lambda c: {"id": f"tg-{c['id']}", "calendar": c["id"], "title": "Thanksgiving",  # noqa: E731
                       "start": "2026-10-22", "end": "2026-10-23", "all_day": True}  # fmt: skip
    post(app, cals, [event(c) for c in cals], minutes_later=1)
    [kept] = [i for i in app.table("items") if i["title"] == "Thanksgiving" and i["status"] == "todo"]  # kept once
    look = load_settings(app.conn)["calendar_look"].model_dump()
    app.do("settings_set", key="calendar_look", value=look | {"toolbar": sorted(hidden)})
    is_hidden = kept["id"] in hidden_of(app.conn, load_settings(app.conn), 1).events
    shown_as = app.do("item", id=kept["id"])["item"]["calendar"]
    assert is_hidden == (len(hidden) == count)
    if not is_hidden:
        assert shown_as not in hidden  # shown as a calendar that shows
