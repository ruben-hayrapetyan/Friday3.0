"""Time you timed is accounted for, the whole system (5 Nov: the Inbox asked "did you do it?" of CS A4 Complete while
its timer ran, and of everything else planned that evening): a real `fridayd serve` on the real clock. Two hours ago
the essay was planned for half an hour and the email for the hour after, and the essay's timer started; it's still
running. The Review the Inbox reads asks about neither, the calendar shows the email's hour missed, and the server's
own replans plan all of the email again."""

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
    server = Friday(tmp_path_factory.mktemp("timed_review"))
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    began = now - timedelta(hours=2, minutes=now.minute % 15)  # two hours back, on the quarter hour
    if (began - DAY_START).date() != (now - DAY_START).date():
        server.stop()
        pytest.skip("Friday's day began less than two hours ago")
    # awake for the hours before and after now, whenever the test runs
    awake = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}"}
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, awake | {"margin_min": 60}))
    conn = connect(server.folder / "data" / "friday.db")
    then = int(began.timestamp() // 60)

    def do(command: str, **payload: object) -> dict:
        return run(conn, command, payload, now_utc=then, actor="you", provisional=False).result

    due = f"{(now + timedelta(days=2)).date()}T23:00"
    ids = {
        "essay": do("add", title="essay", duration_min=240, due=due)["item"]["id"],
        "email": do("add", title="email", duration_min=60, due=due)["item"]["id"],
    }
    at = lambda m: f"{began + timedelta(minutes=m):%Y-%m-%dT%H:%M}"  # noqa: E731
    do("pin", id=ids["essay"], start=at(0), end=at(30), kind="locked")
    do("pin", id=ids["email"], start=at(30), end=at(90), kind="locked")
    replan(conn, then)
    do("start", id=ids["essay"])
    conn.close()
    yield server, ids | {"day": str((began - DAY_START).date()), "email_at": at(30)}
    server.stop()


def test_neither_the_timed_task_nor_what_it_took_the_place_of_is_asked_about(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    gaps = friday.q("review", date=ids["day"])["gaps"]
    assert [g["title"] for g in gaps if g["answer"] is None] == []


def test_the_calendar_shows_the_emails_hour_missed(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    day = ids["day"]
    plan = friday.q("plan", start=f"{day}T04:00", end=f"{day}T23:59")
    (email,) = [b for b in plan["blocks"] if b["item_id"] == ids["email"] and b["start"] == ids["email_at"]]
    assert email["state"] == "missed"


def test_the_servers_replans_plan_all_of_the_email_again(seeded: tuple[Friday, dict]) -> None:
    friday, ids = seeded
    friday.c("replan")
    now = datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%dT%H:%M")
    end = f"{(datetime.now(ZoneInfo(TZ)) + timedelta(days=3)).date()}T00:00"

    def email_ahead() -> int | None:
        blocks = friday.q("plan", start=now, end=end)["blocks"]
        ahead = [b for b in blocks if b["item_id"] == ids["email"] and b["start"] >= now and not b.get("state")]
        total = sum(minutes(b) for b in ahead)
        return total if total == 60 else None

    assert friday.until(email_ahead) == 60


def minutes(b: dict) -> int:
    start, end = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
    return int((end - start).total_seconds() // 60)
