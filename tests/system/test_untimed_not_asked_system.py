"""No timer, nothing asked, the whole system (7 Nov: "these notifications can get a little annoying especially of when
there was no timer, i didnt do anything"): a real `fridayd serve` on the real clock with untimed blocks planned again,
as Settings → Schedule's "Plan it again" saves it. Two hours ago the essay was planned for an hour and nothing was
timed. The Review the Inbox reads asks nothing, the calendar shows the hour missed, and the server plans it again."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from friday.commands.all import REGISTRY
from friday.commands.registry import run
from friday.core.db import connect
from friday.planner.service import replan
from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

DAY_START = timedelta(hours=4)
assert "add" in REGISTRY  # the commands, registered as the server registers them


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, dict]]:
    server = Friday(tmp_path_factory.mktemp("untimed"))
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    began = now - timedelta(hours=2, minutes=now.minute % 15)  # two hours back, on the quarter hour
    if (began - DAY_START).date() != (now - DAY_START).date():
        server.stop()
        pytest.skip("Friday's day began less than two hours ago")
    awake = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}"}
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, awake | {"margin_min": 60}))
    server.c("settings_set", key="planner", value={"assume_unreviewed": "not_done"})
    conn = connect(server.folder / "data" / "friday.db")
    then = int(began.timestamp() // 60)

    def do(command: str, **payload: object) -> dict:
        return run(conn, command, payload, now_utc=then, actor="you", provisional=False).result

    due = f"{(now + timedelta(days=2)).date()}T23:00"
    essay = do("add", title="essay", duration_min=120, due=due)["item"]["id"]
    at = f"{began:%Y-%m-%dT%H:%M}"
    do("pin", id=essay, start=at, end=f"{began + timedelta(hours=1):%Y-%m-%dT%H:%M}", kind="locked")
    replan(conn, then)
    conn.close()
    yield server, {"essay": essay, "day": str((began - DAY_START).date()), "at": at}
    server.stop()


def test_nothing_is_asked(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    gaps = friday.q("review", date=ids["day"])["gaps"]
    assert [g["title"] for g in gaps if g["answer"] is None] == []


def test_the_calendar_shows_the_hour_missed(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    day = ids["day"]
    after = (datetime.fromisoformat(day) + timedelta(days=1)).date()  # a Friday day runs 4am to 4am: past midnight too
    plan = friday.q("plan", start=f"{day}T04:00", end=f"{after}T04:00")
    (essay,) = [b for b in plan["blocks"] if b["item_id"] == ids["essay"] and b["start"] == ids["at"]]
    assert essay["state"] == "missed"


def test_the_server_plans_all_of_it_again(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    friday.c("replan")
    assert friday.until(lambda: friday.q("item", id=ids["essay"])["item"]["remaining_min"] == 120)
    now = datetime.now(ZoneInfo(TZ))

    def ahead() -> int | None:
        blocks = friday.q("plan", start=f"{now:%Y-%m-%dT%H:%M}", end=f"{(now + timedelta(days=3)).date()}T00:00")
        mins = [b for b in blocks["blocks"] if b["item_id"] == ids["essay"] and not b.get("state")]
        total = sum(int((datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).seconds / 60)
                    for b in mins)  # fmt: skip
        return total if total == 120 else None

    assert friday.until(ahead)
