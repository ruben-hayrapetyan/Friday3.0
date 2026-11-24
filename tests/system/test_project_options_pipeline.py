"""A project's options, the whole pipeline (tests/features.toml: project_options; 24 Nov, the user: "go through every
single functionality of the app and build an extensive test suite ... absolutely nothing can break without our tests
flagging it"): a real `fridayd serve` in its own folder, a project's pace and finish-early days set over HTTP as its
Options popup sets them, and what follows read back: its options, the rule in Rules, and where the plan puts its
steps."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("project-options"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def settled(friday: Friday) -> None:
    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, 600)  # a busy machine replans slowly


def refused(friday: Friday, **body: object) -> dict:
    answer = friday.http.post("/api/c/project_set", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def project(friday: Friday, title: str, due_day: int, steps: int = 2, minutes: int = 60) -> tuple[int, list[int]]:
    made = friday.c("add", title=title, preset="Project", due=f"{day(due_day)}T17:00", firmness="hard")["item"]["id"]
    kids = [friday.c("add", title=f"{title} step {n}", duration_min=minutes, parent_id=made)["item"]["id"]
            for n in range(1, steps + 1)]  # fmt: skip
    return made, kids


def options(friday: Friday) -> dict[int, dict]:
    return {o["id"]: o for o in friday.q("project_options")}


def last_end(friday: Friday, project_id: int) -> str:
    return max(b["end"] for b in friday.q("item", id=project_id)["blocks"])


def test_nothing_set_lists_nothing_and_says_nothing_changed(friday: Friday) -> None:
    made, _ = project(friday, "Quiet project", 8)
    assert made not in options(friday)
    assert friday.c("project_set", id=made)["message"] == "Nothing changed"
    assert made not in options(friday)


def test_its_pace_is_kept_said_and_kind_takes_it_away(friday: Friday) -> None:
    made, _ = project(friday, "Robotics build", 9)
    said = friday.c("project_set", id=made, pacing="front")["message"]
    assert said == "Robotics build: most of it early"
    assert options(friday)[made] == {"id": made, "pacing": "front", "early_days": 0}
    assert friday.c("project_set", id=made, pacing="back")["message"] == "Robotics build: most of it toward its due"
    assert friday.c("project_set", id=made, pacing="linear")["message"] == "Robotics build: spread evenly to its due"
    assert options(friday)[made]["pacing"] == "linear"
    assert friday.c("project_set", id=made, pacing="kind")["message"] == "Robotics build: as its kind is paced"
    assert made not in options(friday)


def test_finishing_early_is_a_rule_in_rules_and_zero_takes_it_away(friday: Friday) -> None:
    made, _ = project(friday, "History essay", 10)
    said = friday.c("project_set", id=made, early_days=3)["message"]
    assert said == "History essay: aims to finish 3 days early"
    assert options(friday)[made] == {"id": made, "pacing": None, "early_days": 3}
    rule = next(r for r in friday.q("settings")["rules"] if r["name"] == f"you:project:{made}:early")
    assert (rule["type"], rule["params"], rule["scope"]) == ("finish_early", {"days": 3}, {"project": [str(made)]})
    assert rule["reason"] == "Finish History essay 3 days early" and rule["enabled"]
    assert friday.c("project_set", id=made, early_days=1)["message"] == "History essay: aims to finish 1 day early"
    mine = [r for r in friday.q("settings")["rules"] if r["name"] == f"you:project:{made}:early"]
    assert [r["params"]["days"] for r in mine] == [1]
    assert friday.c("project_set", id=made, early_days=0)["message"] == "History essay: no aim to finish early"
    assert made not in options(friday)
    assert not [r for r in friday.q("settings")["rules"] if r["name"] == f"you:project:{made}:early"]


def test_both_at_once_are_said_together(friday: Friday) -> None:
    made, _ = project(friday, "Thesis chapter", 12)
    said = friday.c("project_set", id=made, pacing="front", early_days=2)["message"]
    assert said == "Thesis chapter: most of it early, aims to finish 2 days early"
    assert options(friday)[made] == {"id": made, "pacing": "front", "early_days": 2}


def test_a_rule_switched_off_in_rules_isnt_an_option_then(friday: Friday) -> None:
    made, _ = project(friday, "Group poster", 11)
    friday.c("project_set", id=made, early_days=2)
    friday.c("rule_set", name=f"you:project:{made}:early", enabled=False)
    assert made not in options(friday)
    friday.c("rule_set", name=f"you:project:{made}:early", enabled=True)
    assert options(friday)[made]["early_days"] == 2


def test_finishing_early_moves_its_steps_ahead_of_its_due(friday: Friday) -> None:
    made, _ = project(friday, "Lab notebook", 6, steps=2, minutes=90)
    friday.c("project_set", id=made, pacing="back")
    settled(friday)
    friday.c("project_set", id=made, early_days=4)
    settled(friday)
    assert friday.until(lambda: last_end(friday, made) <= f"{day(2)}T23:59", 300)


def test_refuses_what_isnt_a_project_more_days_than_it_has_and_a_pace_it_doesnt_know(friday: Friday) -> None:
    task = friday.c("add", title="Plain task", duration_min=30)["item"]["id"]
    said = refused(friday, id=task, pacing="front")
    assert (said["field"], said["message"]) == ("id", "id: Plain task isn't a project")
    made, kids = project(friday, "Short project", 3)
    said = refused(friday, id=made, early_days=5)
    assert said["field"] == "early_days" and "finish early by fewer than that" in said["message"]
    assert made not in options(friday)
    assert "isn't a project" in refused(friday, id=kids[0], pacing="front")["message"]  # a step isn't one
    assert "early_days" in str(refused(friday, id=made, early_days=31))
    assert "pacing" in str(refused(friday, id=made, pacing="sideways"))
    refused(friday, id=999999, pacing="front")


def test_a_project_kind_with_no_steps_yet_has_options(friday: Friday) -> None:
    made = friday.c("add", title="Empty project", preset="Project", due=f"{day(14)}T17:00")["item"]["id"]
    friday.c("project_set", id=made, pacing="back")
    assert options(friday)[made]["pacing"] == "back"
