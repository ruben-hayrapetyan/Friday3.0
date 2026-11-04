"""Readings that matter less the longer they're overdue (3 Nov), the whole system: a real `fridayd serve`, the setting
sent as Settings and the AI send it, and the plan the worker makes read back over HTTP, as the app reads it."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

READINGS = {"kinds": ["Reading"], "titles": [], "half_life_days": 3}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("fading"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def firsts(friday: Friday, titles: tuple[str, ...]) -> dict[str, str]:
    now = datetime.now(ZoneInfo(TZ))
    blocks = friday.q("plan", start=local(now - timedelta(days=1)), end=local(now + timedelta(days=8)))["blocks"]
    return {t: min((b["start"] for b in blocks if b["title"] == t), default="") for t in titles}


def test_a_week_late_reading_gives_way_to_work_still_on_time(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    friday.c("add", title="Old reading", preset="Reading", duration_min=120, due=local(now - timedelta(days=7)))
    friday.c("add", title="Problem set", preset="Assignment", duration_min=180, due=local(now + timedelta(hours=4)))
    titles = ("Old reading", "Problem set")

    def planned() -> dict[str, str] | None:
        f = firsts(friday, titles)
        return f if all(f.values()) else None

    friday.until(planned)  # planned once as by default (tests/commands/test_fading_late.py holds the default order)
    friday.c("settings_set", key="fading_late", value=READINGS)
    assert friday.q("settings")["fading_late"] == READINGS

    def faded() -> dict[str, str] | None:
        f = firsts(friday, titles)
        return f if all(f.values()) and f["Problem set"] < f["Old reading"] else None

    after = friday.until(faded)
    assert after["Problem set"] < after["Old reading"]  # fading: work on time comes first
    reading = next(i for i in friday.q("items") if i["title"] == "Old reading")
    assert reading["fading_late"] is True and reading["pointless_late"] is False
