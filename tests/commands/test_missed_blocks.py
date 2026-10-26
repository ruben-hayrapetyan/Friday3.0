"""When work doesn't go to plan: a block that passes untimed and unmarked is planned again (or counted done, as you
choose), and the calendar says what became of each past block: done, timed (the sitting shows instead), missed, or
gone. "I did it" on a missed block counts it, its joined pieces too."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def planned(app: App, item: int, start: str = "2026-10-19T00:00", end: str = "2026-10-26T00:00") -> list[dict]:
    return [b for b in app.do("plan", start=start, end=end)["blocks"] if b["item_id"] == item]


def an_hour_at_nine(app: App, text: str = "essay due fri ~2h") -> int:
    item = app.do("add", text=text)["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    return item


def plan_again(app: App) -> None:
    planner = app.do("settings")["planner"]
    app.do("settings_set", key="planner", value=planner | {"assume_unreviewed": "not_done"})


def test_a_block_missed_is_planned_again_and_shows_as_missed(app: App) -> None:
    plan_again(app)
    essay = an_hour_at_nine(app)
    app.at("2026-10-19T10:30")
    replan(app.conn, app.now_utc)
    past = [b for b in planned(app, essay) if b["end"] <= "2026-10-19T10:30"]
    ahead = [b for b in planned(app, essay) if b["start"] >= "2026-10-19T10:30"]
    # The 9 o'clock hour, and the half of the next one gone by 10:30: missed, both.
    assert [(b["start"], b["state"]) for b in past] == [("2026-10-19T09:00", "missed"), ("2026-10-19T10:00", "missed")]
    assert sum(minutes(b) for b in ahead) == 120  # all two hours again, nothing assumed done
    assert app.do("item", id=essay)["item"]["remaining_min"] == 120


def test_counted_done_when_you_choose_it(app: App) -> None:
    essay = an_hour_at_nine(app)
    app.at("2026-10-19T10:30")
    (past,) = [b for b in planned(app, essay) if b["start"] == "2026-10-19T09:00"]
    assert past["state"] == "done"


def test_a_timed_block_gives_way_to_its_sitting(app: App) -> None:
    plan_again(app)
    essay = an_hour_at_nine(app)
    app.do("start", id=essay)
    app.at("2026-10-19T09:40").do("stop")
    app.at("2026-10-19T10:30")
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    assert [b["state"] for b in plan["blocks"] if b["item_id"] == essay and b["start"] == "2026-10-19T09:00"] == [
        "timed"
    ]
    assert [(s["start"], s["end"]) for s in plan["sessions"]] == [("2026-10-19T09:00", "2026-10-19T09:40")]


def test_i_did_it_counts_a_missed_block_with_its_joined_pieces(app: App) -> None:
    plan_again(app)
    essay = an_hour_at_nine(app)
    # A replan mid-block cuts it in two in the record; the calendar shows one block, 9 to 10.
    app.at("2026-10-19T09:30")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:30")
    (missed,) = [b for b in planned(app, essay) if b["start"] == "2026-10-19T09:00"]
    assert (missed["start"], missed["end"], missed["state"]) == ("2026-10-19T09:00", "2026-10-19T10:00", "missed")
    app.do("settle", block_key=missed["key"], status="done", until=missed["end"])
    (counted,) = [b for b in planned(app, essay) if b["start"] == "2026-10-19T09:00"]
    assert counted["state"] == "done"
    assert app.do("item", id=essay)["item"]["remaining_min"] == 60  # the whole hour counted, both pieces


def test_a_deleted_items_past_blocks_are_gone(app: App) -> None:
    essay = an_hour_at_nine(app)
    app.at("2026-10-19T10:30")
    app.do("drop", id=essay)
    assert [b["state"] for b in planned(app, essay)] == ["gone"]


def test_settling_yesterdays_missed_block(app: App) -> None:
    plan_again(app)
    essay = an_hour_at_nine(app)
    app.at("2026-10-20T08:00")
    replan(app.conn, app.now_utc)
    (missed,) = [b for b in planned(app, essay) if b["start"] == "2026-10-19T09:00"]
    app.do("settle", block_key=missed["key"], status="done", until=missed["end"])
    assert app.do("item", id=essay)["item"]["remaining_min"] == 60
    with pytest.raises(Exception, match="hasn't happened"):
        app.do("settle", block_key=f"T{essay}@2026-10-21T09:00", status="done")


def minutes(b: dict) -> int:
    h1, m1 = int(b["start"][11:13]), int(b["start"][14:16])
    h2, m2 = int(b["end"][11:13]), int(b["end"][14:16])
    day = 0 if b["end"][:10] == b["start"][:10] else 24 * 60
    return (h2 * 60 + m2 + day) - (h1 * 60 + m1)


def test_a_finished_items_timed_block_still_gives_way_to_the_sitting(app: App) -> None:
    essay = an_hour_at_nine(app)
    app.do("start", id=essay)
    app.at("2026-10-19T09:40").do("stop", done=True)
    app.at("2026-10-19T10:30")
    (block,) = [b for b in planned(app, essay) if b["start"] == "2026-10-19T09:00"]
    assert block["state"] == "timed"  # not drawn again beside its sitting
