"""A new all-day event leaves its day free, the whole system (7 Nov: Remy's Birthday, added as midnight to midnight,
took all of Tuesday and nothing was planned on it): a real `fridayd serve`, the birthday added over HTTP as it was,
yearly, on the day after tomorrow, and work that can only be done that day. The server's own replans plan it there,
lunch included, and the birthday shows as an all-day event of that day."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, str]]:
    server = Friday(tmp_path_factory.mktemp("all_day"))
    server.c("settings_set", key="sleep", value=SLEEP)
    day = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).date()
    after = day + timedelta(days=1)
    server.c("add", title="Remy's Birthday", when="fixed", start=f"{day}T00:00", end=f"{after}T00:00",
             every="rrule:FREQ=YEARLY", after=[], before=[], exceptions=[])  # fmt: skip
    server.c("add", title="essay", duration_min=180, release=f"{day}T00:00", due=f"{day}T23:00")
    server.c("replan")
    yield server, str(day)
    server.stop()


def day_plan(friday: Friday, day: str) -> dict:
    after = (datetime.fromisoformat(day) + timedelta(days=1)).date()
    return friday.q("plan", start=f"{day}T00:00", end=f"{after}T00:00")


def test_the_days_work_is_planned_on_it(friday: tuple[Friday, str]) -> None:
    server, day = friday
    assert server.until(lambda: [b for b in day_plan(server, day)["blocks"] if b["title"] == "essay"])


def test_the_birthday_is_on_that_day_and_blocks_nothing(friday: tuple[Friday, str]) -> None:
    server, day = friday
    (birthday,) = [f for f in day_plan(server, day)["fixed"] if f["title"] == "Remy's Birthday"]
    assert birthday["start"] == f"{day}T00:00"

    def essay_minutes() -> int | None:
        blocks = [b for b in day_plan(server, day)["blocks"] if b["title"] == "essay"]
        spans = [datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"]) for b in blocks]
        total = sum(span.seconds // 60 for span in spans)
        return total if total == 180 else None

    assert server.until(essay_minutes)  # all three hours fit beside it
