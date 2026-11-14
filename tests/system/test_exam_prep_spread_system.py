"""Exam prep spread over the days before its exam, the whole system (14 Nov): a real `fridayd serve` on the real
clock. The built-in rule says so in Rules, and the prep for an exam four days off is planned on several of them;
switched off, the rule says it's off."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

SAID = "Exam prep is spread over the days before the exam, not crammed into one"
EXAM = (datetime.now(ZoneInfo(TZ)) + timedelta(days=4)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("exam_prep_spread"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        server.c("add", title="PHYS 1112 Prelim 2", preset="Exam", start=f"{EXAM}T19:30", end=f"{EXAM}T21:00")
        server.c("add", title="Prep: PHYS 1112 Prelim 2", preset="Exam prep", due=f"{EXAM}T19:30", duration_min=240)
        yield server
    finally:
        server.stop()


def test_the_rule_is_in_rules_in_plain_words(friday: Friday) -> None:
    rule = next(r for r in friday.q("rules") if r["name"] == "exam_prep_spread")
    assert (rule["sentence"], rule["source"], rule["enabled"], rule["background"]) == (SAID, "default", True, False)


def test_the_prep_is_planned_over_several_days_before_the_exam(friday: Friday) -> None:
    def days() -> set[str]:
        return {b["start"][:10] for b in friday.q("plan")["blocks"] if b["title"] == "Prep: PHYS 1112 Prelim 2"}

    assert friday.until(lambda: len(days()) >= 3)
    assert max(days()) <= EXAM


def test_it_switches_off_like_any_built_in(friday: Friday) -> None:
    friday.c("rule_set", name="exam_prep_spread", enabled=False)
    rule = next(r for r in friday.q("rules") if r["name"] == "exam_prep_spread")
    assert (rule["enabled"], rule["effect"]) == (False, "Off")
