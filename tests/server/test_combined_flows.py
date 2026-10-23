"""The combined Friday end to end through the HTTP API the web app uses (COMBINED.md): whole flows as a person goes
through them, each request as the app sends it, the plan solved in the request (no worker)."""

import json
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


def do(client: TestClient, name: str, **body: object) -> dict:
    out = client.post(f"/api/c/{name}", json=body)
    assert out.status_code == 200, out.text
    return out.json()


def ask(client: TestClient, name: str, **params: object) -> object:
    out = client.get(f"/api/q/{name}", params=params)
    assert out.status_code == 200, out.text
    return out.json()


def blocks(client: TestClient, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in ask(client, "plan")["blocks"] if b["item_id"] == item_id]  # type: ignore[index]


def test_moving_in_from_todo_list_and_chroma(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "todos.json").write_text(json.dumps([
        {"id": "1", "title": "MATH 2940 HW 7", "bucket": "assignments", "horizon": "shortTerm",
         "dueDate": "2026-10-21T03:59:00Z"},
        {"id": "2", "title": "Learn Rust", "horizon": "longTerm"},
    ]))  # fmt: skip
    (tmp_path / "categories.json").write_text(json.dumps({
        "categories": [{"name": "Classes", "slug": "class", "color": "blue", "pattern": r"\blec"},
                       {"name": "Advising", "slug": "advising", "color": "green", "pattern": "office hours"}],
        "filter": {"label": "TA hours", "pattern": "office hours", "except": []},
    }))  # fmt: skip
    out = do(client, "import_personal", todos_path=str(tmp_path / "todos.json"),
             categories_path=str(tmp_path / "categories.json"))  # fmt: skip
    assert out["result"]["message"] == "Imported 2 tasks from Todo List and 2 categories from Chroma"
    items = {i["title"]: i for i in ask(client, "items")}  # type: ignore[union-attr]
    assert items["MATH 2940 HW 7"]["due"] == "2026-10-20T23:59" and items["MATH 2940 HW 7"]["area"] == "MATH 2940"
    assert items["Learn Rust"]["long_term"]
    do(client, "add", title="CS 2110 Lec", when="fixed", start="2026-10-20T10:10", end="2026-10-20T11:00")
    do(client, "add", title="CS 2110 Office Hours", when="fixed", start="2026-10-20T13:00", end="2026-10-20T15:00")
    lec, hours = ask(client, "events", text="lec")[0], ask(client, "events", text="office")[0]  # type: ignore[index]
    assert (lec["category_color"], lec["left_out"]) == ("blue", None)
    assert (hours["category_color"], hours["filtered"], hours["left_out"]) == ("green", True, "filtered")
    undone = do(client, "undo", command_id=out["command_id"])
    assert undone and [i["title"] for i in ask(client, "items")] == []  # type: ignore[union-attr]


def test_an_event_s_life_in_the_drawer(client: TestClient) -> None:
    made = do(client, "add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00",
              color="violet", notes="Room 120")["result"]["item"]  # fmt: skip
    assert (made["color"], made["notes"]) == ("violet", "Room 120")
    moved = do(client, "edit", id=made["id"], start="2026-10-22T19:00", end="2026-10-22T20:30", color=None)
    assert (moved["result"]["item"]["start"], moved["result"]["item"]["color"]) == ("2026-10-22T19:00", None)
    assert ask(client, "events", text="chess")[0]["start"] == "2026-10-22T19:00"  # type: ignore[index]
    refused = client.post("/api/c/edit", json={"id": made["id"], "color": "chartreuse"})
    assert refused.status_code == 422 and refused.json()["field"] == "color"
    gone = do(client, "drop", id=made["id"])
    assert ask(client, "events", text="chess") == []
    do(client, "undo", command_id=gone["command_id"])
    assert len(ask(client, "events", text="chess")) == 1  # type: ignore[arg-type]


