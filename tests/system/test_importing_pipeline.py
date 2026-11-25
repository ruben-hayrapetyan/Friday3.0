"""Bringing in the old apps through the whole of Friday (tests/features.toml: importing; 24 Nov, the user: "build an
extensive test suite"): a real `fridayd serve`, Todo List's and Chroma's files as those apps write them (made up here,
in the test's own folder: never the real ones in ~/Documents or ~/Library, so every call names its files), each
import sent over HTTP, and what came in read back: the to-dos and their kinds, dues and lists, the categories, the
color an event from the Mac shows in, and one Undo taking an import back."""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, Friday

# New York, whatever FRIDAY_TEST_HOUR says (24 Nov): the sample to-dos' dues are fixed UTC instants, read back as New
# York's local times (2026-12-04T22:00Z is 5pm there), so the server's zone is New York's too
TZ = "America/New_York"
MAC = {"X-Friday-Client": "mac"}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("importing_pipeline"))
    server.c("settings_set", key="sleep", value=SLEEP)
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"timezone": TZ})
    yield server
    server.stop()


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("old_apps")


def write(folder: Path, name: str, data: Any) -> str:
    path = folder / name
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return str(path)


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def mine(friday: Friday) -> dict[str, dict]:
    return {i["title"]: i for i in friday.q("items")}


TODOS = [
    {"id": "t1", "title": "Read Gatsby ch 3", "bucket": "readings", "horizon": "shortTerm",
     "dueDate": "2026-12-04T22:00:00Z"},
    {"id": "t2", "title": "  CS 3110 A4  ", "bucket": "assignments", "dueDate": "2026-12-05T04:59:00Z"},
    {"id": "t3", "title": "Email the registrar", "bucket": "emails"},
    {"id": "t4", "title": "Learn to juggle", "horizon": "longTerm"},
    {"id": "t5", "title": "Already finished", "isDone": True},
    {"id": "t6", "title": "   "},
    {"id": "t7", "title": "Essay with no due", "bucket": "assignments"},
    {"id": "t8", "title": "Odd one", "dueDate": "next tuesday-ish"},
]  # fmt: skip
CHROMA = {
    "categories": [
        {"name": "Classes", "slug": "classes", "color": "green", "pattern": r"\b(lecture|seminar)\b"},
        {"name": "Fun", "slug": "fun", "color": "pink", "pattern": r"\b(party|concert)\b", "note": "weekends"},
    ],
    "filter": {"label": "Hidden", "pattern": r"\bbirthday\b", "except": ["mom"]},
}


def test_1_neither_file_there_is_said_and_nothing_changes(friday: Friday, files: Path) -> None:
    said = refused(friday, "import_personal", todos_path=str(files / "nope.json"),
                   categories_path=str(files / "nada.json"))  # fmt: skip
    assert said["field"] == "todos_path" and "found neither" in said["message"] and "nope.json" in said["message"]
    assert mine(friday) == {}


def test_2_a_file_that_isnt_the_apps_is_said_not_a_crash(friday: Friday, files: Path) -> None:
    broken = write(files, "broken.json", "{not json")
    said = refused(friday, "import_personal", todos_path=broken, categories_path=str(files / "nada.json"))
    assert said["field"] == "todos_path" and "it isn't JSON" in said["message"]
    shaped = write(files, "shaped.json", {"todos": TODOS})  # an object, not Todo List's list
    said = refused(friday, "import_personal", todos_path=shaped, categories_path=str(files / "nada.json"))
    assert "not the list of tasks it writes" in said["message"]
    listed = write(files, "listed.json", [1, 2])
    assert "not the list of tasks" in refused(friday, "import_personal", todos_path=listed,
                                              categories_path=str(files / "nada.json"))["message"]  # fmt: skip
    cats = write(files, "cats_list.json", [CHROMA])
    said = refused(friday, "import_personal", todos_path=str(files / "nope.json"), categories_path=cats)
    assert said["field"] == "categories_path" and "not what it writes" in said["message"]
    assert mine(friday) == {}


def test_3_open_tasks_come_in_with_their_kinds_dues_and_lists(friday: Friday, files: Path) -> None:
    todos = write(files, "todos.json", TODOS)
    cats = write(files, "categories.json", CHROMA)
    said = friday.c("import_personal", todos_path=todos, categories_path=cats)["message"]
    assert said.startswith("Imported 5 tasks from Todo List and 2 categories from Chroma. Left out, to add by hand:")
    assert "Odd one (" in said
    got = mine(friday)
    assert set(got) == {"Read Gatsby ch 3", "CS 3110 A4", "Email the registrar", "Learn to juggle",
                        "Essay with no due"}  # fmt: skip
    assert got["Read Gatsby ch 3"]["preset"] == "Reading" and got["Read Gatsby ch 3"]["due"] == "2026-12-04T17:00"
    assert got["CS 3110 A4"]["preset"] == "Assignment" and got["CS 3110 A4"]["due"] == "2026-12-04T23:59"
    assert (got["Email the registrar"]["preset"], got["Email the registrar"]["duration_min"]) == ("Errand", 15)
    assert got["Learn to juggle"]["long_term"] is True and got["Read Gatsby ch 3"]["long_term"] is False
    essay = got["Essay with no due"]
    assert essay["preset"] == "Assignment" and essay["due"] is None and essay["firmness"] == "none"


