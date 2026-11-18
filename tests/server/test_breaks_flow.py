"""Breaks through the HTTP API, as the web uses them (whole system, without the worker). Found in the demo, 18 Nov: a
break added from the web answered 500, "Object of type date is not JSON serializable": the registry's log line dumped
the command's input without making its dates text. Commands whose inputs hold dates had only been run with plain
strings, by the command tests. Monday 2026-10-19 9am; the break is Wednesday 21 to Friday 23."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.server.app import create_app
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=7)


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def test_a_break_is_added_changed_and_deleted_from_the_web(client: TestClient) -> None:
    made = client.post("/api/c/vacation_add", json={"name": "Fall break", "start": "2026-10-21", "end": "2026-10-23"})
    assert made.status_code == 200, made.text
    v = made.json()["result"]["vacation"]
    moved = client.post("/api/c/vacation_edit", json={"id": v["id"], "end": "2026-10-24", "mode": "off"})
    assert moved.status_code == 200, moved.text
    assert client.get("/api/q/vacations").json()["vacations"][0]["end"] == "2026-10-24"
    assert client.post("/api/c/vacation_delete", json={"id": v["id"]}).status_code == 200


def test_a_break_day_is_listed_drawn_and_ticked(client: TestClient) -> None:
    client.post("/api/c/vacation_add", json={"name": "Fall break", "start": "2026-10-21", "end": "2026-10-23"})
    essay = client.post("/api/c/add", json={"title": "essay", "duration_min": 60, "release": "2026-10-21T04:00",
                                            "due": "2026-10-21T23:00"}).json()["result"]["item"]["id"]  # fmt: skip
    client.post("/api/c/replan")
    day = client.get("/api/q/vacation_day", params={"date": "2026-10-21"}).json()
    assert [t["item_id"] for t in day["items"]] == [essay]
    days = client.get("/api/q/calendar", params={"start": "2026-10-21", "days": 1}).json()["days"]
    assert days[0]["vacation"]["things"] == 1
    ticked = client.post("/api/c/vacation_tick", json={"date": "2026-10-21", "item_id": essay, "ticked": True})
    assert ticked.status_code == 200, ticked.text
    assert client.get("/api/q/vacation_day", params={"date": "2026-10-21"}).json()["items"][0]["ticked"] is True
    assert client.get("/api/q/break_choices").status_code == 200
