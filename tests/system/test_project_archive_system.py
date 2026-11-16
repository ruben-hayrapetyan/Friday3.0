"""Finished projects, the whole system: a real `fridayd serve` planning a project's steps in its worker. Archived, the
plan drops them and the Finished shelf lists it; unarchived, they're planned again."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("project_archive"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def planned(friday: Friday, ids: set[int]) -> set[int]:
    return {b["item_id"] for b in friday.q("plan")["blocks"]} & ids


def caught_up(friday: Friday) -> bool:
    status = friday.q("status")
    return status["plan_generation"] is not None and status["plan_generation"] >= status["generation"]


def test_archived_its_steps_leave_the_plan_and_come_back_unarchived(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    due = local((now + timedelta(days=5)).replace(hour=17, minute=0))
    project = friday.c("add", title="Lab report", preset="Project", due=due, duration_min=240)["item"]["id"]
    steps = {friday.c("add", title=f"{n} lab report", parent_id=project, duration_min=m)["item"]["id"]
             for n, m in (("Analyze", 120), ("Write", 120))}  # fmt: skip
    assert friday.until(lambda: caught_up(friday) and planned(friday, steps) == steps)
    friday.c("project_archive", id=project)
    assert friday.until(lambda: caught_up(friday) and not planned(friday, steps))
    assert [f["id"] for f in friday.q("projects_finished")] == [project]
    friday.c("project_unarchive", id=project)
    assert friday.until(lambda: caught_up(friday) and planned(friday, steps) == steps)
    assert friday.q("projects_finished") == []
