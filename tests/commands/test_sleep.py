"""Tracking your sleep: off until you turn it on; taps, corrections, what's offered when, and what's learned."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local, parse_utc, to_utc
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def on(app: App) -> None:
    app.do("settings_set", key="sleep_tracking", value={"on": True})


def test_it_is_off_until_you_turn_it_on(app: App) -> None:
    assert app.do("sleep") == app.do("sleep") | {"on": False, "nights": [], "next": None}
    with pytest.raises(FieldError, match="sleep tracking is off"):
        app.do("sleep_mark", kind="up")


def test_a_morning_tap_then_ready_then_bed(app: App) -> None:  # it's Monday 9am
    on(app)
    assert app.do("sleep")["next"] == "up"
    assert app.do("sleep_mark", kind="up", at="2026-10-19T08:10")["message"] == "Good morning: 8:10am"
    assert app.do("sleep")["next"] == "ready"
    app.do("sleep_mark", kind="ready")
    out = app.do("sleep")
    assert (out["up"], out["ready"], out["next"]) == ("2026-10-19T08:10", "2026-10-19T09:00", None)
    app.now_utc += 12 * 60 + 30  # 9:30pm, within four hours of an 11:30pm bedtime
    assert app.do("sleep")["next"] == "done"
    assert app.do("sleep_mark", kind="done")["message"] == "Done with work: 9:30pm"
    assert (app.do("sleep")["next"], app.do("sleep")["done"]) == ("bed", "2026-10-19T21:30")
    app.do("sleep_mark", kind="bed")
    assert app.do("sleep")["next"] is None


def test_a_tap_can_be_moved_or_taken_back_but_not_set_in_the_future(app: App) -> None:
    on(app)
    app.do("sleep_mark", kind="up")
    (night,) = app.do("sleep")["nights"]
    app.do("sleep_mark_edit", id=night["up_id"], at="2026-10-19T07:30")
    assert app.do("sleep")["nights"][0]["up"] == "2026-10-19T07:30"
    with pytest.raises(FieldError, match="later than now"):
        app.do("sleep_mark_edit", id=night["up_id"], at="2026-10-19T11:00")
    app.do("sleep_mark_remove", id=night["up_id"])
    assert app.do("sleep")["nights"] == []


def test_weeks_of_late_nights_are_offered_as_a_later_bedtime(app: App) -> None:
    on(app)
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        evening = first + timedelta(days=n)
        morning = evening + timedelta(days=1)
        app.do("sleep_mark", kind="bed", at=f"{morning}T00:50")
        app.do("sleep_mark", kind="up", at=f"{morning}T08:30")
    out = app.do("sleep")
    bedtimes = [c for c in out["changes"] if c["field"] == "bedtime"]
    assert bedtimes and all(c["learned"] == "00:45" for c in bedtimes)
    assert out["suggested"]["tue"]["bedtime"] == "00:45" and out["average_slept_min"] == 7 * 60 + 40
    app.do("settings_set", key="sleep", value=out["suggested"])  # "Use these times"
    assert not [c for c in app.do("sleep")["changes"] if c["field"] == "bedtime"]


def problem_of(app: App):
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    return build_problem(build_input(take_snapshot(app.conn, app.now_utc)))


def slot_at(problem, local: str) -> int:
    return next(s for s, slot in enumerate(problem.grid.slots) if slot.start_utc == app_utc(problem, local))


def app_utc(problem, local: str) -> int:

    return to_utc(parse_local(local), problem.grid.spec.timezone)


def test_a_learned_routine_keeps_the_morning_light_for_as_long_as_it_takes(app: App) -> None:
    on(app)
    app.do("add", text="essay ~2h due fri")
    for n in range(5):  # five weekday mornings: up at 7:30, ready at 9
        morning = date(2026, 10, 12) + timedelta(days=n)
        app.do("sleep_mark", kind="up", at=f"{morning}T07:30")
        app.do("sleep_mark", kind="ready", at=f"{morning}T09:00")
    assert app.do("sleep")["routine_min"]["tue"] == 90
    problem = problem_of(app)
    late = next(r for r in problem.rules if r.type == "late_night")
    essay = next(iter(problem.items.values()))
    assert late.price(essay, slot_at(problem, "2026-10-20T08:30")) > 0  # Tuesday 8:30, inside the 90 minutes
    assert late.price(essay, slot_at(problem, "2026-10-20T09:00")) == 0


def test_up_early_frees_the_morning(app: App) -> None:
    on(app)
    app.now_utc -= 3 * 60  # Monday 6am, an hour and a half before the 7:30 wake
    before = problem_of(app)
    assert before.core[slot_at(before, "2026-10-19T06:30")]
    app.do("sleep_mark", kind="up")
    after = problem_of(app)
    assert not after.core[slot_at(after, "2026-10-19T06:30")]


def test_a_short_night_makes_the_next_nights_dearer(app: App) -> None:
    on(app)
    assert problem_of(app).nights[date(2026, 10, 19)].debt_hours == 0
    app.do("sleep_mark", kind="bed", at="2026-10-19T03:00")  # Sunday night: four hours of a seven-hour night
    app.do("sleep_mark", kind="up", at="2026-10-19T07:00")  # (12:30am to 7:30am)
    assert problem_of(app).nights[date(2026, 10, 19)].debt_hours == 3.0


def test_the_brief_offers_an_easy_day_after_a_short_night(app: App) -> None:
    on(app)
    assert app.do("brief")["sleep"] is None
    app.do("sleep_mark", kind="bed", at="2026-10-19T03:00")
    app.do("sleep_mark", kind="up", at="2026-10-19T07:00")
    assert app.do("brief")["sleep"].startswith("You slept 4h last night")


def test_the_review_asks_for_the_taps_you_forgot_and_a_skip_stops_it(app: App) -> None:
    assert app.do("review", date="2026-10-18")["sleep"] == []  # off: nothing asked
    on(app)
    asks = {a["kind"]: a for a in app.do("review", date="2026-10-18")["sleep"]}  # yesterday, Sunday
    assert set(asks) == {"up", "ready", "done", "bed"} and asks["up"]["at"] == "2026-10-18T09:00"  # usual Sunday wake
    assert asks["done"]["at"] == "2026-10-18T23:30"  # an hour before a 12:30am Sunday-night bedtime
    app.do("sleep_mark", kind="up", at="2026-10-18T09:40")
    app.do("sleep_skip", date="2026-10-18", kind="ready")
    assert [a["kind"] for a in app.do("review", date="2026-10-18")["sleep"]] == ["done", "bed"]
    app.at("2026-10-19T11:00")
    assert [a["kind"] for a in app.do("review")["sleep"]] == ["up", "ready"]  # today: tonight isn't over


# 19 Nov: "i keep getting a 'when were you ready to work' 'when did you go to bed'... in my inbox and i think those
# messages should only come up once the user has not marked it outside of their expected time. so say my morning
# routine was usually 20 mins. if i hadn't clicked 'ready to work' in 2 hours, it should ask (and remember this is
# only if you are tracking it)". A tap is asked about once it's two hours past its usual time and still not made.


def today_asked(app: App, at: str) -> list[str]:
    return [a["kind"] for a in app.at(at).do("review")["sleep"]]


def test_a_tap_isnt_asked_about_before_its_two_hours_past_its_usual_time(app: App) -> None:
    on(app)  # Monday: up usually at 7:30, ready an hour later (no routine learned yet)
    assert today_asked(app, "2026-10-19T07:00") == []
    assert today_asked(app, "2026-10-19T09:29") == []  # up is late, not yet two hours late
    assert today_asked(app, "2026-10-19T09:30") == ["up"]
    assert today_asked(app, "2026-10-19T10:30") == ["up", "ready"]


def test_ready_is_asked_two_hours_after_your_usual_routine_from_when_you_got_up(app: App) -> None:
    on(app)
    for day in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"):  # five weekdays
        app.at(f"{day}T07:30").do("sleep_mark", kind="up")
        app.at(f"{day}T08:00").do("sleep_mark", kind="ready")  # a half-hour routine, learned
    app.at("2026-10-19T08:00").do("sleep_mark", kind="up")
    assert today_asked(app, "2026-10-19T10:29") == []
    assert today_asked(app, "2026-10-19T10:30") == ["ready"]  # up at 8, usually ready half an hour later, two hours on
    app.do("sleep_mark", kind="ready", at="2026-10-19T08:35")
    assert today_asked(app, "2026-10-19T10:40") == []


def test_last_nights_taps_are_asked_once_their_time_is_two_hours_gone(app: App) -> None:
    on(app)
    asked = [a["kind"] for a in app.at("2026-10-19T09:00").do("review", date="2026-10-18")["sleep"]]
    assert asked == ["up", "ready", "done", "bed"]  # yesterday's are all long past


def test_done_with_work_is_not_offered_while_a_timer_runs(app: App) -> None:
    on(app)
    app.now_utc += 11 * 60  # 8pm
    chore = app.do("add", text="laundry ~1h")["item"]["id"]
    app.do("start", id=chore)
    assert app.do("sleep")["next"] is None
    app.do("stop")
    assert app.do("sleep")["next"] == "done"


def test_after_done_with_work_nothing_more_is_planned_that_night(app: App) -> None:
    """14 Nov, your answer: after "Done with work", nothing at all is planned that night; what then can't be done on
    time shows as late, for the Inbox to ask about. (Before, work after the tap only cost as working past bedtime does,
    and a night already broken for one deadline was filled with work due days later: Math HW due in 5 days at 3am.)"""
    on(app)
    app.now_utc += 11 * 60  # Monday 8pm
    reading = app.do("add", text="reading ~2h due fri 5pm")["item"]["id"]
    urgent = app.do("add", title="Quiz corrections", duration_min=45, due="2026-10-19T23:00")["item"]["id"]
    app.do("replan")
    tonight = lambda: [  # noqa: E731
        b for b in app.do("plan", start="2026-10-19T20:00", end="2026-10-20T10:00")["blocks"] if not b.get("fixed")
    ]
    assert any(b["item_id"] == urgent for b in tonight())  # before the tap: due tonight, so planned tonight
    app.do("sleep_mark", kind="done")
    app.do("replan")
    assert tonight() == []  # nothing after the tap, not even what's due tonight
    status = app.do("status")
    late = {i["item_id"] for i in [*status["late_items"], *status["slipping"]]}
    assert urgent in late and reading not in late  # the quiz is late, for you to decide; the reading waits for Tuesday
    assert any(
        b["item_id"] == reading for b in app.do("plan", start="2026-10-20T10:00", end="2026-10-24T00:00")["blocks"]
    )


def test_the_tap_starts_the_nights_wall_and_a_later_bedtime_doesnt_move_it(app: App) -> None:
    """The night's wall (never planned in) starts at the tap when that's before bedtime's margin; a tap after it
    changes nothing, and a tap last night doesn't reach tonight."""
    from friday.engine.problem import Night

    night = Night(bedtime_utc=1000, wake_utc=1500, margin_min=60, done_utc=900)
    assert night.core == (900, 1500)
    assert Night(bedtime_utc=1000, wake_utc=1500, margin_min=60, done_utc=1200).core == (1060, 1500)
    assert Night(bedtime_utc=1000, wake_utc=1500, margin_min=60).core == (1060, 1500)
    on(app)
    app.now_utc += 11 * 60  # Monday 8pm
    app.do("sleep_mark", kind="done")
    problem = problem_of(app)
    nights = sorted(problem.nights.items())
    tonight = next(n for d, n in nights if str(d) == "2026-10-19")
    assert tonight.core[0] == app.now_utc  # from the tap, 8pm
    assert all(n.core[0] == n.bedtime_utc + n.margin_min for d, n in nights if str(d) != "2026-10-19")


