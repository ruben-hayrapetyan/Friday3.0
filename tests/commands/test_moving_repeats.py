"""Moving a repeating event to another day, from what you see (5 Nov: "change jaspers bday to nov 6 yearly" failed:
the AI's edit was refused and nothing else could move a repeat's day)."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app
from tests.commands.test_ask_claude import asking


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-05T08:48")  # a Thursday


def days_of(app: App, title: str) -> list[str]:
    shown = [app.do("item", id=i["id"])["item"] for i in app.table("items") if i["title"] == title]
    return sorted(s["start"] for s in shown if s["status"] == "todo")


def test_a_yearly_birthday_asked_to_move_to_the_next_day_moves_this_year_and_every_year(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.do("add", title="Jasper's Birthday", when="fixed", start="2026-11-05T00:00", end="2026-11-06T00:00",
           every="year")  # fmt: skip
    (series,) = app.table("series")
    (today,) = [i for i in app.table("items") if i["title"] == "Jasper's Birthday"]
    asking(monkeypatch, {"reply": "Moved to Nov 6, yearly.", "actions": [
        {"sentence": "Move Jasper's Birthday to Nov 6, every year", "command": "edit",
         "input": {"id": today["id"], "start": "2026-11-06T00:00", "end": "2026-11-07T00:00",
                   "from_date": "2026-11-05"}}]})  # fmt: skip
    action = app.do("ask_claude", text="change jaspers bday to nov 6 yearly")["actions"][0]
    assert action["error"] is None  # checked before you see it, and taken
    app.do(action["command"], **action["input"])
    assert days_of(app, "Jasper's Birthday") == ["2026-11-06T00:00"]
    (row,) = app.do("series_list")
    assert row["pattern"] == "Yearly" and row["id"] == series["id"]  # the same repeat, moved
    app.at("2027-11-01T09:00").do("materialize")
    assert days_of(app, "Jasper's Birthday")[-1] == "2027-11-06T00:00"


def test_a_weekly_class_moved_from_a_later_week_keeps_the_weeks_before(app: App) -> None:
    app.do("add", title="Seminar", when="fixed", start="2026-11-09T14:00", end="2026-11-09T15:00", every="mon")
    later = next(i for i in app.table("items") if i["occurrence_date"] == "2026-11-16")
    app.do("edit", id=later["id"], start="2026-11-17T15:00", end="2026-11-17T16:00", from_date="2026-11-16")
    seen = days_of(app, "Seminar")
    assert seen[0] == "2026-11-09T14:00"  # the week before, as it was
    assert seen[1:3] == ["2026-11-17T15:00", "2026-11-24T15:00"] and all(s[11:] == "15:00" for s in seen[1:])
    assert [r["pattern"] for r in app.do("series_list")] == ["Every Monday until Nov 15", "Every Tuesday"]


def test_one_day_of_a_class_on_two_days_moves_and_the_other_stays(app: App) -> None:
    app.do("add", title="Lab", when="fixed", start="2026-11-09T10:00", end="2026-11-09T11:00", every="mon,wed")
    monday = next(i for i in app.table("items") if i["occurrence_date"] == "2026-11-09")
    app.do("edit", id=monday["id"], start="2026-11-10T10:00", end="2026-11-10T11:00", from_date="2026-11-09")
    assert days_of(app, "Lab")[:4] == ["2026-11-10T10:00", "2026-11-11T10:00", "2026-11-17T10:00", "2026-11-18T10:00"]
    assert app.do("series_list")[0]["pattern"] == "Every Tue and Wed"


def test_a_monthly_payment_on_the_15th_moves_to_the_16th(app: App) -> None:
    app.do("add", title="Rent", when="fixed", start="2026-11-15T09:00", end="2026-11-15T09:30",
           every="rrule:FREQ=MONTHLY;BYMONTHDAY=15")  # fmt: skip
    first = next(i for i in app.table("items") if i["occurrence_date"] == "2026-11-15")
    app.do("edit", id=first["id"], start="2026-11-16T09:00", end="2026-11-16T09:30", from_date="2026-11-15")
    assert days_of(app, "Rent")[:2] == ["2026-11-16T09:00", "2026-12-16T09:00"]
    assert app.do("series_list")[0]["pattern"] == "Monthly on the 16th"


def test_moving_a_repeat_is_undone_in_one_step(app: App) -> None:
    app.do("add", title="Jasper's Birthday", when="fixed", start="2026-11-05T00:00", end="2026-11-06T00:00",
           every="year")  # fmt: skip
    (today,) = [i for i in app.table("items") if i["title"] == "Jasper's Birthday"]
    moved = app.full("edit", payload={"id": today["id"], "start": "2026-11-06T00:00", "end": "2026-11-07T00:00",
                                      "from_date": "2026-11-05"})  # fmt: skip
    app.do("undo", command_id=moved.command_id)
    assert days_of(app, "Jasper's Birthday") == ["2026-11-05T00:00"]
    assert app.table("series")[0]["dtstart_local"] == "2026-11-05T00:00"


def test_a_repeat_on_set_dates_or_onto_a_day_it_has_says_how_to_change_it(app: App) -> None:
    app.do("add", title="Club", when="fixed", start="2026-11-09T18:00", end="2026-11-09T19:00",
           every="rrule:FREQ=MONTHLY;BYDAY=2MO")  # fmt: skip
    club = next(i for i in app.table("items") if i["occurrence_date"] == "2026-11-09")
    with pytest.raises(Exception, match="repeats on set dates"):
        app.do("edit", id=club["id"], start="2026-11-10T18:00", end="2026-11-10T19:00", from_date="2026-11-09")
    app.do("add", title="Lab", when="fixed", start="2026-11-09T10:00", end="2026-11-09T11:00", every="mon,wed")
    monday = next(i for i in app.table("items") if i["title"] == "Lab")
    with pytest.raises(Exception, match="repeats on set dates"):
        app.do("edit", id=monday["id"], start="2026-11-11T12:00", end="2026-11-11T13:00", from_date="2026-11-09")


def test_one_time_moved_without_a_date_on_is_still_that_time_only(app: App) -> None:
    app.do("add", title="Seminar", when="fixed", start="2026-11-09T14:00", end="2026-11-09T15:00", every="mon")
    first = next(i for i in app.table("items") if i["occurrence_date"] == "2026-11-09")
    app.do("edit", id=first["id"], start="2026-11-10T14:00", end="2026-11-10T15:00")
    assert days_of(app, "Seminar")[:2] == ["2026-11-10T14:00", "2026-11-16T14:00"]
    assert app.do("series_list")[0]["pattern"] == "Every Monday"
