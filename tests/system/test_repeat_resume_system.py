"""A repeat stopped and started again keeps the times you dropped one at a time, the whole system (audit, 12 Nov: Start
brought them back): a real `fridayd serve` on the real clock, with only HTTP between it and the test, as the app
sends it. A daily run has its time two days on dropped, is stopped from Settings → Repeating and started again; that
time is still dropped and isn't made again, and the rest are back."""

from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("repeat_resume"))
    yield server
    server.stop()


def runs(friday: Friday, status: str) -> list[dict]:
    return [i for i in friday.q("items", status=status, text="Morning run") if i["series_id"] is not None]


def test_a_time_dropped_before_stop_stays_dropped_once_started_again(friday: Friday) -> None:
    made = friday.c("add", title="Morning run", duration_min=30, every="day")
    series_id = made["series_id"]
    before = runs(friday, "todo")
    dropped = before[2]
    friday.c("drop", id=dropped["id"])
    friday.c("series_stop", id=series_id)
    assert runs(friday, "todo") == []
    friday.c("series_resume", id=series_id)
    back = runs(friday, "todo")
    assert dropped["id"] not in {i["id"] for i in back}
    assert len(back) == len(before) - 1
    assert [i["id"] for i in runs(friday, "dropped")] == [dropped["id"]]
    (row,) = [r for r in friday.q("series_list") if r["id"] == series_id]
    assert row["active"] is True
