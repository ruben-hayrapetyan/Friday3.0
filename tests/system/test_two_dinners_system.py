"""Two dinners in a day, the whole system (5 Nov: "sometimes i have 4 meals (2 dinners)"): a real `fridayd serve`,
meals logged over HTTP as Sleep & meals logs them, and the meals read back as the app reads them."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("two_dinners"))
    server.c("settings_set", key="sleep", value=SLEEP)
    server.c("settings_set", key="meal_tracking", value={"on": True})
    yield server
    server.stop()


def test_two_dinners_logged_yesterday_both_come_back_the_second_named_so(friday: Friday) -> None:
    day = (datetime.now(ZoneInfo(TZ)) - timedelta(days=1)).date()
    first = friday.c("meal_log", kind="dinner", start=f"{day}T18:00", end=f"{day}T18:45")
    second = friday.c("meal_log", kind="dinner", start=f"{day}T22:00", end=f"{day}T22:30")
    assert first["message"].startswith("Logged dinner") and second["message"].startswith("Logged second dinner")
    (shown,) = [d for d in friday.q("meals")["days"] if d["date"] == str(day)]
    dinners = sorted((m for m in shown["meals"] if m["kind"] == "dinner"), key=lambda m: m["start"])
    assert [(m["start"][11:], m["end"][11:], m["nth"]) for m in dinners] == [
        ("18:00", "18:45", 1),
        ("22:00", "22:30", 2),
    ]
