"""Moving a repeat's day, from inside (commands/series_days.py): which series row changes, its first date, and
what happens to each time already made."""

from pathlib import Path

import pytest

from friday.commands.series_days import anchor
from friday.core.time import parse_local
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def times(app: App, title: str) -> list[dict]:
    found = [i for i in app.table("items") if i["title"] == title]
    return sorted(found, key=lambda i: (i["occurrence_date"], i["id"]))


def test_the_first_time_moved_changes_the_one_series_and_keeps_every_id(app: App) -> None:
    app.do("add", title="Club", when="fixed", start="2026-10-19T18:00", end="2026-10-19T19:00", every="week")
    before = times(app, "Club")
    app.do("edit", id=before[0]["id"], start="2026-10-20T18:00", end="2026-10-20T19:00", from_date="2026-10-19")
    (series,) = app.table("series")
    assert (series["rrule"], series["dtstart_local"]) == ("FREQ=WEEKLY", "2026-10-20T18:00")
    after = [i for i in times(app, "Club") if i["status"] == "todo"]
    assert {i["id"] for i in before} <= {i["id"] for i in after}
    assert [i["occurrence_date"] for i in after][:3] == ["2026-10-20", "2026-10-27", "2026-11-03"]


def test_a_later_time_moved_ends_the_series_and_starts_a_new_one_its_times_moved_into(app: App) -> None:
    app.do("add", title="Club", when="fixed", start="2026-10-19T18:00", end="2026-10-19T19:00", every="mon,wed")
    made = times(app, "Club")
    monday = next(i for i in made if i["occurrence_date"] == "2026-10-26")
    app.do("edit", id=monday["id"], start="2026-10-27T18:00", end="2026-10-27T19:00", from_date="2026-10-26")
    old, new = app.table("series")
    assert old["rrule"] == "FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261025T235959"
    assert (new["rrule"], new["dtstart_local"]) == ("FREQ=WEEKLY;BYDAY=TU,WE", "2026-10-26T18:00")
    moved = app.do("item", id=monday["id"])["item"]
    assert moved["start"] == "2026-10-27T18:00"
    by_day = {i["occurrence_date"]: i for i in times(app, "Club") if i["status"] == "todo"}
    assert by_day["2026-10-27"]["id"] == monday["id"] and by_day["2026-10-27"]["series_id"] == new["id"]
    assert by_day["2026-10-21"]["series_id"] == old["id"]  # before the date: the old repeat's
    wednesday = next(i for i in made if i["occurrence_date"] == "2026-10-28")
    assert by_day["2026-10-28"]["id"] == wednesday["id"]  # a Wednesday stays where it is, in the new repeat


def test_a_rule_naming_weekdays_keeps_its_first_date_and_one_naming_none_moves_it() -> None:
    first, at = parse_local("2026-10-19T18:00"), parse_local("2026-10-26T18:00")
    later = parse_local("2026-10-27T18:00")
    assert str(anchor("FREQ=WEEKLY;BYDAY=MO,WE", first.date(), first.date(), first, later)) == "2026-10-19"
    assert (
        str(anchor("FREQ=WEEKLY", first.date(), first.date(), first, parse_local("2026-10-20T18:00"))) == "2026-10-20"
    )
    assert str(anchor("FREQ=WEEKLY", first.date(), at.date(), at, later)) == "2026-10-27"
    earlier = parse_local("2026-10-18T18:00")
    assert str(anchor("FREQ=WEEKLY;BYDAY=MO", first.date(), first.date(), first, earlier)) == "2026-10-18"


def test_a_time_the_moved_repeat_no_longer_has_is_skipped_not_deleted(app: App) -> None:
    # Every day, moved a day later: each time moves a day, and a detached one already on a moved day stays its own.
    app.do("add", title="Walk", when="fixed", start="2026-10-19T07:00", end="2026-10-19T07:30", every="day")
    made = times(app, "Walk")
    app.do("edit", id=made[0]["id"], start="2026-10-20T07:00", end="2026-10-20T07:30", from_date="2026-10-19")
    todo = [i for i in times(app, "Walk") if i["status"] == "todo"]
    assert len({i["occurrence_date"] for i in todo}) == len(todo)  # one a day
    assert {i["id"] for i in made} >= {i["id"] for i in todo if i["id"] <= made[-1]["id"]}
    assert todo[0]["occurrence_date"] == "2026-10-20"


def test_only_a_new_start_keeps_the_length(app: App) -> None:
    app.do("add", title="Club", when="fixed", start="2026-10-19T18:00", end="2026-10-19T19:30", every="week")
    first = times(app, "Club")[0]
    app.do("edit", id=first["id"], start="2026-10-21T17:00", from_date="2026-10-19")
    shown = app.do("item", id=first["id"])["item"]
    assert (shown["start"], shown["end"]) == ("2026-10-21T17:00", "2026-10-21T18:30")
    assert '"length_min": 90' in app.table("series")[0]["template"]
