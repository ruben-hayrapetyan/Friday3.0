"""Undated work placed by rules (3 Nov), the whole system: a real `fridayd serve`. Work with no due date you logged
in the afternoons comes back as an Inbox question; keeping it adds a rule the Rules page lists, and the worker's plan
keeps undated work inside it while work with a due goes where it must."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("undated"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def test_logged_afternoons_become_a_rule_you_keep_and_the_plan_follows_it(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    # an errand is done in one sitting: 14 h, 12 of them logged, leaves 2 h for the 2-hour window
    errand = friday.c("add", title="Sort photos", preset="Errand", duration_min=14 * 60)["item"]["id"]
    for back in range(2, 8):
        day = (now - timedelta(days=back)).replace(hour=14, minute=0)
        friday.c("log", id=errand, start=local(day), end=local(day + timedelta(hours=2)))
    decisions = {d["key"]: d for d in friday.q("status")["decisions"]}
    assert "between 2pm and 4pm" in decisions["learned:undated:window"]["title"]

    assert friday.c("conflict_resolve", key="undated:window", option="always")["message"].startswith("Added: ")
    listed = [r for r in friday.q("rules") if r["sentence"] == "Undated work between 2pm and 4pm"]
    assert [(r["strength"], r["editable"]) for r in listed] == [("Always", True)]  # on the Rules page, to change

    friday.c("add", title="Lab report", preset="Assignment", duration_min=120, due=local(now + timedelta(days=2)))
    window = {"start": local(now), "end": local(now + timedelta(days=7))}

    def planned() -> list[dict] | None:
        blocks = friday.q("plan", **window)["blocks"]
        mine = [b for b in blocks if b["title"] == "Sort photos"]
        return mine if mine and any(b["title"] == "Lab report" for b in blocks) else None

    for b in friday.until(planned):
        assert b["start"][11:] >= "14:00" and b["end"][11:] <= "16:00", b
