"""A quarter hour left empty between two evening blocks, the whole system (5 Nov: "why does it leave a gap between the
second 17.3 and what came before it"): a real `fridayd serve`, pins posted over HTTP as the app moves blocks, the
worker replanning after one is let go, and the plan read back as the app reads it."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("closed_gaps"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def test_a_block_let_go_after_a_gap_moves_up_to_meet_the_work_before_it(friday: Friday) -> None:
    # In the afternoon nothing prices the quarter hour: only keeping the plan steady held the reading where it was.
    day = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).date()
    essay = friday.c("add", title="Essay", preset="Assignment", duration_min=60, due=f"{day + timedelta(days=1)}T09:00")
    reading = friday.c("add", title="Reading", preset="Reading", duration_min=45, release=f"{day}T15:00",
                       due=f"{day}T16:00")  # fmt: skip
    friday.c("pin", id=essay["item"]["id"], start=f"{day}T14:00", end=f"{day}T15:00", kind="preferred")
    friday.c("pin", id=reading["item"]["id"], start=f"{day}T15:15", end=f"{day}T16:00", kind="preferred")
    window = {"start": f"{day}T12:00", "end": f"{day}T18:00"}

    def reading_at(start: str):  # noqa: ANN202
        def found() -> list[dict] | None:
            shown = friday.q("plan", **window)
            blocks = [b for b in shown["blocks"] if b["title"] == "Reading"]
            # the worker's plan, not the quick one drawn at once when a block is let go
            return blocks if not shown["provisional"] and [b["start"] for b in blocks] == [start] else None

        return found

    friday.until(reading_at(f"{day}T15:15"))  # where you put it, a quarter hour after the essay
    friday.c("unpin", id=reading["item"]["id"])
    (moved,) = friday.until(reading_at(f"{day}T15:00"))
    assert moved["end"] == f"{day}T15:45"
    essay_blocks = [b for b in friday.q("plan", **window)["blocks"] if b["title"] == "Essay"]
    assert [(b["start"], b["end"]) for b in essay_blocks] == [(f"{day}T14:00", f"{day}T15:00")]  # the pin held
