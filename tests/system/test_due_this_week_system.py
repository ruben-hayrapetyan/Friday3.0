"""The To-do drawer's Due view (3 Nov: "in one quick look, i want to gague what i really need to get done today, even if
friday says that it is going to be late"), the whole system: a real `fridayd serve` answering what the list is drawn
from (web/src/lib/dueSoon.ts): each open item's due and whether it still matters once overdue, and the plan's late and
slipping work, so a row can say Friday has it late."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("due_week"))
    server.c("settings_set", key="sleep", value=SLEEP)
    server.c("settings_set", key="fading_late", value={"kinds": ["Reading"], "titles": [], "half_life_days": 3})
    yield server
    server.stop()


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def still_matters(item: dict) -> bool:
    """dueSoon.ts `stillMatters`, as the drawer reads it."""
    return item["firmness"] == "hard" and not item["pointless_late"] and not item["fading_late"]


def test_overdue_work_says_whether_it_still_matters_and_late_work_is_named(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    friday.c("add", title="Lab report", preset="Assignment", duration_min=60, due=local(now - timedelta(days=1)))
    friday.c("add", title="Old reading", preset="Reading", duration_min=60, due=local(now - timedelta(days=2)))
    friday.c("add", title="Quiz prep", preset="Exam prep", duration_min=60, due=local(now - timedelta(hours=5)))
    friday.c("add", title="Soft thing", preset="Errand", duration_min=30, due=local(now - timedelta(days=1)),
             firmness="soft")  # fmt: skip
    friday.c("add", title="Huge essay", preset="Assignment", duration_min=20 * 60, due=local(now + timedelta(hours=6)))
    items = {i["title"]: i for i in friday.q("items")}
    assert {t for t, i in items.items() if still_matters(i)} == {"Lab report", "Huge essay"}
    assert all(i["status"] == "todo" and i["due"] and i["series_id"] is None for i in items.values())  # all deadlines

    def late() -> set[str] | None:
        status = friday.q("status")
        named = {i["title"] for i in status["late_items"] + status["slipping"]}
        return named if "Huge essay" in named else None

    assert "Huge essay" in friday.until(late)  # twenty hours in six: the row says Friday has it late
