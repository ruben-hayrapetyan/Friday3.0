"""A project is judged by its steps, the whole system (13 Nov: "CDJ Article isn't planned before it's due", in the
plan's header, with its three steps planned on the calendar days before its due): a real `fridayd serve` planning a
project's steps in its worker. The header's pill and the To-do lists read `status.late_items` and `status.slipping`,
so neither may name the project while its steps are planned in time; and once the steps are done, the plan has
nothing of the project's own."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("project_steps"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def article(friday: Friday, title: str) -> tuple[int, dict[str, int], str]:
    """The client's project, due in four days at 5pm: three steps each waiting on the one before, none with a due."""
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    due = local((now + timedelta(days=4)).replace(hour=17, minute=0))
    project = friday.c("add", title=title, preset="Project", due=due, duration_min=375)["item"]["id"]
    steps = {}
    for step, minutes in (("Outline", 60), ("Draft", 180), ("Revise", 135)):
        steps[step] = friday.c("add", title=f"{step} {title}", parent_id=project, duration_min=minutes)["item"]["id"]
    friday.c("depend", item_id=steps["Draft"], depends_on_id=steps["Outline"])
    friday.c("depend", item_id=steps["Revise"], depends_on_id=steps["Draft"])
    return project, steps, due


def warned(friday: Friday) -> set[int]:
    status = friday.q("status")
    return {i["item_id"] for i in status["late_items"] + status["slipping"]}


def replanned(friday: Friday) -> bool:
    status = friday.q("status")
    return status["plan_generation"] is not None and status["plan_generation"] >= status["generation"]


def test_a_projects_steps_planned_before_its_due_leave_it_out_of_the_warnings(friday: Friday) -> None:
    project, steps, due = article(friday, "CDJ Article")

    def on_track() -> dict | None:
        found = [p for p in friday.q("projects") if p["item"]["id"] == project]
        return found[0] if found and found[0]["status"] == "on_track" and replanned(friday) else None

    assert friday.until(on_track)["planned_finish"] < due
    planned = {b["item_id"] for b in friday.q("plan")["blocks"]}
    assert planned >= set(steps.values()) and project not in planned
    assert project not in warned(friday)  # "CDJ Article isn't planned before it's due"


def test_a_project_whose_steps_are_done_has_no_time_of_its_own_on_the_plan(friday: Friday) -> None:
    project, steps, _ = article(friday, "Lab writeup")
    for step in steps.values():
        friday.c("done", id=step)
    friday.until(lambda: replanned(friday))
    assert project not in {b["item_id"] for b in friday.q("plan")["blocks"]}  # its own 6h15 was planned as work
    assert project not in warned(friday)