def test_a_tap_after_midnight_still_ends_that_nights_work(app: App) -> None:
    """Your case, 14 Nov: "Done with work" at 12:48am, bedtime later than that; the night's work due days later (and
    a chore that runs by itself) was planned at 1am to 3:30am."""
    on(app)
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    app.do(
        "settings_set", key="sleep", value={d: {"wake": "11:00", "bedtime": "03:00", "margin_min": 30} for d in days}
    )
    app.now_utc += 16 * 60 + 48  # Tuesday 12:48am, Monday's night
    # due at 4pm with an 11am wake: before, this broke the night, and the rest of the night was filled
    app.do("add", title="CUAI HW", duration_min=360, due="2026-10-20T16:00")
    later = app.do("add", title="Math HW", duration_min=30, due="2026-10-24T00:00")["item"]["id"]
    app.do("replan")
    night = lambda: [  # noqa: E731
        b for b in app.do("plan", start="2026-10-20T00:48", end="2026-10-20T11:00")["blocks"] if not b.get("fixed")
    ]
    app.do("sleep_mark", kind="done")
    app.do("replan")
    assert night() == []
    assert any(
        b["item_id"] == later for b in app.do("plan", start="2026-10-20T11:00", end="2026-10-24T00:00")["blocks"]
    )


def test_the_wind_down_is_learned_from_done_to_bed(app: App) -> None:
    on(app)
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        evening = first + timedelta(days=n)
        app.do("sleep_mark", kind="done", at=f"{evening}T22:00")
        app.do("sleep_mark", kind="bed", at=f"{evening}T23:15")
    out = app.do("sleep")
    assert out["nights"][0]["wind_down_min"] == 75 and out["nights"][0]["done"].endswith("T22:00")
    assert out["wind_down_min"]["mon"] == 75


