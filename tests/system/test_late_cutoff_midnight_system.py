"""Late work's last chance for work due at midnight, the whole system (audit, 12 Nov: "late_cutoff at midnight"): a
real `fridayd serve` on the real clock, the rule added in words over HTTP as the Rules box adds it. Physics homework
was due at 12am last night, as yesterday ended; "before <today>" is then already past, so it isn't planned, where
it was read as due today and given until the same weekday a week on. Chemistry homework due then too, which no rule
covers, is still planned (late), so the plan the test reads has been made."""

from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

NOW = datetime.now(ZoneInfo(TZ))
TODAY = NOW.strftime("%A").lower()
SAID = f"If physics homework becomes overdue, it must be done before {TODAY}"


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("late_cutoff_midnight"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        midnight = f"{NOW.date()}T00:00"
        for title in ("Physics 1112 HW7", "Chem 2090 Problem Set 9"):
            server.c("add", title=title, preset="Assignment", duration_min=60, due=midnight)
        server.c("rule_add", text=SAID)
        server.until(lambda: [b for b in server.q("plan")["blocks"] if b["title"] == "Chem 2090 Problem Set 9"])
        yield server
    finally:
        server.stop()


def test_due_at_midnight_its_last_chance_has_passed(friday: Friday) -> None:
    assert [b for b in friday.q("plan")["blocks"] if b["title"] == "Physics 1112 HW7"] == []
