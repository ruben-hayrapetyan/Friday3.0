"""Work is logged once it's done (9 Nov, C68's open list: "`log` takes future times"). Work logged ahead counted as
done before it was, and taught Friday lengths that hadn't happened."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def essay(app: App) -> int:
    return app.do("add", text="essay 3h due fri")["item"]["id"]


# Black box: what you can and can't log.


def test_work_ending_later_today_is_refused(app: App) -> None:
    item = essay(app)
    with pytest.raises(FieldError, match="later than now"):
        app.do("log", id=item, start="2026-10-19T08:30", end="2026-10-19T09:30")
    assert app.table("progress") == []


def test_something_that_happened_tomorrow_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="later than now"):
        app.do("log", title="dentist", start="2026-10-20T09:00", end="2026-10-20T10:00")
    assert [r for r in app.table("items") if r["title"] == "dentist"] == []


def test_work_ending_now_counts(app: App) -> None:
    item = essay(app)
    assert app.do("log", id=item, start="2026-10-19T08:00", end="2026-10-19T09:00")["item"]["done_min"] == 60


def test_work_yesterday_counts(app: App) -> None:
    item = essay(app)
    assert app.do("log", id=item, start="2026-10-18T14:00", end="2026-10-18T15:30")["item"]["done_min"] == 90


# Glass box: the check is the logged end against the command's clock, made after the start/end check.


def test_an_end_before_its_start_is_still_that_error(app: App) -> None:
    with pytest.raises(FieldError, match="after the start"):
        app.do("log", id=essay(app), start="2026-10-20T10:00", end="2026-10-20T09:00")


def test_the_same_work_counts_once_the_clock_passes_it(app: App) -> None:
    item = essay(app)
    with pytest.raises(FieldError):
        app.do("log", id=item, start="2026-10-19T10:00", end="2026-10-19T11:00")
    assert app.at("2026-10-19T11:00").do("log", id=item, start="2026-10-19T10:00", end="2026-10-19T11:00")


# The whole system: the server answers the web app's "I worked on this" in words.


def test_the_server_says_why_it_refused(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    item = essay(app)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        later = web.post("/api/c/log", json={"id": item, "start": "2026-10-19T10:00", "end": "2026-10-19T11:00"})
        assert later.status_code == 422 and "later than now" in later.text
        done = web.post("/api/c/log", json={"id": item, "start": "2026-10-19T08:00", "end": "2026-10-19T09:00"})
        assert done.status_code == 200 and done.json()["result"]["item"]["done_min"] == 60