def test_a_task_dropped_on_a_day_is_due_then_and_a_reminder_doesn_t_block_time(client: TestClient) -> None:
    essay = do(client, "add", title="Essay", preset="Assignment", due="2026-10-25T17:00", duration_min=120)
    do(client, "edit", id=essay["result"]["item"]["id"], due="2026-10-20T17:00")  # what dropping on Tuesday sends
    do(client, "add", title="PS 8 due", when="fixed", start="2026-10-19T09:00", end="2026-10-20T17:00")
    do(client, "replan")
    placed = blocks(client, essay["result"]["item"]["id"])
    assert placed and all(end <= "2026-10-20T17:00" for _, end in placed)  # planned through the reminder


def test_counting_room_bookings_after_all(client: TestClient, app: App) -> None:
    booking = do(client, "add", title="Study room 3", when="fixed", start="2026-10-19T09:00", end="2026-10-19T23:00")
    assert booking["result"]["item"]["left_out"] is None  # made in Friday: no calendar, so it counts
    do(client, "settings_set", key="busy", value={"count_reminders": True})
    reminder = do(client, "add", title="Essay due", when="fixed", start="2026-10-20T09:00", end="2026-10-20T10:00")
    assert reminder["result"]["item"]["left_out"] is None


def test_an_overloaded_monday_and_what_gives(client: TestClient) -> None:
    do(client, "add", title="Robotics", when="fixed", start="2026-10-19T09:00", end="2026-10-19T14:00")
    do(client, "add", title="CS 2110 Lecture", when="fixed", start="2026-10-19T14:00", end="2026-10-19T18:00")
    do(client, "add", title="Poker night", when="fixed", start="2026-10-19T18:00", end="2026-10-19T23:00")
    ps = do(client, "add", title="Problem set", preset="Assignment", due="2026-10-19T23:00", duration_min=180)
    do(client, "replan")
    triage = ask(client, "triage")
    late_before = sum(triage["late"].values())  # type: ignore[index]
    skip = next(o for o in triage["options"] if o["skip_title"] == "Poker night")  # type: ignore[index]
    assert "CS 2110 Lecture" not in [o["skip_title"] for o in triage["options"]]  # type: ignore[index]
    for step in skip["steps"]:
        do(client, step["command"], **step["input"])
    do(client, "replan")
    assert any(start >= "2026-10-19T18:00" for start, _ in blocks(client, ps["result"]["item"]["id"]))
    after = ask(client, "triage")
    assert sum(after["late"].values()) < late_before  # type: ignore[index]
    poker = ask(client, "events", text="poker")[0]  # type: ignore[index]
    assert poker["start"] == "2026-10-19T18:00"  # still on the calendar


def test_another_way_previewed_then_picked(client: TestClient) -> None:
    for n in range(1, 5):
        do(client, "add", title=f"Essay {n}", preset="Assignment", due=f"2026-10-2{n}T23:59", duration_min=120)
    do(client, "replan")
    ways = ask(client, "other_ways")["ways"]  # type: ignore[index]
    assert ways and all(w["blocks"] and w["summary"] and w["hours"] > 0 for w in ways)
    way = ways[-1]
    do(client, "other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    do(client, "replan")
    mine = {(b["item_id"], b["start"]) for b in ask(client, "plan")["blocks"]}  # type: ignore[index]
    assert mine == {(b["item_id"], b["start"]) for b in way["blocks"]}


def test_exam_prep_before_its_exam_and_a_switch_to_keep_it_going(client: TestClient) -> None:
    do(client, "add", title="CHEM 2090 Prelim 2", when="fixed", start="2026-10-21T19:30", end="2026-10-21T21:00")
    prep = do(client, "add", title="CHEM 2090 prelim study guide", due="2026-10-21T23:59", duration_min=120)
    item = prep["result"]["item"]
    assert (item["preset"], item["area"], item["pointless_late"]) == ("Exam prep", "CHEM 2090", True)
    do(client, "replan")
    assert blocks(client, item["id"]) and all(end <= "2026-10-21T19:30" for _, end in blocks(client, item["id"]))
    off = do(client, "edit", id=item["id"], expires=False)["result"]["item"]
    assert off["pointless_late"] is False and off["expires"] is False
