"""Other ways one at a time (6 Nov: "it just says the same static thing for over 20 seconds"): each way is half a
minute of planning on a full term, so the app asks for one seed at a time and shows each as it comes. A seed's way
is the one both at once would give, says which blocks it has so the app drops a repeat, and is none when it came out
as your plan."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from friday.planner.views import signature
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    for n in range(1, 5):
        app.do("add", title=f"Essay {n}", preset="Assignment", due=f"2026-10-2{n}T23:59", duration_min=120)
    app.do("add", title="Reading", preset="Reading", due="2026-10-23T23:59", duration_min=90)
    replan(app.conn, app.now_utc)
    return app


def keys(way: dict) -> list[tuple[int, str, str]]:
    return sorted((b["item_id"], b["start"], b["end"]) for b in way["blocks"])


def test_a_seeds_way_is_the_one_both_at_once_give(app: App) -> None:
    both = app.do("other_ways")["ways"]
    one = app.do("other_way", seed=both[0]["seed"])
    assert keys(one["way"]) == keys(both[0]) and one["way"]["signature"] == both[0]["signature"]
    assert (one["tries"], one["wanted"]) == (6, 2)


def test_two_seeds_give_two_ways_told_apart_by_their_signature(app: App) -> None:
    first, second = app.do("other_way", seed=1)["way"], app.do("other_way", seed=2)["way"]
    assert (first["signature"] == second["signature"]) == (keys(first) == keys(second))


def test_a_way_that_came_out_as_your_plan_is_none(tmp_path: Path) -> None:
    empty = new_app(tmp_path)  # nothing to plan: every way is your plan, no blocks
    replan(empty.conn, empty.now_utc)
    assert empty.do("other_way", seed=1) == {"way": None, "tries": 6, "wanted": 2}


def test_a_signature_is_the_blocks_whatever_their_order() -> None:
    class B:
        def __init__(self, item_id: int, start: int, end: int) -> None:
            self.item_id, self.start_utc, self.end_utc = item_id, start, end

    assert signature([B(1, 0, 15), B(2, 15, 30)]) == signature([B(2, 15, 30), B(1, 0, 15)])
    assert signature([B(1, 0, 15)]) != signature([B(1, 0, 30)])
