"""Two things timed at once, the whole system (2 Nov): a real `fridayd serve` on the real clock, its worker
replanning, only HTTP between it and the test as the app sends it, then the CLI against the same server."""

import subprocess
import sys
from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import REPO, SLEEP, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("alongside"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


@pytest.fixture(scope="module")
def items(friday: Friday) -> dict[str, int]:
    return {t: friday.c("add", title=t, duration_min=90)["item"]["id"] for t in ("reading", "laundry")}


def test_1_starting_alongside_keeps_both_running(friday: Friday, items: dict[str, int]) -> None:
    friday.c("start", id=items["reading"])
    out = friday.c("start", id=items["laundry"], alongside=True)
    assert out["message"] == "Timing laundry, alongside reading"
    status = friday.q("status")
    assert status["timer"]["item_id"] == items["laundry"] and status["timer"]["title"] == "laundry"
    assert [(t["item_id"], t["title"]) for t in status["alongside"]] == [(items["reading"], "reading")]


def test_2_the_worker_s_plan_holds_the_timer_and_now_shows_it(friday: Friday, items: dict[str, int]) -> None:
    friday.c("replan")
    now = friday.until(lambda: (n := friday.q("now")) and n.get("current") and n)
    assert now["current"]["item_id"] == items["laundry"] and now["current_source"] == "timer"


def test_3_the_cli_says_both(friday: Friday, items: dict[str, int]) -> None:
    env = {**friday.env, "FRIDAY_SERVER": f"http://127.0.0.1:{friday.port}", "COLUMNS": "400"}
    run = subprocess.run([sys.executable, "-m", "friday.cli.main", "status"], cwd=REPO, env=env, capture_output=True,
                         text=True, timeout=60)  # fmt: skip
    assert run.returncode == 0, run.stderr
    assert f"Timer on T{items['laundry']}" in run.stdout and f"Also timing T{items['reading']}" in run.stdout


def test_4_stopping_one_leaves_the_other_then_stopping_that_leaves_none(friday: Friday, items: dict[str, int]) -> None:
    assert friday.c("stop", id=items["laundry"])["item_id"] == items["laundry"]
    status = friday.q("status")
    assert status["timer"]["item_id"] == items["reading"] and status["alongside"] == []
    friday.c("stop")
    status = friday.q("status")
    assert status["timer"] is None and status["alongside"] == []


def test_5_three_at_most_said_as_the_app_shows_it(friday: Friday, items: dict[str, int]) -> None:
    more = [friday.c("add", title=f"chore {n}", duration_min=30)["item"]["id"] for n in range(3)]
    friday.c("start", id=items["reading"])
    for item in more[:2]:
        friday.c("start", id=item, alongside=True)
    refused = friday.http.post("/api/c/start", json={"id": more[2], "alongside": True})
    assert refused.status_code == 422 and "3 things are being timed already" in refused.text
    friday.c("start", id=more[2])  # a plain start switches: all three stop
    status = friday.q("status")
    assert status["timer"]["item_id"] == more[2] and status["alongside"] == []
