"""A calendar you hid is ignored everywhere but the plan (14 Nov: a client set calendars to "Hide" in Setup's walk, and
their invitations still came into the Inbox). Friday keeps reading it, plans around it when you count it busy, but
nothing of it surfaces: not in the Inbox and its count, not in what's on now and next, search, the brief, the week's
review, exams, rules, the AI's context, skip suggestions, Settings → Repeating; and the plan gives its events only to
the calendar, which asks for them (`with_hidden`), marked, for Show to switch on. Showing it again brings it all back.

Black box: Mac calendars posted as the Mac app posts them, hidden through Setup's walk (`setup_save`) and shown again
through Settings → Calendars (`settings_set`), each place read through its query."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.claude import context
from friday.commands.explain import shaping
from friday.commands.learning import fixed_on
from friday.commands.registry import Ctx
from friday.commands.writer import Writer
from friday.core.time import parse_local, to_utc
from friday.planner.snapshot import take_snapshot
from friday.planner.store import load_settings
from friday.planner.views import skip_actions
from tests.commands.helpers import TZ, App, new_app
from tests.sync.test_mac_calendars import calendar, mac_event, post

HOME, CLUBS = calendar("home", "Home"), calendar("clubs", "Clubs")  # read straight in
FRIENDS, INVITES = calendar("friends", "Friends"), calendar("invites", "Invites")  # through the Inbox
CALENDARS = [HOME, CLUBS, FRIENDS, INVITES]
EVENTS = [
    mac_event("d", "home", "Dentist", "2026-10-19T10:00", "2026-10-19T11:00"),
    mac_event("r", "clubs", "Rocketry meeting", "2026-10-19T09:30", "2026-10-19T10:00"),
    mac_event("s", "clubs", "Rocketry social", "2026-10-22T19:00", "2026-10-22T20:00"),
    mac_event("l", "clubs", "Rocketry launch", "2026-10-27T10:00", "2026-10-27T12:00"),
    *(mac_event(f"g{d}", "clubs", "Gym", f"2026-10-{d}T07:30", f"2026-10-{d}T08:30", series="gym") for d in (21, 28)),
    mac_event("m", "friends", "Movie night", "2026-10-22T19:00", "2026-10-22T21:00"),
    mac_event("c", "invites", "Career fair", "2026-10-21T14:00", "2026-10-21T16:00"),
    *(
        mac_event(f"h{d}", "invites", "Choir", f"2026-10-{d}T18:00", f"2026-10-{d}T19:00", series="choir")
        for d in (20, 27)
    ),  # fmt: skip
]


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)  # Monday 19 October, 9am
    post(app, CALENDARS, [])
    for c in (FRIENDS, INVITES):
        app.do("calendar_set", id=c["id"], mac=True, trusted=False)
    post(app, CALENDARS, EVENTS, minutes_later=1)
    return app


def hide(app: App) -> None:
    """Setup's walk: Clubs hidden but still kept clear of work (as Settings' "Keep work off it anyway" leaves it),
    Invites hidden as the walk's Hide sets it."""
    picked = [
        {"name": "Home", "shown": True, "busy": True},
        {"name": "Friends", "shown": True, "busy": True},
        {"name": "Clubs", "shown": False, "busy": True},
        {"name": "Invites", "shown": False, "busy": False},
    ]
    app.do("setup_save", **(app.do("setup")["answers"] | {"calendars": picked}))


def show(app: App) -> None:
    """Settings → Calendars: both back to Plan around it."""
    look = app.do("settings")["calendar_look"]
    app.do("settings_set", key="calendar_look", value=look | {"toolbar": []})


def waiting(app: App) -> set[str]:
    return {s["input"].get("title") for s in app.do("inbox")["suggestions"]}


def fixed(app: App, **extra: Any) -> dict[str, dict]:
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-11-02T00:00", **extra)
    return {f["title"]: f for f in plan["fixed"]}


def ctx(app: App) -> Ctx:
    return Ctx(app.conn, Writer(app.conn, 1), app.now_utc, "you", 1, load_settings(app.conn))


def test_its_invitations_leave_the_inbox_and_its_count_and_come_back_shown(app: App) -> None:
    assert {"Movie night", "Career fair"} <= waiting(app)
    assert app.do("status")["suggestions"] == len(app.do("inbox")["suggestions"])
    hide(app)
    assert "Movie night" in waiting(app) and "Career fair" not in waiting(app)
    assert app.do("status")["suggestions"] == len(app.do("inbox")["suggestions"])  # the count the badges show
    show(app)
    assert "Career fair" in waiting(app)
    assert app.do("status")["suggestions"] == len(app.do("inbox")["suggestions"])


def test_its_repeating_events_dont_wait_to_be_imported(app: App) -> None:
    def repeats() -> set[str]:
        return {r["title"] for r in app.do("calendar_repeats")}

    assert "Choir" in repeats() and app.do("inbox")["repeats"] == 1
    hide(app)
    assert "Choir" not in repeats() and app.do("inbox")["repeats"] == 0
    show(app)
    assert "Choir" in repeats()