def test_4_chromas_categories_replace_the_starter_set(friday: Friday) -> None:
    found = friday.q("settings")["categories"]
    assert [(c["name"], c["color"], c["pattern"]) for c in found["categories"]] == [
        ("Classes", "green", r"\b(lecture|seminar)\b"), ("Fun", "pink", r"\b(party|concert)\b")]  # fmt: skip
    assert found["categories"][1]["note"] == "weekends"
    assert found["filter"]["label"] == "Hidden" and found["filter"]["except_"] == ["mom"]  # read back by its field name


def test_5_again_nothing_comes_in_twice_and_your_categories_stay(friday: Friday, files: Path) -> None:
    other = write(files, "categories2.json", {"categories": [{"name": "Work", "slug": "work", "color": "blue",
                                                               "pattern": "standup"}]})  # fmt: skip
    more = write(files, "todos2.json", [*TODOS, {"id": "t9", "title": "New since"}])
    said = friday.c("import_personal", todos_path=more, categories_path=other)["message"]
    assert said.startswith("Imported 1 task from Todo List. Left out")  # the odd one is named again; no categories
    assert [c["name"] for c in friday.q("settings")["categories"]["categories"]] == ["Classes", "Fun"]
    titles = [i["title"] for i in friday.q("items")]
    assert titles.count("Read Gatsby ch 3") == 1 and "New since" in titles


def test_6_one_undo_takes_a_whole_import_back(friday: Friday, files: Path) -> None:
    todos = write(files, "todos3.json", [{"id": "u1", "title": "Undo me one"}, {"id": "u2", "title": "Undo me two"}])
    body = {"todos_path": todos, "categories_path": str(files / "nada.json")}
    answer = friday.http.post("/api/c/import_personal", json=body)
    assert answer.status_code == 200, answer.text
    assert answer.json()["result"]["message"] == "Imported 2 tasks from Todo List"
    assert {"Undo me one", "Undo me two"} <= set(mine(friday))
    friday.c("undo", command_id=answer.json()["command_id"])
    assert not {"Undo me one", "Undo me two"} & set(mine(friday))
    # and, undone, they come in again (the record of what came in went back too)
    again = friday.c("import_personal", todos_path=todos, categories_path=str(files / "nada.json"))
    assert again["message"] == "Imported 2 tasks from Todo List"


# Chroma's colors


def mac_event(friday: Friday) -> dict:
    """An event on the Mac's Home calendar, read in by the sync job."""
    now = datetime.now(ZoneInfo(TZ))
    at = (now + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    calendars = [{"id": "home", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}]
    events = [{"id": "EVT-dentist", "calendar": "home", "title": "Dentist", "start": at.isoformat(),
               "end": (at + timedelta(hours=1)).isoformat()}]  # fmt: skip
    body = {"calendars": calendars, "events": events, "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    assert friday.http.post("/api/c/mac_sync", headers=MAC, json=body).status_code == 200
    return friday.until(lambda: next(iter(friday.q("events", text="dentist")), None))


def color(friday: Friday) -> str | None:
    return friday.q("events", text="dentist")[0]["chroma_color"]


def test_7_an_events_chroma_color_shows_on_it_a_whole_repeats_over_one_times(friday: Friday, files: Path) -> None:
    event = mac_event(friday)
    assert event["chroma_color"] is None
    colors = write(files, "colors.json", {"chroma-cal:EVT-dentist/RID=20261126T150000": "red",
                                          "chroma-cal:EVT-dentist": "blue", "chroma-cal:other": "Unmarked",
                                          "chroma-cal:another": "green"})  # fmt: skip
    said = friday.c("import_chroma_colors", colors_path=colors)
    assert said["message"] == "Brought in Chroma's colors for 2 events"  # Unmarked left out
    assert color(friday) == "blue"
    fixed = [i for i in friday.q("plan")["fixed"] if i["title"] == "Dentist"]
    assert fixed and {i["chroma_color"] for i in fixed} == {"blue"}  # the calendar draws it so


def test_8_reading_again_takes_in_what_changed(friday: Friday, files: Path) -> None:
    colors = write(files, "colors.json", {"chroma-cal:EVT-dentist": "purple"})
    assert friday.c("import_chroma_colors", colors_path=colors)["message"] == "Brought in Chroma's colors for 1 event"
    assert color(friday) == "purple"
    colors = write(files, "colors.json", {"chroma-cal:EVT-dentist": "not-a-pigment"})
    assert friday.c("import_chroma_colors", colors_path=colors)["message"] == "Brought in Chroma's colors for 0 events"
    assert color(friday) is None


def test_9_a_missing_or_broken_colors_file_is_said_and_keeps_what_you_had(friday: Friday, files: Path) -> None:
    good = write(files, "colors.json", {"chroma-cal:EVT-dentist": "orange"})
    friday.c("import_chroma_colors", colors_path=good)
    said = refused(friday, "import_chroma_colors", colors_path=str(files / "gone.json"))
    assert said["field"] == "colors_path" and "found no" in said["message"]
    said = refused(friday, "import_chroma_colors", colors_path=write(files, "bad.json", "]["))
    assert said["field"] == "colors_path" and "it isn't JSON" in said["message"]
    said = refused(friday, "import_chroma_colors", colors_path=write(files, "list.json", ["red"]))
    assert "not what it writes" in said["message"]
    assert color(friday) == "orange"
