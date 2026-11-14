"""Editing a rule, the whole system (14 Nov): a real `fridayd serve` on the real clock. A rule edited keeps its place
and name and the plan follows its new hours; one edited into another kind takes its place as a new rule; a built-in
rule's number changes the plan; Undo puts the old rule back."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("rule_edit"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        due = (datetime.now(ZoneInfo(TZ)) + timedelta(days=4)).strftime("%Y-%m-%dT17:00")
        server.c("add", title="Lab report", duration_min=240, due=due, preset="Assignment")
        server.c("rule_add", text="no work after 9pm", strength="Always")
        server.c("rule_add", text="lunch before 1pm")
        yield server
    finally:
        server.stop()


def names(friday: Friday) -> list[str]:
    return [r["name"] for r in friday.q("rules")]


def report_blocks(friday: Friday) -> list[dict]:
    return [b for b in friday.q("plan")["blocks"] if b["title"] == "Lab report"]


def test_an_edited_rule_keeps_its_place_and_the_plan_follows_it(friday: Friday) -> None:
    order = names(friday)
    name = next(r["name"] for r in friday.q("rules") if r["sentence"] == "No work after 9pm")
    out = friday.c("rule_edit", name=name, text="no work after 5pm")
    assert out["message"] == "Saved: No work after 5pm"
    assert names(friday) == order

    def by_five() -> list[dict]:
        blocks = report_blocks(friday)
        return blocks if blocks and all("04:00" <= b["end"][11:16] <= "17:00" for b in blocks) else []

    assert friday.until(by_five)  # the plan made after the edit keeps the lab report before 5pm


def test_another_kind_starts_over_in_the_same_place_and_undo_puts_it_back(friday: Friday) -> None:
    before = friday.q("rules")
    at = next(n for n, r in enumerate(before) if r["sentence"] == "Lunch before 1pm")
    answer = friday.http.post("/api/c/rule_edit", json={"name": before[at]["name"], "text": "gym in the morning"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["result"]["message"].startswith("Replaced with a new rule")
    now = friday.q("rules")
    assert now[at]["sentence"] == "Gym between 8am and 12pm" and now[at]["name"] != before[at]["name"]
    friday.c("undo", command_id=answer.json()["command_id"])
    assert [r["name"] for r in friday.q("rules")] == [r["name"] for r in before]


def test_a_built_in_number(friday: Friday) -> None:
    friday.c("rule_edit", name="daily_load", number=6)
    assert next(r for r in friday.q("rules") if r["name"] == "daily_load")["sentence"] == "At most 6 h of work a day"
