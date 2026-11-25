"""Other ways to plan the same work (tests/features.toml: ways: other_ways, other_way, other_way_pick), the whole
pipeline (24 Nov, the user: "go through every single functionality of the app and build an extensive test suite"): a
real `fridayd serve`, a week of work added over HTTP and planned by its worker, other ways asked for as the plan's
"Other ways" does, and one picked: the next plan is that way, and it counts as an answer Friday learns from."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from friday.commands.ways import PHRASES
from tests.system.test_beat_plan_system import TZ, Friday, local

NOW = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
TOMORROW = (NOW + timedelta(days=1)).replace(hour=0, minute=0)
WORK = {"Essay": 240, "Lab report": 120, "Reading": 120, "Problem set": 180}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("ways"))
    for n, (title, length) in enumerate(WORK.items()):
        server.c("add", title=title, duration_min=length, due=local(TOMORROW + timedelta(days=2 + n, hours=17)))
    start = TOMORROW + timedelta(hours=10)
    server.c("add", title="Lecture", when="fixed", start=local(start), end=local(start + timedelta(hours=1)))
    planned(server)
    yield server
    server.stop()


def planned(friday: Friday) -> dict[str, Any]:
    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up)
    return friday.q("plan")


def ahead(blocks: list[dict[str, Any]]) -> set[tuple[int, str, str]]:
    """The blocks from half an hour on: a plan made a quarter hour later starts at the next quarter hour."""
    soon = local(NOW + timedelta(minutes=30))
    return {(b["item_id"], b["start"], b["end"]) for b in blocks if b["start"] >= soon}


def minutes(block: dict[str, Any]) -> float:
    return (datetime.fromisoformat(block["end"]) - datetime.fromisoformat(block["start"])).total_seconds() / 60


def per_item(blocks: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for b in blocks:
        out[b["title"]] = out.get(b["title"], 0) + minutes(b)
    return out


@pytest.fixture(scope="module")
def ways(friday: Friday) -> dict[str, Any]:
    return friday.q("other_ways")


def test_two_other_ways_each_unlike_your_plan_and_each_other(friday: Friday, ways: dict[str, Any]) -> None:
    plan = friday.q("plan")
    assert len(ways["ways"]) == 2
    first, second = ({(b["item_id"], b["start"], b["end"]) for b in w["blocks"]} for w in ways["ways"])
    mine = {(b["item_id"], b["start"], b["end"]) for b in plan["blocks"]}
    assert first != mine and second != mine and first != second
    assert ways["ways"][0]["signature"] != ways["ways"][1]["signature"]
    assert len({w["seed"] for w in ways["ways"]}) == 2


def test_each_way_plans_the_same_work_and_says_its_sizes(friday: Friday, ways: dict[str, Any]) -> None:
    for way in ways["ways"]:
        assert per_item(way["blocks"]) == WORK  # every task its whole length, nothing else
        assert way["sessions"] == len(way["blocks"])
        assert way["hours"] == pytest.approx(sum(minutes(b) for b in way["blocks"]) / 60, abs=0.05)
        assert way["late"] == {}  # nothing here has to be late
        assert way["weights"] and all(w > 0 for w in way["weights"].values())


def test_the_current_costs_are_your_plans(friday: Friday, ways: dict[str, Any]) -> None:
    current = ways["current"]
    assert current and all(isinstance(v, int) for v in current.values())
    assert friday.q("other_ways")["current"] == current  # read from the saved plan, the same each time


def test_each_way_says_what_it_gains_and_gives_up_by_rule(friday: Friday, ways: dict[str, Any]) -> None:
    current = ways["current"]
    for way in ways["ways"]:
        moved = {r: way["rule_totals"].get(r, 0) - current.get(r, 0) for r in way["weights"] if r in PHRASES}
        moved = {r: d for r, d in moved.items() if d}
        if not moved:
            assert way["summary"] == "Much the same, arranged differently"
            continue
        most, least = max(moved.values()), min(moved.values())
        if most > 0:  # the rule it costs most more on is the first it gives up
            assert any(f"but {PHRASES[r][1]}" in way["summary"] for r, d in moved.items() if d == most)
        else:
            assert "but" not in way["summary"]
        if least < 0:  # and the one it saves most on the first it gains
            starts = [PHRASES[r][0].lower() for r, d in moved.items() if d == least]
            assert any(way["summary"].lower().startswith(s) for s in starts)
        else:
            assert way["summary"].startswith("Arranged differently; but ")


def test_one_way_at_a_time_is_the_same_for_the_same_seed(friday: Friday) -> None:
    one, again = friday.q("other_way", seed=3), friday.q("other_way", seed=3)
    assert (one["tries"], one["wanted"]) == (6, 2)
    assert one["way"] is not None and one["way"]["seed"] == 3
    assert one["way"]["signature"] == again["way"]["signature"]
    assert per_item(one["way"]["blocks"]) == WORK


def test_the_ways_seeds_are_the_ones_asked_for_one_at_a_time(friday: Friday, ways: dict[str, Any]) -> None:
    for way in ways["ways"]:
        alone = friday.q("other_way", seed=way["seed"])["way"]
        assert alone is not None and alone["signature"] == way["signature"]


def test_a_way_needs_its_seed(friday: Friday) -> None:
    answer = friday.http.get("/api/q/other_way")
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["query", "seed"]
    answer = friday.http.get("/api/q/other_way", params={"seed": "x"})
    assert answer.status_code == 422


def test_a_pick_needs_the_ways_costs(friday: Friday, ways: dict[str, Any]) -> None:
    answer = friday.http.post("/api/c/other_way_pick", json={"weights": ways["ways"][0]["weights"]})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "rule_totals"]
    assert friday.q("learning")["comparisons"] == 0  # nothing was learned from it


def test_picking_a_way_makes_it_your_plan_and_counts_as_your_answer(friday: Friday, ways: dict[str, Any]) -> None:
    way = ways["ways"][0]
    said = friday.c("other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    assert said["message"] == "That's your plan now"
    assert ahead(planned(friday)["blocks"]) == ahead(way["blocks"])
    assert friday.q("learning")["comparisons"] == 1


def test_a_way_picked_on_top_of_a_pick_plans_as_it_was_shown(friday: Friday) -> None:
    # The ways are made on the pick in force; picked, the new one plans as shown, the two picks' weights combined.
    found = friday.q("other_ways")["ways"]
    assert found
    way = found[-1]
    friday.c("other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    assert ahead(planned(friday)["blocks"]) == ahead(way["blocks"])
    assert friday.q("learning")["comparisons"] == 2
