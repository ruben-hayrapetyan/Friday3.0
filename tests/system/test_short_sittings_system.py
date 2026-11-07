"""Work sessions under five minutes are ignored, the whole system (7 Nov: "can you ignore work sessions less then 5
minutes"): a real `fridayd serve` on the real clock. The essay's timer started three minutes ago and the reading's
seven, beside it; both are stopped over HTTP as the app's Pause does. The essay's three minutes are told too short and
recorded nowhere; the reading's seven count."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from friday.commands.all import REGISTRY
from friday.commands.registry import run
from friday.core.db import connect
from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

assert "add" in REGISTRY  # the commands, registered as the server registers them


@pytest.fixture(scope="module")
def stopped(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, dict]]:
    server = Friday(tmp_path_factory.mktemp("short_sittings"))
    server.c("settings_set", key="sleep", value=SLEEP)
    due = f"{(datetime.now(ZoneInfo(TZ)) + timedelta(days=3)).date()}T23:00"
    ids = {
        "essay": server.c("add", title="essay", duration_min=120, due=due)["item"]["id"],
        "reading": server.c("add", title="reading", duration_min=60, due=due)["item"]["id"],
    }
    conn = connect(server.folder / "data" / "friday.db")
    now = int(datetime.now().timestamp() // 60)
    run(conn, "start", {"id": ids["reading"]}, now_utc=now - 7, actor="you", provisional=False)
    run(conn, "start", {"id": ids["essay"], "alongside": True}, now_utc=now - 3, actor="you", provisional=False)
    conn.close()
    said = {name: server.c("stop", id=ids[name]) for name in ("essay", "reading")}
    yield server, ids | {"said": said}
    server.stop()


def test_three_minutes_is_told_too_short(stopped: tuple[Friday, dict]) -> None:
    _, ids = stopped
    out = ids["said"]["essay"]
    assert out["minutes"] == 0 and "too short to count (under 5 min)" in out["message"]


def test_and_recorded_nowhere(stopped: tuple[Friday, dict]) -> None:
    friday, ids = stopped
    assert friday.q("item", id=ids["essay"])["item"]["done_min"] == 0
    today = datetime.now(ZoneInfo(TZ)).date()
    sessions = friday.q("review", date=str(today))["sessions"]
    assert [s for s in sessions if s["item_id"] == ids["essay"]] == []


def test_seven_minutes_counts(stopped: tuple[Friday, dict]) -> None:
    friday, ids = stopped
    assert ids["said"]["reading"]["minutes"] in (7, 8)  # the clock may have ticked over since
    assert friday.q("item", id=ids["reading"])["item"]["done_min"] in (7, 8)
