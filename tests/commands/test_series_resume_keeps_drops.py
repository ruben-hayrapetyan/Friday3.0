"""A repeat stopped and started again keeps the times you dropped one at a time (audit, 12 Nov: Start
brought them back, as it couldn't tell them from the times Stop took). Glass box: Stop keeps the times it took
(`series.stopped_items`), Start brings back only those, and a repeat stopped before they were kept is started as it
was. Black box through the commands, with and without a calendar: what you dropped stays dropped, and the rest come
back. The whole system is tests/system/test_repeat_resume_system.py."""

import json
from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from tests.commands.helpers import App, new_app
from tests.commands.test_repeats_by_hand import ASIDE, todo, with_google


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-08T15:00")


def occurrences(app: App, series_id: int) -> list[dict]:
    found = [i for i in app.table("items") if i["series_id"] == series_id]
    return sorted(found, key=lambda i: (i["occurrence_date"], i["occurrence_n"]))


def series_row(app: App, series_id: int) -> dict:
    return next(s for s in app.table("series") if s["id"] == series_id)


def gym(app: App, **calendar: str) -> int:
    made = app.do("add", title="Gym", when="fixed", start="2026-11-10T07:30", end="2026-11-10T08:30",
                  every="rrule:FREQ=WEEKLY;BYDAY=TU", **ASIDE, **calendar)  # fmt: skip
    return made["series_id"]


# Glass box: what Stop keeps, and what Start reads.


def test_stop_keeps_the_times_it_took_off_a_calendar_and_only_those(app: App) -> None:
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    first, second, *rest = occurrences(app, series_id)
    app.do("drop", id=second["id"])  # yours, before Stop
    app.do("series_stop", id=series_id)
    kept = json.loads(series_row(app, series_id)["stopped_items"])
    assert kept == [first["id"], *(i["id"] for i in rest)]


def test_start_empties_what_stop_kept(app: App) -> None:
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    app.do("series_stop", id=series_id)
    app.do("series_resume", id=series_id)
    assert json.loads(series_row(app, series_id)["stopped_items"]) == []


def test_stopping_a_stopped_repeat_again_forgets_nothing_it_took(app: App) -> None:
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    app.do("series_stop", id=series_id)
    taken = json.loads(series_row(app, series_id)["stopped_items"])
    app.do("series_stop", id=series_id)
    assert json.loads(series_row(app, series_id)["stopped_items"]) == taken and taken


def test_a_repeat_stopped_before_this_was_kept_comes_back_as_it_did(app: App) -> None:
    """Stopped before Friday kept what Stop took (NULL): every time dropped from today on comes back, as before."""
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    before = len(todo(app, "Gym"))
    app.do("series_stop", id=series_id)
    app.conn.execute("UPDATE series SET stopped_items = NULL WHERE id = ?", [series_id])
    app.do("series_resume", id=series_id)
    assert len(todo(app, "Gym")) == before


def test_the_migration_marks_stopped_repeats_as_not_kept_and_running_ones_as_empty(tmp_path: Path) -> None:
    import sqlite3

    from friday.core.db import MIGRATIONS

    conn = sqlite3.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE series (id INTEGER PRIMARY KEY, active INTEGER NOT NULL) STRICT")
    conn.executemany("INSERT INTO series (id, active) VALUES (?, ?)", [(1, 1), (2, 0)])
    conn.executescript((MIGRATIONS / "032_stopped_times.sql").read_text())
    assert conn.execute("SELECT id, stopped_items FROM series ORDER BY id").fetchall() == [(1, "[]"), (2, None)]
    conn.execute("INSERT INTO series (id, active) VALUES (3, 1)")
    assert conn.execute("SELECT stopped_items FROM series WHERE id = 3").fetchone() == ("[]",)


# Black box: through the commands, as the app sends them.


def test_a_time_dropped_before_stop_stays_dropped_after_start(app: App) -> None:
    series_id = app.do("add", title="Run", duration_min=30, every="day")["series_id"]
    second = occurrences(app, series_id)[1]
    app.do("drop", id=second["id"])
    app.do("series_stop", id=series_id)
    app.do("series_resume", id=series_id)
    that_day = [i for i in occurrences(app, series_id) if i["occurrence_date"] == second["occurrence_date"]]
    assert [(i["id"], i["status"]) for i in that_day] == [(second["id"], "dropped")]  # not made again
    assert all(i["status"] == "todo" for i in occurrences(app, series_id) if i["id"] != second["id"])


def test_a_skipped_time_stays_skipped_after_start(app: App) -> None:
    series_id = app.do("add", title="Run", duration_min=30, every="day")["series_id"]
    third = occurrences(app, series_id)[2]
    app.do("skip", id=third["id"])
    app.do("series_stop", id=series_id)
    app.do("series_resume", id=series_id)
    that_day = [i for i in occurrences(app, series_id) if i["occurrence_date"] == third["occurrence_date"]]
    assert [i["status"] for i in that_day] == ["skipped"]


@pytest.mark.parametrize("sent", [True, False], ids=["deletes-sent", "deletes-waiting"])
def test_on_a_calendar_a_time_you_dropped_stays_off_it_after_start(app: App, sent: bool) -> None:
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    before = len(todo(app, "Gym"))
    second = todo(app, "Gym")[1]
    app.do("drop", id=second["id"])
    if sent:
        write_events(app.conn, app.now_utc, google=google)
    app.do("series_stop", id=series_id)
    if sent:
        write_events(app.conn, app.now_utc, google=google)
    app.do("series_resume", id=series_id)
    assert len(todo(app, "Gym")) == before - 1
    assert second["occurrence_date"] not in {i["occurrence_date"] for i in todo(app, "Gym")}
    write_events(app.conn, app.now_utc, google=google)
    assert sum(e.get("summary") == "Gym" for e in google.calendars_by_id["Classes@group"]) == before - 1


def test_undoing_start_stops_it_again_with_what_stop_took_kept(app: App) -> None:
    google = with_google(app, ["Classes"])
    series_id = gym(app)
    write_events(app.conn, app.now_utc, google=google)
    app.do("series_stop", id=series_id)
    taken = series_row(app, series_id)["stopped_items"]
    started = app.full("series_resume", payload={"id": series_id})
    app.do("undo", command_id=started.command_id)
    assert (series_row(app, series_id)["active"], series_row(app, series_id)["stopped_items"]) == (0, taken)
