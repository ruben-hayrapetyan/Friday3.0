"""The calendar's faint rail of when you slept, got ready and ate (4 Nov: "add visuals for when I ate and when I went
to sleep/woke up/did my morning routines"), the whole system: a real `fridayd serve`, the Now bar's taps over HTTP,
and the two queries the rail reads (web/src/plan/lived.ts) giving each span's ends as local times, whole."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("lived"))
    server.c("settings_set", key="sleep", value=SLEEP)
    server.c("settings_set", key="sleep_tracking", value={"on": True})
    server.c("settings_set", key="meal_tracking", value={"on": True})
    yield server
    server.stop()


def days_ago(n: int) -> str:
    return str((datetime.now(ZoneInfo(TZ)) - timedelta(days=n)).date())


def test_a_tapped_night_gives_bed_up_and_ready_for_the_rail(friday: Friday) -> None:
    evening, morning = days_ago(3), days_ago(2)
    friday.c("sleep_mark", kind="bed", at=f"{evening}T23:40")
    friday.c("sleep_mark", kind="up", at=f"{morning}T08:05")
    friday.c("sleep_mark", kind="ready", at=f"{morning}T08:35")
    sleep = friday.q("sleep")
    assert sleep["on"] is True
    (night,) = [n for n in sleep["nights"] if n["date"] == evening]
    # asleep from bed to up, the routine from up to ready: the rail's two spans
    assert (night["bed"], night["up"], night["ready"]) == (f"{evening}T23:40", f"{morning}T08:05", f"{morning}T08:35")


def test_meals_eaten_and_skipped_come_back_as_the_rail_tells_them_apart(friday: Friday) -> None:
    day = days_ago(1)
    friday.c("meal_log", kind="lunch", start=f"{day}T12:10", end=f"{day}T12:40")
    friday.c("meal_skip", kind="breakfast", date=day)
    meals = friday.q("meals")
    assert meals["on"] is True
    (logged,) = [d for d in meals["days"] if d["date"] == day]
    by_kind = {m["kind"]: m for m in logged["meals"]}
    lunch = by_kind["lunch"]
    assert (lunch["start"], lunch["end"], lunch["skipped"]) == (f"{day}T12:10", f"{day}T12:40", False)
    assert by_kind["breakfast"]["skipped"] is True and by_kind["breakfast"]["start"] is None  # no span drawn


def test_tracking_off_says_so_and_the_rail_draws_nothing(friday: Friday) -> None:
    friday.c("settings_set", key="meal_tracking", value={"on": False})
    assert friday.q("meals")["on"] is False
    friday.c("settings_set", key="meal_tracking", value={"on": True})
