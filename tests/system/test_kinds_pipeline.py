"""Kinds of to-do, the whole pipeline (tests/features.toml: kinds; 24 Nov, the user: "build an extensive test suite ...
i want to make sure that absolutely nothing can break without our tests flagging it"): a real `fridayd serve`; a kind
added in Settings → Tags as a copy of another and deleted again, over HTTP as the page sends it, and what that did read
back: the kinds in the settings, the to-dos and repeats that used it, its place in the priority order, its buffer,
a rule about it, and a Mac calendar read into it."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

MAC = {"X-Friday-Client": "mac"}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("kinds"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def refused(friday: Friday, verb: str, **body: Any) -> str:
    """A command Friday turns down: the 422 and the words it gives ("field: words")."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"]


def presets(friday: Friday) -> dict[str, dict]:
    return friday.q("settings")["presets"]


def rules(friday: Friday) -> list[dict]:
    return friday.q("settings")["rules"]


def test_a_kind_added_is_a_copy_of_the_one_it_is_like(friday: Friday) -> None:
    before = presets(friday)
    assert "Lab" not in before
    assert friday.c("kind_add", name="  Lab ", like="Assignment")["message"] == "Added Lab"  # trimmed
    after = presets(friday)
    assert after["Lab"] == before["Assignment"]
    assert set(after) == set(before) | {"Lab"}  # nothing else changed
    # a to-do of the new kind takes its defaults
    item = friday.c("add", title="Lab 3 report", preset="Lab", due="2026-12-04T17:00")["item"]
    assert item["preset"] == "Lab"
    like = friday.c("add", title="Essay draft", preset="Assignment", due="2026-12-04T17:00")["item"]
    assert (item["firmness"], item["shape"], item["amount"]) == (like["firmness"], like["shape"], like["amount"])


def test_a_kind_is_refused_twice_nameless_or_like_one_you_dont_have(friday: Friday) -> None:
    before = presets(friday)
    assert refused(friday, "kind_add", name="lab", like="Task") == "name: there is already a kind called lab"
    assert refused(friday, "kind_add", name="ASSIGNMENT", like="Task") == (
        "name: there is already a kind called ASSIGNMENT"
    )
    assert refused(friday, "kind_add", name="   ", like="Task") == "name: give it a name"
    assert refused(friday, "kind_add", name="Studio", like="Nope") == "like: no kind called Nope"
    assert presets(friday) == before


def test_a_kind_others_need_or_a_rule_names_isnt_deleted(friday: Friday) -> None:
    assert refused(friday, "kind_remove", name="Nope", move_to="Task") == "name: no kind called Nope"
    for read_into in ("Assignment", "Exam prep", "Class", "Exam", "Event"):
        assert refused(friday, "kind_remove", name=read_into, move_to="Task") == (
            f"name: calendars and mail are read into {read_into}, so it stays"
        )
    words = "move_to: pick another kind for what used it"
    assert refused(friday, "kind_remove", name="Lab", move_to="Lab") == words
    assert refused(friday, "kind_remove", name="Lab", move_to="Nope") == words
    spread = next(r for r in rules(friday) if r["name"] == "exam_prep_spread")
    friday.c("settings_set", key="rules", value=[*rules(friday), spread | {"name": "lab_spread",
                                                                           "scope": {"preset": ["Lab"]}}])  # fmt: skip
    assert refused(friday, "kind_remove", name="Lab", move_to="Assignment") == (
        "name: the rule lab_spread is about Lab; change or delete it first"
    )
    friday.c("settings_set", key="rules", value=[r for r in rules(friday) if r["name"] != "lab_spread"])
    assert "Lab" in presets(friday)


def test_deleting_a_kind_moves_what_used_it_and_forgets_it_everywhere(friday: Friday) -> None:
    friday.c("add", title="Lab 4 report", preset="Lab", due="2026-12-11T17:00")
    series = friday.c("series_add", title="Lab notebook", preset="Lab", every="mon", duration_min=30)
    friday.c("settings_set", key="kind_order", value=["Lab", "Assignment"])
    buffer = next(r for r in rules(friday) if r["type"] == "buffer")
    with_lab = [r | {"params": r["params"] | {"by_preset": {"Lab": "10m"}}} if r["type"] == "buffer" else r
                for r in rules(friday)]  # fmt: skip
    friday.c("settings_set", key="rules", value=with_lab)
    assert next(r for r in rules(friday) if r["type"] == "buffer")["params"]["by_preset"] == {"Lab": "10m"}
    # a Mac calendar read into it
    now = datetime.now(ZoneInfo(TZ))
    body = {"calendars": [{"id": "labs", "name": "Labs", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}],
            "events": [], "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    assert friday.http.post("/api/c/mac_sync", headers=MAC, json=body).status_code == 200
    friday.c("calendar_set", id="labs", mac=True, on=True, kind="Lab")
    assert {c["id"]: c["kind"] for c in friday.q("mac_calendars")}["labs"] == "Lab"

    labs = [i for i in friday.q("items", status="all") if i["preset"] == "Lab"]
    assert len(labs) >= 3  # two reports and the notebook's times
    out = friday.c("kind_remove", name="Lab", move_to="Assignment")
    assert out["message"] == f"Deleted Lab; {len(labs)} moved to Assignment"
    assert "Lab" not in presets(friday)
    every = {i["id"]: i for i in friday.q("items", status="all")}
    assert all(every[i["id"]]["preset"] == "Assignment" for i in labs)
    assert not [i for i in every.values() if i["preset"] == "Lab"]
    assert friday.q("settings")["kind_order"] == ["Assignment"]
    assert next(r for r in rules(friday) if r["type"] == "buffer")["params"] == buffer["params"]
    assert {c["id"]: c["kind"] for c in friday.q("mac_calendars")}["labs"] == "auto"  # back to deciding per event
    # the repeat makes Assignments from now on: its times, made again on other days, come out as one
    friday.c("series_edit", id=series["id"], every="tue")
    notebook = [i for i in friday.q("items") if i["title"] == "Lab notebook"]
    assert notebook and all(i["preset"] == "Assignment" for i in notebook)
    assert {datetime.fromisoformat(i["release"]).weekday() for i in notebook} == {1}  # Tuesdays now


def test_a_kind_with_nothing_using_it_is_deleted_without_a_count(friday: Friday) -> None:
    friday.c("kind_add", name="Studio", like="Task")
    assert friday.c("kind_remove", name="Studio", move_to="Task")["message"] == "Deleted Studio"
    assert "Studio" not in presets(friday)
    assert refused(friday, "kind_remove", name="Studio", move_to="Task") == "name: no kind called Studio"
    friday.c("kind_add", name="Studio", like="Chore")  # its name is free again
    assert presets(friday)["Studio"] == presets(friday)["Chore"]
