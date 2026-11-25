"""Finished projects through the whole of Friday (tests/features.toml: archive; 24 Nov, the user: "build an extensive
test suite"): a real `fridayd serve`, each command sent over HTTP as the Projects page sends it, and what you'd then
see read back through other queries: the project and its steps, the plan, the Finished shelf, Undo."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("archive_pipeline"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def due(days: int) -> str:
    return local((datetime.now(ZoneInfo(TZ)) + timedelta(days=days)).replace(hour=17, minute=0, second=0))


def project(friday: Friday, title: str, steps: list[tuple[str, int]]) -> tuple[int, list[int]]:
    pid = friday.c("add", title=title, preset="Project", due=due(6), duration_min=60)["item"]["id"]
    kids = [friday.c("add", title=s, parent_id=pid, duration_min=m)["item"]["id"] for s, m in steps]
    return pid, kids


def status(friday: Friday, item_id: int) -> str:
    return friday.q("item", id=item_id)["item"]["status"]


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def finished(friday: Friday) -> dict[int, dict]:
    return {f["id"]: f for f in friday.q("projects_finished")}


def caught_up(friday: Friday) -> bool:
    s = friday.q("status")
    return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]


def planned(friday: Friday) -> set[int]:
    return {b["item_id"] for b in friday.q("plan")["blocks"]}


def test_archiving_drops_only_the_open_steps_and_unarchiving_brings_back_only_those(friday: Friday) -> None:
    pid, (done, dropped, open_) = project(friday, "Poster", [("Sketch", 30), ("Print", 30), ("Hang", 30)])
    friday.c("done", id=done)
    friday.c("drop", id=dropped)  # dropped by hand: stays dropped
    said = friday.c("project_archive", id=pid)
    assert said["message"] == "Poster archived"
    assert (status(friday, pid), status(friday, open_)) == ("done", "dropped")
    assert pid in finished(friday)
    assert friday.c("project_unarchive", id=pid)["message"] == "Poster is open again"
    assert [status(friday, i) for i in (pid, done, dropped, open_)] == ["todo", "done", "dropped", "todo"]
    assert pid not in finished(friday)


def test_the_finished_shelf_says_what_it_took_against_its_steps(friday: Friday) -> None:
    pid, (a, b) = project(friday, "Lab report", [("Analyze", 90), ("Write", 60)])
    yesterday = datetime.now(ZoneInfo(TZ)).replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1)
    friday.c("log", id=a, start=local(yesterday), end=local(yesterday + timedelta(minutes=40)))
    friday.c("project_archive", id=pid)
    shelf = finished(friday)[pid]
    assert (shelf["title"], shelf["steps"], shelf["estimate_min"], shelf["actual_min"]) == ("Lab report", 2, 150, 40)
    assert shelf["finished"] and shelf["finished"][:10] == local(datetime.now(ZoneInfo(TZ)))[:10]
    assert list(finished(friday))[0] == pid  # newest first


def test_deleting_a_finished_project_drops_it_and_its_steps_and_undo_brings_it_back(friday: Friday) -> None:
    pid, kids = project(friday, "Garden plan", [("Measure", 30), ("Order seeds", 15)])
    friday.c("project_archive", id=pid)
    answer = friday.http.post("/api/c/project_delete", json={"id": pid})
    assert answer.status_code == 200, answer.text
    assert answer.json()["result"]["message"] == "Garden plan deleted"
    assert pid not in finished(friday)
    assert {status(friday, i) for i in (pid, *kids)} == {"dropped"}
    friday.c("undo", command_id=answer.json()["command_id"])
    assert pid in finished(friday)
    assert status(friday, pid) == "done"
    # still archived after Undo: unarchiving brings its steps back
    friday.c("project_unarchive", id=pid)
    assert {status(friday, i) for i in kids} == {"todo"}


def test_deleting_keeps_the_time_you_put_in(friday: Friday) -> None:
    pid, (step,) = project(friday, "Thesis outline", [("Read sources", 120)])
    yesterday = datetime.now(ZoneInfo(TZ)).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=1)
    friday.c("log", id=step, start=local(yesterday), end=local(yesterday + timedelta(minutes=50)))
    friday.c("project_delete", id=pid)
    assert friday.q("item", id=step)["item"]["done_min"] == 50
    assert status(friday, step) == "dropped"


def test_deleting_an_open_project_takes_its_steps_off_the_plan(friday: Friday) -> None:
    pid, kids = project(friday, "Move flat", [("Pack", 60), ("Clean", 60)])
    friday.c("replan")
    assert friday.until(lambda: caught_up(friday) and set(kids) <= planned(friday))
    friday.c("project_delete", id=pid)
    assert friday.until(lambda: caught_up(friday) and not set(kids) & planned(friday))
    assert pid not in finished(friday)  # deleted, not finished


def test_a_project_of_the_project_kind_without_steps_is_still_a_project(friday: Friday) -> None:
    pid = friday.c("add", title="Learn Rust", preset="Project", due=due(9), duration_min=120)["item"]["id"]
    friday.c("project_archive", id=pid)
    assert finished(friday)[pid]["estimate_min"] == 120  # its own length, having no steps
    friday.c("project_delete", id=pid)
    assert pid not in finished(friday) and status(friday, pid) == "dropped"


def test_a_task_or_a_step_isnt_a_project_and_a_gone_id_is_said(friday: Friday) -> None:
    task = friday.c("add", title="Buy stamps", duration_min=15, due=due(2))["item"]["id"]
    pid, (step,) = project(friday, "Recital", [("Practice", 60)])
    for verb in ("project_delete", "project_archive", "project_unarchive"):
        assert refused(friday, verb, id=task) == {"field": "id", "message": "id: Buy stamps isn't a project"}
        assert refused(friday, verb, id=step)["message"] == "id: Practice isn't a project"
        assert "isn't there any more" in refused(friday, verb, id=999_999)["message"]
    assert status(friday, task) == "todo" and status(friday, step) == "todo" and status(friday, pid) == "todo"
    assert "id" in str(refused(friday, "project_delete"))  # no id at all