def test_the_plan_gives_its_events_only_to_the_calendar_marked_for_show(app: App) -> None:
    assert "Rocketry meeting" in fixed(app) and fixed(app)["Rocketry meeting"]["hidden_calendar"] is None
    hide(app)
    assert "Rocketry meeting" not in fixed(app) and "Dentist" in fixed(app)  # the plan as anything else reads it
    marked = fixed(app, with_hidden=True)  # as the calendar reads it, for its Show switch
    assert (
        marked["Rocketry meeting"]["hidden_calendar"] == "Clubs" and marked["Rocketry meeting"]["calendar"] == "Clubs"
    )
    assert marked["Gym"]["hidden_calendar"] == "Clubs" and marked["Dentist"]["hidden_calendar"] is None
    show(app)
    assert "Rocketry meeting" in fixed(app)


def test_now_never_names_it_but_its_busy_time_ends_your_free_time(app: App) -> None:
    assert app.do("now")["next"]["title"] == "Rocketry meeting"
    hide(app)
    now = app.do("now")
    assert now["next"]["title"] == "Dentist"  # what's next, for the Now dock and Siri
    assert now["gap_minutes"] == 30  # free until the hidden meeting at 9:30, which still keeps work off its time
    # and the bar says until when you're free as its length does (24 Nov, the agreement check: "Free until" the
    # Dentist's time, beside the 30 minutes to the hidden meeting)
    assert now["free_until"].endswith("T09:30") and now["free_until"] < now["next"]["start"]
    show(app)
    assert app.do("now")["next"]["title"] == "Rocketry meeting"


def test_a_hidden_event_happening_now_is_not_what_you_are_doing(app: App) -> None:
    hide(app)
    app.at("2026-10-19T09:40")
    now = app.do("now")
    assert now["current"] is None and now["next"]["title"] == "Dentist" and now["gap_minutes"] == 0


def test_search_the_brief_and_the_week_leave_it_out(app: App) -> None:
    def week() -> tuple[set[str], float]:
        out = app.do("week_review", date="2026-10-19")
        return {c["title"] for c in out["coming"]}, sum(out["fixed_h"].values())

    assert [e["title"] for e in app.do("events", text="rocketry")] == [
        "Rocketry meeting",
        "Rocketry social",
        "Rocketry launch",
    ]
    assert "Rocketry meeting" in {f["title"] for f in app.do("brief")["fixed"]}
    coming, hours = week()
    assert "Rocketry launch" in coming
    hide(app)
    assert app.do("events", text="rocketry") == []
    assert {f["title"] for f in app.do("brief")["fixed"]} == {"Dentist"}
    assert week() == (coming - {"Rocketry launch", "Gym"}, hours - 0.5 - 1 - 1)  # meeting, social, Wednesday's gym
    show(app)
    assert len(app.do("events", text="rocketry")) == 3


def test_settings_repeating_leaves_out_its_repeats(app: App) -> None:
    assert "Gym" in {s["title"] for s in app.do("series_list")}
    hide(app)
    assert "Gym" not in {s["title"] for s in app.do("series_list")}
    show(app)
    assert "Gym" in {s["title"] for s in app.do("series_list")}


def test_a_rule_doesnt_say_it_matches_a_hidden_event(app: App) -> None:
    def matches(text: str) -> str:
        return app.do("rule_read", text=text)["effect"]

    assert "Rocketry meeting" in matches("rocketry is optional")
    hide(app)
    assert "Rocketry" not in matches("rocketry is optional") and "Dentist" in matches("dentist is optional")


def test_accepting_an_invitation_doesnt_name_the_hidden_event_it_clashes_with(app: App) -> None:
    (movie,) = [s for s in app.do("inbox")["suggestions"] if s["input"].get("title") == "Movie night"]
    assert [c["title"] for c in app.do("suggestion_effect", id=movie["id"])["clashes"]] == ["Rocketry social"]
    hide(app)
    assert app.do("suggestion_effect", id=movie["id"])["clashes"] == []


def test_skips_offered_for_late_work_leave_it_out(app: App) -> None:
    task = app.do("add", title="Essay", preset="Assignment", duration_min=60, due="2026-10-23T23:00")["item"]["id"]

    def offered() -> set[str]:
        return {title for *_, title in skip_actions(take_snapshot(app.conn, app.now_utc), {task: 1.0}, {}, frozenset())}

    assert {"Rocketry meeting", "Dentist"} <= offered()
    hide(app)
    assert "Rocketry meeting" not in offered() and "Dentist" in offered()


def test_the_ai_the_day_comparison_and_why_a_block_starts_where_it_does_leave_it_out(app: App) -> None:
    def said(c: Ctx) -> str:
        return context(c)

    assert "Rocketry meeting" in said(ctx(app)) and "Gym" in said(ctx(app))
    assert "Rocketry meeting" in {f["title"] for f in fixed_on(ctx(app), "2026-10-19")}
    ten = to_utc(parse_local("2026-10-19T10:00"), TZ)
    assert "Rocketry meeting" in (shaping(ctx(app), ten) or "")
    hide(app)
    assert "Rocketry" not in said(ctx(app)) and "Gym" not in said(ctx(app)) and "Dentist" in said(ctx(app))
    assert {f["title"] for f in fixed_on(ctx(app), "2026-10-19")} == {"Dentist"}
    assert "Rocketry" not in (shaping(ctx(app), ten) or "")


def test_the_walk_still_lists_it_with_its_events_to_show_it_again(app: App) -> None:
    hide(app)
    out = app.do("setup")
    assert out["events"]["Clubs"] == 5  # the place to choose, so its events are counted
    assert {c["name"]: c["shown"] for c in out["answers"]["calendars"]}["Clubs"] is False
