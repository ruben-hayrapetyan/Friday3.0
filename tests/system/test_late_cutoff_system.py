"""Late work's last chance, the whole system (8 Nov: "If math homework becomes overdue, it must be done before
sunday"): a real `fridayd serve` on the real clock. The rule is added in words over HTTP as the Rules box adds it; math
homework due last night is planned, all of it before the weekday the rule names (two days from today, so there's room
whatever day the test runs: "before sunday" run on a Sunday has no time left)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

NOW = datetime.now(ZoneInfo(TZ))
DAY = (NOW + timedelta(days=2)).strftime("%A").lower()
SAID = f"If math homework becomes overdue, it must be done before {DAY}"


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("late_cutoff"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        yesterday = (NOW - timedelta(days=1)).date()
        for title in ("Math 1920 HW10", "Chem 2090 Problem Set 9"):
            server.c("add", title=title, preset="Assignment", duration_min=60, due=f"{yesterday}T23:59")
        server.c("rule_add", text=SAID)
        server.until(lambda: [b for b in server.q("plan")["blocks"] if b["title"] == "Math 1920 HW10"])
        yield server
    finally:
        server.stop()


def test_the_rule_reads_without_the_ai_and_shows_in_words(friday: Friday) -> None:
    rules = [r for r in friday.q("settings")["rules"] if r["type"] == "late_cutoff"]
    assert [r["reason"] for r in rules] == [f"Overdue math homework is done before {DAY.title()}, never later"]
    assert rules[0]["scope"] == {"preset": "Assignment", "title": "math"}


def test_overdue_math_homework_is_planned_before_the_sunday_after_its_due(friday: Friday) -> None:
    last = f"{(NOW + timedelta(days=2)).date()}T00:00"
    blocks = [b for b in friday.q("plan")["blocks"] if b["title"] == "Math 1920 HW10"]
    assert blocks and all(b["end"] <= last for b in blocks)
