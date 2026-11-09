"""Times in the hour the clocks skip (9 Nov, C68's open list: "a 2:30am event on the spring-forward night is
refused"). 2:30am on 14 Mar 2027 doesn't exist in New York; an event typed there moves past the gap whole, keeping
its length, and one that only ends in the gap keeps its clock times."""

from datetime import datetime
from pathlib import Path

import pytest

from friday.core.time import parse_utc, span_to_utc, to_local, to_utc
from tests.commands.helpers import TZ, App, new_app

PLAIN = dict(when="fixed", blocks_time=True, color=None, notes="", location=None)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2027-03-10T12:00")


# Glass box: span_to_utc moves the end with the start only when the start fell in the gap.


def test_a_start_in_the_gap_keeps_its_length() -> None:
    start, end = span_to_utc(datetime(2027, 3, 14, 2, 30), datetime(2027, 3, 14, 3, 30), TZ)
    assert start == to_utc(datetime(2027, 3, 14, 3, 30), TZ) and end - start == 60


def test_a_start_before_the_gap_keeps_its_clock_times() -> None:
    start, end = span_to_utc(datetime(2027, 3, 14, 1, 30), datetime(2027, 3, 14, 3, 30), TZ)
    assert (start, end) == (to_utc(datetime(2027, 3, 14, 1, 30), TZ), to_utc(datetime(2027, 3, 14, 3, 30), TZ))
    assert end - start == 60  # an hour of real time: 2am to 3am never happens


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 11, 10, 14, 0), datetime(2026, 11, 10, 15, 30)),  # an ordinary day
        (datetime(2026, 11, 1, 1, 30), datetime(2026, 11, 1, 2, 30)),  # the night the clocks go back
        (datetime(2027, 3, 14, 3, 0), datetime(2027, 3, 14, 4, 0)),  # just after the gap
    ],
)
def test_elsewhere_it_is_two_plain_conversions(start: datetime, end: datetime) -> None:
    assert span_to_utc(start, end, TZ) == (to_utc(start, TZ), to_utc(end, TZ))


def test_an_end_before_the_start_is_left_for_the_check_to_refuse() -> None:
    start, end = span_to_utc(datetime(2027, 3, 14, 2, 30), datetime(2027, 3, 14, 2, 0), TZ)
    assert end <= start


# Black box: through the commands, as the app sends them.


def local(stored: str) -> str:
    return to_local(parse_utc(stored), TZ).strftime("%Y-%m-%dT%H:%M")


def test_an_event_typed_at_2_30am_that_night_is_3_30_to_4_30(app: App) -> None:
    item = app.do("add", title="Late show", start="2027-03-14T02:30", end="2027-03-14T03:30", **PLAIN)["item"]
    assert (item["start"], item["end"]) == ("2027-03-14T03:30", "2027-03-14T04:30")


def test_quick_add_at_2_30am_that_night(app: App) -> None:
    item = app.do("add", text="late show sun 2:30am 1h")["item"]
    assert (item["start"], item["end"]) == ("2027-03-14T03:30", "2027-03-14T04:30")


def test_an_event_moved_onto_2_30am_keeps_its_hour(app: App) -> None:
    movie = app.do("add", title="Movie", start="2027-03-13T20:00", end="2027-03-13T21:00", **PLAIN)["item"]["id"]
    item = app.do("edit", id=movie, start="2027-03-14T02:30", end="2027-03-14T03:30")["item"]
    assert (item["start"], item["end"]) == ("2027-03-14T03:30", "2027-03-14T04:30")


def test_a_daily_2_30am_repeat_is_there_every_night(app: App) -> None:
    out = app.do(
        "add", title="Late", start="2027-03-12T02:30", end="2027-03-12T03:30", every="rrule:FREQ=DAILY;COUNT=5", **PLAIN
    )
    times = app.conn.execute(
        "SELECT start_utc, end_utc FROM items WHERE series_id = ? ORDER BY start_utc", [out["series_id"]]
    )
    assert [(local(s), local(e)) for s, e in times] == [
        ("2027-03-12T02:30", "2027-03-12T03:30"),
        ("2027-03-13T02:30", "2027-03-13T03:30"),
        ("2027-03-14T03:30", "2027-03-14T04:30"),
        ("2027-03-15T02:30", "2027-03-15T03:30"),
        ("2027-03-16T02:30", "2027-03-16T03:30"),
    ]


def test_logged_work_in_the_gap_counts_its_length(app: App) -> None:
    app.at("2027-03-14T09:00")
    essay = app.do("add", text="essay 3h due fri")["item"]["id"]
    out = app.do("log", id=essay, start="2027-03-14T02:30", end="2027-03-14T03:00")
    assert out["item"]["done_min"] == 30


def test_a_pin_in_the_gap_keeps_its_length(app: App) -> None:
    essay = app.do("add", text="essay 3h due fri")["item"]["id"]
    app.do("pin", id=essay, start="2027-03-14T02:30", end="2027-03-14T03:30")
    start, end = app.conn.execute("SELECT start_utc, end_utc FROM pins WHERE item_id = ?", [essay]).fetchone()
    assert (local(start), parse_utc(end) - parse_utc(start)) == ("2027-03-14T03:30", 60)


# The whole system: the server's command endpoint, as the web app calls it.


def test_the_server_takes_a_2_30am_event_that_night(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path, now="2027-03-10T12:00")
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        body = {"title": "Late show", "start": "2027-03-14T02:30", "end": "2027-03-14T03:30"} | PLAIN
        answer = web.post("/api/c/add", json=body)
        assert answer.status_code == 200, answer.text
        item = answer.json()["result"]["item"]
        assert (item["start"], item["end"]) == ("2027-03-14T03:30", "2027-03-14T04:30")
        listed = web.get("/api/q/item", params={"id": item["id"]}).json()["item"]
        assert listed["start"] == "2027-03-14T03:30"