def test_a_night_less_than_an_hour_short_offers_nothing(app: App) -> None:
    on(app)
    app.do("sleep_mark", kind="bed", at="2026-10-19T00:45")  # Sunday night: 6h45 of a seven-hour night
    app.do("sleep_mark", kind="up", at="2026-10-19T07:30")
    assert app.do("brief")["sleep"] is None


def test_moving_a_tap_that_isnt_there_says_so(app: App) -> None:
    on(app)
    with pytest.raises(FieldError, match="no sleep mark 99"):
        app.do("sleep_mark_edit", id=99, at="2026-10-19T07:30")


def test_learned_times_that_break_your_sleep_rule_say_so(app: App) -> None:
    on(app)
    app.do("rule_add", text="at least 8 hours of sleep")
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        morning = first + timedelta(days=n + 1)
        app.do("sleep_mark", kind="bed", at=f"{morning}T00:50")
        app.do("sleep_mark", kind="up", at=f"{morning}T08:30")
    out = app.do("sleep")
    assert out["suggested"] and out["against"]
    assert all("under your 8 h rule" in said for said in out["against"])


def test_done_with_work_is_offered_by_6pm_even_after_a_late_learned_bedtime(app: App) -> None:
    """14 Nov: a user never saw "Done with work" (so never "Going to bed") once Friday had a late bedtime: it was
    offered only from four hours before it. Now from 6pm at the latest; earlier when bedtime puts it earlier."""
    on(app)
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    app.do(
        "settings_set", key="sleep", value={d: {"wake": "10:00", "bedtime": "03:30", "margin_min": 30} for d in days}
    )
    app.at("2026-10-19T17:55")
    assert app.do("sleep")["next"] != "done"
    app.at("2026-10-19T18:00")
    assert app.do("sleep")["next"] == "done"
    app.do("sleep_mark", kind="done")
    assert app.do("sleep")["next"] == "bed"  # and Going to bed right after it, whatever the hour


