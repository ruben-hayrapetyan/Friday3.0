"""An early event wakes you only when you're going (14 Nov, your answer "Give the sleep back"): a 6am club you said is
optional and haven't chosen is Friday's to decide, and a plan woke you at 5:30 for one, then gave the club's time to
exam prep while the evening before was kept for sleep. Now an optional one you haven't chosen leaves the night and the
morning as usual; one you said you're going to, or one that isn't optional, still wakes you (29 Oct). The test nights:
bed 11:30pm, up 7:30am, Monday 2026-10-19 in New York; the club is Wednesday 6–8am."""

from pathlib import Path

import pytest

from friday.core.time import format_utc, parse_local, to_utc
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import TZ, App, new_app

TUESDAY_NIGHT = parse_local("2026-10-20T00:00").date()


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=4)


def club(app: App, optional: bool = True) -> int:
    club_id = app.do("add", title="Climbing Club", when="fixed", start="2026-10-21T06:00", end="2026-10-21T08:00")
    if optional:
        app.do("rule_add", text="climbing club only if i'm ahead")
    return club_id["item"]["id"]


def wake_after_tuesday(app: App) -> str:
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    return format_utc(problem.nights[TUESDAY_NIGHT].wake_utc)


def utc(local: str) -> str:
    return format_utc(to_utc(parse_local(local), TZ))


def test_an_optional_early_event_you_haven_t_chosen_leaves_your_wake_as_usual(app: App) -> None:
    club(app)
    assert wake_after_tuesday(app) == utc("2026-10-21T07:30")


def test_one_you_said_you_re_going_to_wakes_you_for_it(app: App) -> None:
    app.do("event_keep", id=club(app), going=True)
    assert wake_after_tuesday(app) == utc("2026-10-21T06:00")


def test_one_that_isn_t_optional_wakes_you_for_it(app: App) -> None:
    club(app, optional=False)
    assert wake_after_tuesday(app) == utc("2026-10-21T06:00")


def tuesday_evening(app: App, going: bool) -> tuple[list[tuple[str, str]], list[str]]:
    """Tuesday 9am–10pm taken; a 2-hour essay due Wednesday at 9am, and 8 hours of sleep a night: the essay's blocks
    from Tuesday 10pm to Wednesday 9am, and the plan's notes."""
    club_id = club(app)
    if going:
        app.do("event_keep", id=club_id, going=True)
    app.do("add", title="Lab", when="fixed", start="2026-10-19T09:00", end="2026-10-20T22:00")
    app.do("add", title="Essay", duration_min=120, due="2026-10-21T09:00")
    app.do("rule_add", text="at least 8 hours of sleep")
    replan(app.conn, app.now_utc)
    blocks = app.do("plan", start="2026-10-20T00:00", end="2026-10-22T00:00")["blocks"]
    essay = sorted((b["start"], b["end"]) for b in blocks if b["title"] == "Essay")
    return essay, app.do("status")["notices"]


def test_unchosen_you_sleep_through_the_club_and_the_morning_is_a_normal_one(app: App) -> None:
    """Up at 7:30 as usual: nothing is planned from 4am to 7:30 (you'd have been woken at 6 for the club before), and
    the essay takes the evening and your usual morning."""
    essay, notices = tuesday_evening(app, going=False)
    assert essay and not any("2026-10-21T04:00" <= start < "2026-10-21T07:30" for start, _ in essay), essay
    assert any(n.startswith("Skip Climbing Club on Wed at 6am: it’s before you’d be up") for n in notices), notices
    assert not app.do("status")["late"]


def test_going_the_evening_before_is_your_night_and_the_club_s_time_is_kept(app: App) -> None:
    essay, notices = tuesday_evening(app, going=True)
    assert not any("2026-10-21T06:00" <= start < "2026-10-21T08:00" for start, _ in essay)
    assert not any("Climbing Club" in n for n in notices)
