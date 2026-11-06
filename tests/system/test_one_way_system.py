"""Other ways one at a time, the whole system (6 Nov: "it just says the same static thing for over 20 seconds"): a
real `fridayd serve` on the real clock, its worker planning a few days of work, and the dialog's requests over HTTP:
one seed at a time, each a way of its own, then the one picked becoming the plan."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("one_way"))
    server.c("settings_set", key="sleep", value=SLEEP)
    soon = datetime.now(ZoneInfo(TZ)).date()
    # a week with room to plan it more than one way (four 2-hour essays fit only one)
    for n in range(1, 6):
        server.c("add", title=f"Essay {n}", preset="Assignment", due=f"{soon + timedelta(days=n + 2)}T23:59",
                 duration_min=300)  # fmt: skip
    for n in range(1, 4):
        server.c("add", title=f"Reading {n}", preset="Reading", due=f"{soon + timedelta(days=n + 1)}T23:59",
                 duration_min=90)  # fmt: skip
    server.c("replan")
    server.until(lambda: any(b["title"].startswith("Essay") for b in plan(server)))
    yield server
    server.stop()


def plan(friday: Friday) -> list[dict]:
    today = datetime.now(ZoneInfo(TZ)).date()
    return friday.q("plan", start=f"{today}T00:00", end=f"{today + timedelta(days=8)}T00:00")["blocks"]


def ways(friday: Friday) -> list[dict]:
    """As the dialog asks: one seed at a time, keeping ways unlike each other, until two or the seeds run out."""
    found: list[dict] = []
    for seed in range(1, 7):
        way = friday.q("other_way", seed=seed)["way"]
        if way and all(w["signature"] != way["signature"] for w in found):
            found.append(way)
        if len(found) == 2:
            break
    return found


def test_each_seed_is_asked_for_on_its_own_and_says_which_blocks_it_has(friday: Friday) -> None:
    first = friday.q("other_way", seed=1)
    assert (first["tries"], first["wanted"]) == (6, 2)
    found = ways(friday)
    assert found and all(len(w["signature"]) == 16 and w["blocks"] for w in found)
    again = friday.q("other_way", seed=found[0]["seed"])["way"]
    assert again["signature"] == found[0]["signature"]  # the same seed, the same way: a repeat is told apart


def test_the_way_picked_becomes_the_plan(friday: Friday) -> None:
    way = ways(friday)[0]
    friday.c("other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    wanted = {(b["item_id"], b["start"]) for b in way["blocks"]}
    assert friday.until(lambda: {(b["item_id"], b["start"]) for b in plan(friday) if b["item_id"]} >= wanted)
