"""Violated, and why in words, the whole system (14 Nov): a real `fridayd serve` on the real clock, more work due soon
than fits before 6pm. "No work after 6pm" says the days it's violated, and Why? names the work and its due."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("rule_why"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        due = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).strftime("%Y-%m-%dT23:00")
        for n in range(6):
            server.c("add", title=f"Lab report {n}", duration_min=300, due=due, preset="Assignment")
        server.c("rule_add", text="no work after 6pm")
        yield server
    finally:
        server.stop()


def mine(friday: Friday) -> dict:
    return next(r for r in friday.q("rules") if r["sentence"] == "No work after 6pm")


def test_the_rule_says_the_days_it_is_violated(friday: Friday) -> None:
    rule = friday.until(lambda: (r := mine(friday))["violated"] and r)
    assert rule["effect"] == "Violated on " + ", ".join(f"{date.fromisoformat(d):%a}" for d in rule["violated"])
    assert rule["kept"].startswith("kept ")


def test_why_names_the_work_and_its_due(friday: Friday) -> None:
    friday.until(lambda: mine(friday)["violated"])
    lines = friday.q("rule_why", name=mine(friday)["name"])["lines"]
    said = " ".join(line["said"] for line in lines)
    assert "Lab report" in said and "(due " in said and "needed those hours" in said
