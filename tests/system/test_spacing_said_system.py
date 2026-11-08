"""Friday says when it planned a repeat's times closer than you asked, the whole system (C50, 8 Nov): a real `fridayd
serve` on the real clock. A daily stretch asked to be 3 days apart can't be (each is due the day after the one
before), so every time goes a day after the last, none late; the plan says so in one line for the repeat, not one a
day, and each block's "why" says it too."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

SAID = "after the one before, closer than the 3 days you asked, so it isn't late"


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("spacing_said"))
    server.c("settings_set", key="sleep", value=SLEEP)
    tomorrow = (datetime.now(ZoneInfo(TZ)) + timedelta(days=1)).date()
    series = server.c("series_add", title="Stretch", every="day", duration_min=60, start_date=str(tomorrow))
    server.c("series_spacing", id=series["id"], days=3)
    server.until(lambda: [n for n in server.q("status")["notices"] if SAID in n])
    yield server
    server.stop()


def test_one_line_for_the_repeat_with_how_many_more(friday: Friday) -> None:
    status = friday.q("status")
    (said,) = [n for n in status["notices"] if n.startswith("Stretch on ")]
    assert SAID in said and "more of them are closer too" in said
    assert not any("Stretch" in title for title in status["late"])


def test_a_block_says_it_in_its_why(friday: Friday) -> None:
    blocks = sorted((b for b in friday.q("plan")["blocks"] if b["title"] == "Stretch"), key=lambda b: b["start"])
    assert len(blocks) > 2
    assert SAID in friday.q("why", key=blocks[1]["key"])["sentence"]
