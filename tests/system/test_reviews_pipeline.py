"""The week's review (tests/features.toml: reviews), the whole pipeline: a real `fridayd serve`, what you do in the week
sent over HTTP as the app sends it (work logged, a deadline met, a block moved, an event, how the week felt), and the
week read back as Insights reads it, `week_review`: its days, hours by tag, deadlines, moves, what's finished and
coming, and the note `week_note` kept with that week and no other."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

DAY_START = timedelta(hours=4)  # Friday's day runs 4am to 4am


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def now() -> datetime:
    return datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)


def planning_day(moment: datetime) -> date:
    return (moment - DAY_START).date()


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("reviews"))
    yield server
    server.stop()


def week_end(week: dict) -> datetime:
    """When the week ends: the day after its last, at the day's start."""
    last = date.fromisoformat(week["end"]) + timedelta(days=1)
    return datetime.combine(last, datetime.min.time(), ZoneInfo(TZ)) + DAY_START


def test_the_week_runs_from_its_first_day_to_its_last_whatever_day_is_asked(friday: Friday) -> None:
    wednesday = date(2026, 11, 18)
    for asked in (wednesday - timedelta(days=2), wednesday, wednesday + timedelta(days=4)):
        week = friday.q("week_review", date=asked.isoformat())
        assert (week["start"], week["end"]) == ("2026-11-16", "2026-11-22")  # Monday to Sunday
    week = friday.q("week_review")  # this week when left out
    today = planning_day(now())
    assert date.fromisoformat(week["start"]) <= today <= date.fromisoformat(week["end"])
    assert date.fromisoformat(week["start"]).weekday() == 0


def test_a_week_starting_sunday_moves_the_weeks_bounds(friday: Friday) -> None:
    time = friday.q("settings")["time"]
    friday.c("settings_set", key="time", value=time | {"week_start": "sun"})
    try:
        week = friday.q("week_review", date="2026-11-18")
        assert (week["start"], week["end"]) == ("2026-11-15", "2026-11-21")
    finally:
        friday.c("settings_set", key="time", value=time)
    assert friday.q("week_review", date="2026-11-18")["start"] == "2026-11-16"


def test_how_the_week_felt_is_kept_with_that_week_and_shown_in_its_review(friday: Friday) -> None:
    assert friday.q("week_review", date="2026-11-04")["note"] == {}
    assert friday.c("week_note", week="2026-11-02", feel="good", notes="Midterms went fine")["message"] == "Saved"
    assert friday.q("week_review", date="2026-11-04")["note"] == {"feel": "good", "notes": "Midterms went fine"}
    # only what's said changes: the notes stay when the feel is changed
    friday.c("week_note", week="2026-11-02", feel="tired")
    assert friday.q("week_review", date="2026-11-08")["note"] == {"feel": "tired", "notes": "Midterms went fine"}
    friday.c("week_note", week="2026-11-02", notes="")
    assert friday.q("week_review", date="2026-11-02")["note"] == {"feel": "tired", "notes": ""}
    # the week after has its own (none)
    assert friday.q("week_review", date="2026-11-09")["note"] == {}


def test_a_note_without_its_week_or_a_day_that_isnt_one_is_refused(friday: Friday) -> None:
    answer = friday.http.post("/api/c/week_note", json={"feel": "good"})
    assert answer.status_code == 422 and [e["loc"][-1] for e in answer.json()["detail"]] == ["week"]
    answer = friday.http.get("/api/q/week_review", params={"date": "2026-02-30"})
    assert answer.status_code == 422


def test_work_logged_this_week_counts_as_its_tags_hours(friday: Friday) -> None:
    friday.c("area_add", name="Chemistry")
    task = friday.c("add", title="Titration lab report", duration_min=180, area="Chemistry",
                    due=local(now() + timedelta(days=9)))["item"]  # fmt: skip
    end = now() - timedelta(minutes=5)
    start = end - timedelta(minutes=90)
    week = friday.q("week_review", date=planning_day(start).isoformat())
    before = {a["area"]: a["actual_h"] for a in week["areas"]}.get("Chemistry", 0)
    friday.c("log", id=task["id"], start=local(start), end=local(end))
    week = friday.q("week_review", date=planning_day(start).isoformat())
    assert {a["area"]: a["actual_h"] for a in week["areas"]}["Chemistry"] == before + 1.5
    (group,) = [g for g in week["groups"] if g["name"] == "Chemistry"]
    assert group["by"] == "tag" and group["actual_h"] == before + 1.5
    assert [i["title"] for i in group["items"]] == ["Titration lab report"]
    # the week before doesn't have it
    earlier = friday.q("week_review", date=(planning_day(start) - timedelta(days=7)).isoformat())
    assert "Chemistry" not in {a["area"] for a in earlier["areas"]}


def test_a_hard_deadline_met_this_week_is_on_time_and_finished(friday: Friday) -> None:
    week = friday.q("week_review")
    due = now() + (week_end(week) - now()) / 2  # within this week, after now
    task = friday.c("add", title="Submit visa form", duration_min=30, firmness="hard", due=local(due))["item"]
    (deadline,) = [d for d in friday.q("week_review")["deadlines"] if d["item_id"] == task["id"]]
    assert deadline["outcome"] == "open" and deadline["due"] == local(due)
    friday.c("done", id=task["id"])
    week = friday.q("week_review")
    (deadline,) = [d for d in week["deadlines"] if d["item_id"] == task["id"]]
    assert deadline["outcome"] == "on_time"
    assert task["id"] in {i["item_id"] for i in week["finished"]}


def test_what_is_due_next_week_is_coming_and_an_event_this_week_counts_as_fixed_time(friday: Friday) -> None:
    week = friday.q("week_review")
    next_week = week_end(week) + timedelta(days=2, hours=10)
    task = friday.c("add", title="Grant proposal", duration_min=60, due=local(next_week))["item"]
    later = friday.c("add", title="Thesis draft", duration_min=60, due=local(next_week + timedelta(days=14)))["item"]
    coming = {i["item_id"]: i for i in friday.q("week_review")["coming"]}
    assert task["id"] in coming and coming[task["id"]]["note"] == "due" and later["id"] not in coming

    # an event inside this week, in the past so whatever the hour: two hours of it
    start = max(now() - timedelta(hours=3), week_end(week) - timedelta(days=7))
    fixed = friday.q("week_review", date=planning_day(start).isoformat())["fixed_h"]
    friday.c("add", title="Department seminar", when="fixed", start=local(start), end=local(start + timedelta(hours=2)))
    after = friday.q("week_review", date=planning_day(start).isoformat())["fixed_h"]
    assert sum(after.values()) == pytest.approx(sum(fixed.values()) + 2)


def test_a_block_you_move_is_counted_among_the_weeks_moves(friday: Friday) -> None:
    moves = friday.q("week_review")["moves"]
    task = friday.c("add", title="Read chapter 9", duration_min=60, due=local(now() + timedelta(days=5)))["item"]
    at = now() + timedelta(days=1)
    at = at.replace(hour=15, minute=0)
    friday.c("pin", id=task["id"], start=local(at), kind="preferred")
    assert friday.q("week_review")["moves"] == moves + 1
    friday.c("unpin", id=task["id"])
    assert friday.q("week_review")["moves"] == moves + 2
