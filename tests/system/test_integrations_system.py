"""Todoist through the whole of Friday (C96): a real `fridayd serve`, a stand-in Todoist on a real port
(FRIDAY_API_TODOIST), and what the app does over HTTP: connect, the first read reviewed in the Inbox, new to-dos
straight in and planned, done in Friday closed in Todoist, done in Todoist done in Friday."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.integrations.fake_todoist import HARNESS, FakeTodoist
from tests.integrations.kit import serve
from tests.system.test_beat_plan_system import TZ, Friday


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, FakeTodoist]]:
    fake = FakeTodoist(HARNESS.token)
    soon = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=3)
    fake.add("Write the grant report", f"{soon}", 120)
    fake.add("Renew passport", f"{soon}T17:00:00")
    address, stop = serve(fake)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_API_TODOIST", f"{address}/api/v1")
        friday = Friday(tmp_path_factory.mktemp("todoist"))
    yield friday, fake
    friday.stop()
    stop()


def titles(friday: Friday) -> set[str]:
    return {i["title"] for i in friday.q("items")}


def test_connecting_reviews_the_first_read_then_new_ones_come_straight_in_and_get_planned(world) -> None:  # noqa: ANN001
    friday, fake = world
    connected = friday.c("integration_connect", kind="todoist", token=HARNESS.token)
    assert connected["source"]["arrival"] == "inbox_first"
    batch = friday.until(lambda: next((s["batch"] for s in friday.q("inbox")["suggestions"]
                                       if (s.get("batch") or "").startswith("integration:")), None))  # fmt: skip
    assert not titles(friday) & {"Write the grant report", "Renew passport"}  # waiting, not in
    friday.c("batch_accept", batch=batch)
    assert {"Write the grant report", "Renew passport"} <= titles(friday)
    fake.add("Book the venue", f"{datetime.now(ZoneInfo(TZ)).date() + timedelta(days=4)}", 60)
    friday.c("sync_now")
    assert friday.until(lambda: "Book the venue" in titles(friday))
    report = next(i for i in friday.q("items") if i["title"] == "Write the grant report")
    assert report["duration_min"] == 120
    assert friday.until(lambda: any(b["item_id"] == report["id"] for b in friday.q("plan")["blocks"]))


def test_done_goes_both_ways(world) -> None:  # noqa: ANN001
    friday, fake = world
    passport = next(i for i in friday.q("items") if i["title"] == "Renew passport")
    import time

    began = time.monotonic()
    friday.c("done", id=passport["id"])
    task = next(t for t in fake.tasks.values() if t["content"] == "Renew passport")
    assert friday.until(lambda: task["checked"])
    assert time.monotonic() - began < 10, "done reached Todoist at the job's minute, not at once"  # C97
    venue = next(t for t in fake.tasks.values() if t["content"] == "Book the venue")
    venue["checked"] = True
    friday.c("sync_now")
    assert friday.until(lambda: "Book the venue" not in titles(friday))
