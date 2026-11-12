"""Repeating items as the Repeating settings list them."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_series_list_shows_each_repeat_and_a_stopped_one_can_start_again(app: App) -> None:
    made = app.do("series_add", title="gym", every="mon,wed", duration_min=60)
    (row,) = app.do("series_list")
    assert (row["title"], row["pattern"], row["source"], row["active"]) == ("gym", "Every Mon and Wed", "you", True)
    app.do("series_stop", id=made["id"])
    assert app.do("series_list")[0]["active"] is False
    app.do("series_resume", id=made["id"])
    assert app.do("series_list")[0]["next"] is not None


def test_deleting_a_repeat_removes_whats_undone_keeps_whats_done_and_can_be_undone(app: App) -> None:
    made = app.do("series_add", title="lunch", every="every day", duration_min=30)
    first, *rest = sorted((i for i in app.table("items") if i["title"] == "lunch"), key=lambda i: i["occurrence_date"])
    app.do("done", id=first["id"])
    deleted = app.full("series_delete", payload={"id": made["id"]})
    assert app.do("series_list") == []
    left = [i for i in app.table("items") if i["title"] == "lunch"]
    assert [(i["status"], i["series_id"]) for i in left] == [("done", None)]
    app.do("undo", command_id=deleted.command_id)
    assert len(app.do("series_list")) == 1
    assert len([i for i in app.table("items") if i["title"] == "lunch"]) == 1 + len(rest)


def test_a_meal_whose_window_has_passed_is_skipped_at_night_not_owed(app: App) -> None:
    app.do("add", text="lunch every day 11:30am-2pm 30-45m")
    app.now_utc += 2 * 1440  # two days on, nothing eaten
    app.do("close_day")
    lunches = sorted((i for i in app.table("items") if i["title"] == "lunch"), key=lambda i: i["occurrence_date"])
    assert [i["status"] for i in lunches[:2]] == ["skipped", "skipped"] and lunches[2]["status"] == "todo"


def test_a_daily_break_keeps_its_window_and_one_length_is_exact(app: App) -> None:
    app.do("add", text="Lunch every day 11:30am-2:30pm 15m")
    lunches = sorted((i for i in app.table("items") if i["title"] == "Lunch"), key=lambda i: i["occurrence_date"])
    assert [(i["release_utc"], i["due_utc"]) for i in lunches[:2]] == [
        ("2026-10-19T15:30Z", "2026-10-19T18:30Z"),
        ("2026-10-20T15:30Z", "2026-10-20T18:30Z"),
    ]  # 11:30am–2:30pm New York, every day
    assert {(i["amount"], i["min_units"], i["ideal_units"], i["max_units"]) for i in lunches} == {("elastic", 1, 1, 1)}


def test_time_to_get_there_set_on_one_lunch_is_every_lunch_from_then(app: App) -> None:
    app.do("add", text="Lunch every day 11:30am-2:30pm 30m")
    app.do("add", text="essay ~2h due fri")  # an item made after them, so a remade lunch can't take an old id
    lunches = sorted((i for i in app.table("items") if i["title"] == "Lunch"), key=lambda i: i["occurrence_date"])
    today, later = lunches[0], lunches[1:]
    app.do("progress", id=today["id"], share=0.5)
    out = app.do(
        "edit",
        id=today["id"],
        buffer_before_min=15,
        buffer_after_min=15,
        min_min=15,
        ideal_min=15,
        max_min=15,
        from_date="2026-10-19",
    )
    assert out["item"]["id"] == today["id"] and out["item"]["done_min"] == 15  # the same lunch, its work kept
    now = {i["id"]: i for i in app.table("items") if i["title"] == "Lunch" and i["status"] == "todo"}
    assert set(now) == {i["id"] for i in lunches}  # changed where they are, none remade
    assert {(i["buffer_before_min"], i["buffer_after_min"]) for i in now.values()} == {(15, 15)}
    assert all(i["max_units"] == 1 for i in now.values()) and len(later) > 7
    shown = next(i for i in app.do("items") if i["title"] == "Lunch")
    assert (shown["buffer_before_min"], shown["buffer_after_min"]) == (15, 15)


def test_a_new_time_from_a_date_on_moves_that_time_and_every_later_one(app: App) -> None:
    # 31 Oct: Salsa "1:25 to 2:30 from the 7th on" moved nothing; the times were dropped and the rest kept.
    app.do("add", title="Salsa", when="fixed", start="2026-10-24T13:35", end="2026-10-24T14:40", every="sat")
    first, second, *later = sorted(
        (i for i in app.table("items") if i["title"] == "Salsa"), key=lambda i: i["occurrence_date"]
    )
    app.do("edit", id=second["id"], start="2026-10-31T13:25", end="2026-10-31T14:30", from_date="2026-10-31")

    def when(item: dict) -> tuple[str, str]:
        shown = app.do("item", id=item["id"])["item"]
        return shown["start"], shown["end"]

    assert when(first) == ("2026-10-24T13:35", "2026-10-24T14:40")  # before the date: as it was
    assert when(second) == ("2026-10-31T13:25", "2026-10-31T14:30")
    assert len(later) > 3 and {(when(i)[0][11:], when(i)[1][11:]) for i in later} == {("13:25", "14:30")}  # past 1 Nov
    app.now_utc += 60 * 1440
    app.do("materialize")
    newest = max((i for i in app.table("items") if i["title"] == "Salsa"), key=lambda i: i["occurrence_date"])
    assert when(newest)[0][11:] == "13:25" and newest["id"] not in {i["id"] for i in later}  # those made later too


def test_a_repeat_more_than_once_a_day_keeps_each_time(app: App) -> None:
    # The audit (30 Oct): "every day at 9 and 5" failed to save; both times of a day took the same place in it.
    made = app.do("add", title="Meds", when="fixed", start="2026-10-20T09:00", end="2026-10-20T09:15",
                  every="rrule:FREQ=DAILY;BYHOUR=9,17")  # fmt: skip
    meds = [i for i in app.table("items") if i["title"] == "Meds"]
    shown = {app.do("item", id=i["id"])["item"]["start"] for i in meds}
    assert {"2026-10-20T09:00", "2026-10-20T17:00", "2026-10-21T09:00", "2026-10-21T17:00"} <= shown
    assert len(meds) == len(shown) == made["occurrences"]
    app.do("materialize")  # made again: nothing new
    assert len([i for i in app.table("items") if i["title"] == "Meds"]) == len(meds)
    with pytest.raises(Exception, match="part of how it repeats"):
        app.do("edit", id=meds[0]["id"], start="2026-10-20T08:00", end="2026-10-20T08:15", from_date="2026-10-20")


def test_a_new_due_from_a_date_on_is_every_later_ones(app: App) -> None:
    task = app.do("add", title="Reading quiz", duration_min=30, due="2026-10-23T17:00")["item"]
    app.do("repeat", id=task["id"], every="fri")
    first, second, *later = sorted(
        (i for i in app.table("items") if i["title"] == "Reading quiz"), key=lambda i: i["occurrence_date"]
    )
    app.do("edit", id=second["id"], due="2026-10-30T15:00", from_date=second["occurrence_date"])
    due = {i["id"]: app.do("item", id=i["id"])["item"]["due"] for i in [first, second, *later]}
    assert due[first["id"]] == "2026-10-23T17:00" and due[second["id"]] == "2026-10-30T15:00"
    assert len(later) > 2 and {due[i["id"]][11:] for i in later} == {"15:00"}


def test_a_task_made_to_repeat_repeats_from_its_own_due_day(app: App) -> None:
    # The audit (31 Oct): a Friday-due task made "every fri" came due on Tuesdays (counted from today, a Monday), and
    # wasn't the first of its own repeat.
    task = app.do("add", title="Reading quiz", duration_min=30, due="2026-10-23T17:00")["item"]
    app.do("repeat", id=task["id"], every="fri")
    mine = [i for i in app.table("items") if i["title"] == "Reading quiz" and i["status"] == "todo"]
    assert {i["due_utc"][:10] for i in mine} >= {"2026-10-23", "2026-10-30"}
    york = ZoneInfo("America/New_York")
    local = [datetime.fromisoformat(i["due_utc"].replace("Z", "+00:00")).astimezone(york) for i in mine]
    assert all(d.weekday() == 4 and d.hour == 17 for d in local)  # 5 PM each Friday, either side of the clocks changing
    assert next(i for i in mine if i["id"] == task["id"])["series_id"] is not None
    assert len([i for i in mine if i["due_utc"].startswith("2026-10-23")]) == 1


def test_an_event_kept_only_in_friday_repeats_only_in_friday(app: App) -> None:
    # The audit (31 Oct): its repeats were all sent to the calendar new events go to.
    app.do("settings_set", key="gcal", value={"new_events_to": "Classes@group"})
    made = app.do("add", title="Chess", when="fixed", start="2026-10-21T19:00", end="2026-10-21T20:00", calendar="")
    app.do("repeat", id=made["item"]["id"], every="week")
    assert app.table("event_writes") == []


def test_a_repeat_must_say_how(app: App) -> None:
    task = app.do("add", title="Reading quiz", duration_min=30, due="2026-10-23T17:00")["item"]
    with pytest.raises(Exception, match="say how it repeats"):
        app.do("repeat", id=task["id"], every="every")


def test_a_repeat_said_in_words_friday_cant_read_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="isn't a repeat like"):
        app.do("series_add", title="gym", every="whenever I like", duration_min=60)


def test_a_saturday_made_to_repeat_on_weekdays_stays_beside_its_repeat(app: App) -> None:
    sat = app.do("add", title="Club", when="fixed", start="2026-10-24T10:00", end="2026-10-24T11:00")["item"]
    app.do("repeat", id=sat["id"], every="weekdays")
    row = next(i for i in app.table("items") if i["id"] == sat["id"])
    assert (row["series_id"] is not None, row["occurrence_date"], row["occurrence_n"], row["detached"]) == (
        True,
        "2026-10-24",
        0,
        1,
    )
    others = [i for i in app.table("items") if i["title"] == "Club" and i["id"] != sat["id"]]
    assert others and all(i["series_id"] == row["series_id"] for i in others)


def test_a_series_that_isnt_there_is_said_by_its_number(app: App) -> None:
    with pytest.raises(FieldError, match="no series 99"):
        app.do("series_stop", id=99)


def test_deleting_a_repeat_takes_its_pins_and_waits_with_it_and_leaves_the_one_being_timed(app: App) -> None:
    made = app.do("series_add", title="practice", every="every day", duration_min=30)
    first, second, *_ = sorted(
        (i for i in app.table("items") if i["title"] == "practice"), key=lambda i: i["occurrence_date"]
    )
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("start", id=first["id"])
    app.do("pin", id=second["id"], start="2026-10-20T15:00", kind="preferred")
    app.do("depend", item_id=essay, depends_on_id=second["id"])
    app.do("series_delete", id=made["id"])
    assert app.table("pins") == [] and app.table("dependencies") == []
    assert sorted(i["title"] for i in app.table("items")) == ["Essay", "practice"]  # the one on the timer stays
    assert [t["item_id"] for t in app.table("timer")] == [first["id"]]


def test_a_new_time_from_a_date_on_ends_after_it_starts(app: App) -> None:
    app.do("add", title="Salsa", when="fixed", start="2026-10-24T13:35", end="2026-10-24T14:40", every="sat")
    first = min((i for i in app.table("items") if i["title"] == "Salsa"), key=lambda i: i["occurrence_date"])
    with pytest.raises(FieldError, match="the end comes before the start"):
        app.do("edit", id=first["id"], start="2026-10-24T14:00", end="2026-10-24T13:00", from_date="2026-10-24")
    with pytest.raises(FieldError, match="the end comes before the start"):
        app.do("edit", id=first["id"], start="2026-10-25T14:00", end="2026-10-25T13:00", from_date="2026-10-24")


def test_a_time_that_is_part_of_how_it_repeats_cant_move_to_another_day(app: App) -> None:
    app.do("add", title="Meds", when="fixed", start="2026-10-20T09:00", end="2026-10-20T09:15",
           every="rrule:FREQ=DAILY;BYHOUR=9,17")  # fmt: skip
    first = min((i for i in app.table("items") if i["title"] == "Meds"), key=lambda i: i["start_utc"])
    with pytest.raises(FieldError, match="part of how it repeats"):
        app.do("edit", id=first["id"], start="2026-10-21T08:00", end="2026-10-21T08:15", from_date="2026-10-20")


def test_deleting_a_calendars_own_repeat_switches_it_off(app: App) -> None:
    made = app.do("series_add", title="Lecture", every="mon,wed", duration_min=60)
    app.conn.execute("UPDATE series SET external_id = 'gcal:abc' WHERE id = ?", [made["id"]])
    out = app.do("series_delete", id=made["id"])
    assert out["message"] == "Lecture switched off; your calendar won't bring it back"
    assert app.table("series")[0]["active"] == 0


def test_only_a_repeat_has_a_time_to_skip(app: App) -> None:
    item = app.do("add", title="Laundry", duration_min=30)["item"]
    with pytest.raises(FieldError, match=f"T{item['id']} doesn't repeat; drop it instead"):
        app.do("skip", id=item["id"])