def test_im_up_is_offered_after_a_night_whatever_the_hour(app: App) -> None:
    """14 Nov: "I'm up" was offered only from 4am to 3pm, so someone up at 3:30pm after a late night never saw it.
    Once you've said you're going to bed, it's offered until you say you're up: from two hours after the bed tap."""
    on(app)
    app.at("2026-10-20T05:00")
    app.do("sleep_mark", kind="bed")  # to bed at 5am
    app.at("2026-10-20T06:30")
    assert app.do("sleep")["next"] is None  # just gone to bed: not "I'm up" yet
    app.at("2026-10-20T15:30")
    assert app.do("sleep")["next"] == "up"  # up mid-afternoon: still offered
    app.do("sleep_mark", kind="up")
    assert app.do("sleep")["next"] == "ready"


def test_done_with_work_at_4am_still_offers_going_to_bed(app: App) -> None:
    """14 Nov: past 4am the day starts again; "Done with work" tapped then is the night before's, and "Going to bed"
    must still follow it (not "Done with work" again, nor nothing)."""
    on(app)
    app.at("2026-10-20T04:10")
    app.do("sleep_mark", kind="done")
    app.at("2026-10-20T04:20")
    assert app.do("sleep")["next"] == "bed"
    app.do("sleep_mark", kind="bed")
    app.at("2026-10-20T12:30")
    assert app.do("sleep")["next"] == "up"
    app.do("sleep_mark", kind="up")
    night = next(n for n in app.do("sleep")["nights"] if n["date"] == "2026-10-19")
    assert night["bed"] and night["up"]  # one night, from bed at 4:20am to up at 12:30pm


def current_blocks(app: App, item_id: int) -> list[tuple[str, str]]:
    found = app.conn.execute(
        "SELECT b.start_utc, b.end_utc FROM blocks b JOIN plans p ON p.id = b.plan_id "
        "WHERE p.status = 'current' AND b.item_id = ? ORDER BY b.start_utc",
        [item_id],
    ).fetchall()
    return [(r[0], r[1]) for r in found]


