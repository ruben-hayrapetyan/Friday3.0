"""Exam focus as a rule, the whole system (14 Nov): a real `fridayd serve` on the real clock. "Focus on exams 3 days
before" is a rule in Rules; other courses' work due after the exam waits until it's over; editing its days moves when
focus starts, and switching it off lets the work back before the exam."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

EXAM_DAY = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("exam_focus"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        server.c("add", title="MATH 2940 Prelim 2", preset="Exam", start=f"{EXAM_DAY}T19:30", end=f"{EXAM_DAY}T21:00")
        due = (datetime.now(ZoneInfo(TZ)) + timedelta(days=6)).strftime("%Y-%m-%dT23:00")
        server.c("add", title="HIST 1200 essay", preset="Assignment", due=due, duration_min=120)
        server.c("rule_add", text="focus on exams 3 days before")
        yield server
    finally:
        server.stop()


def essay_starts(friday: Friday) -> list[str]:
    return sorted(b["start"] for b in friday.q("plan")["blocks"] if b["title"] == "HIST 1200 essay")


def test_it_is_a_rule_in_rules(friday: Friday) -> None:
    rule = next(r for r in friday.q("rules") if r["type"] == "exam_focus")
    assert (rule["sentence"], rule["source"], rule["enabled"]) == (
        "Focus on an exam's course 3 days before it",
        "you",
        True,
    )
    assert "exam_focus" not in friday.q("settings")


def test_other_courses_wait_and_its_days_and_switch_change_that(friday: Friday) -> None:
    after = f"{EXAM_DAY}T21:00"
    assert friday.until(lambda: (s := essay_starts(friday)) and all(x >= after for x in s))
    exam = next(e for e in friday.q("exams") if e["item"]["title"] == "MATH 2940 Prelim 2")
    assert exam["focus_from"] is not None
    friday.c("rule_edit", name="you:exam-focus", overrides={"amount": 1})
    later = next(e for e in friday.q("exams") if e["item"]["title"] == "MATH 2940 Prelim 2")["focus_from"]
    assert later > exam["focus_from"]  # a day before, not three
    friday.c("rule_set", name="you:exam-focus", enabled=False)
    assert next(e for e in friday.q("exams") if e["item"]["title"] == "MATH 2940 Prelim 2")["focus_from"] is None