def utc(local: str) -> str:
    from friday.core.time import format_utc  # noqa: PLC0415

    return format_utc(to_utc(parse_local(local), "America/New_York"))


def test_what_was_planned_while_you_slept_in_didnt_happen(tmp_path: Path) -> None:
    """21 Nov, a user's screenshot: up at 12:04, and the 11:45 lunch of the plan made before stayed on the day beside
    the new one. Planned at 7am for 9 to 11, up at 11: those two hours weren't done, and aren't kept on the day."""
    from friday.planner.prepare import assumed_blocks  # noqa: PLC0415

    app = new_app(tmp_path, now="2026-10-19T07:00")
    on(app)
    essay = app.do("add", text="essay ~2h due tue")["item"]["id"]
    app.do("replan")
    assert current_blocks(app, essay) == [(utc("2026-10-19T09:00"), utc("2026-10-19T11:00"))]
    app.now_utc += 4 * 60  # 11am
    app.do("sleep_mark", kind="up")
    assert assumed_blocks(take_snapshot(app.conn, app.now_utc)) == []  # not two hours done in your sleep
    app.do("replan")
    planned = current_blocks(app, essay)
    assert planned and all(start >= utc("2026-10-19T11:00") for start, _ in planned)  # none before you were up
    assert sum(parse_utc(end) - parse_utc(start) for start, end in planned) == 120  # all of it still to do


def test_getting_ready_counts_as_away_until_you_say_youre_ready(tmp_path: Path) -> None:
    from friday.planner.prepare import assumed_blocks, away_this_morning  # noqa: PLC0415

    app = new_app(tmp_path, now="2026-10-19T07:00")
    on(app)
    app.do("add", text="essay ~2h due tue")
    app.do("replan")  # 9 to 11
    app.now_utc += 4 * 60 + 30  # 11:30am
    app.do("sleep_mark", kind="up", at="2026-10-19T09:30")
    app.do("sleep_mark", kind="ready", at="2026-10-19T10:30")
    snapshot = take_snapshot(app.conn, app.now_utc)
    assert away_this_morning(snapshot)[1] == to_utc(parse_local("2026-10-19T10:30"), "America/New_York")
    (done,) = assumed_blocks(snapshot)  # 10:30 to 11, once you were ready
    assert (done.start_utc, done.end_utc) == (
        to_utc(parse_local("2026-10-19T10:30"), "America/New_York"),
        to_utc(parse_local("2026-10-19T11:00"), "America/New_York"),
    )


def test_work_before_you_went_to_bed_still_counts(tmp_path: Path) -> None:
    from friday.planner.prepare import awake_parts  # noqa: PLC0415

    away = (100, 200)  # bed at 100, ready at 200
    assert awake_parts(40, 90, away) == [(40, 90)]  # the evening before: done as planned
    assert awake_parts(80, 120, away) == [(80, 100)]  # up to going to bed
    assert awake_parts(150, 260, away) == [(200, 260)]  # from being ready
    assert awake_parts(120, 180, away) == []
    assert awake_parts(120, 180, None) == [(120, 180)]  # no taps this morning: as planned


# 23 Nov, the user: a night's "slept" was yellow when it was an hour under that night's own plan, which ran from 6h30
# to 8h15 as one-off nights moved, so short nights could stay gray and long ones turn yellow. Yellow is now an hour or
# more under one number for every night: your usual night, as your sleep setting has it (the amount you set up, as
# it's updated since), the length most of its seven nights have.
def test_your_usual_night_is_what_most_nights_of_your_sleep_setting_give(app: App) -> None:
    on(app)
    assert app.do("sleep")["usual_night_min"] == 8 * 60  # weeknights 11:30pm–7:30am, weekends 12:30–9am
    week = app.do("settings")["sleep"]
    shorter = {d: ({**n, "bedtime": "00:00", "wake": "07:00"} if d in ("mon", "tue", "wed", "thu", "fri") else n)
               for d, n in week.items()}  # fmt: skip
    app.do("settings_set", key="sleep", value=shorter)  # as "Use these times" updates it
    assert app.do("sleep")["usual_night_min"] == 7 * 60


def test_a_one_off_night_doesnt_change_your_usual_night(app: App) -> None:
    on(app)
    before = app.do("sleep")["usual_night_min"]
    app.do("day_override", date="2026-10-20", wake="05:30")  # up early once
    assert app.do("sleep")["usual_night_min"] == before
