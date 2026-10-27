"""Learned durations and the learned energy map through the registry (DESIGN §21.7)."""

from pathlib import Path

import pytest

from friday.commands.learned import learn_nightly
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from friday.planner.store import kv_get
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-10-01T09:00", horizon_days=3)
    app.do("area_add", name="CS")
    return app


def finish(app: App, title: str, minutes: int, day: int) -> None:
    """An item done on day `day` of October, logged at its real length."""
    item = app.do("add", text=f"{title} #CS ~1h")["item"]["id"]
    start = f"2026-10-{day:02d}T10:00"
    end_min = 10 * 60 + minutes
    app.do("log", id=item, start=start, end=f"2026-10-{day:02d}T{end_min // 60:02d}:{end_min % 60:02d}")
    app.do("done", id=item)


def test_new_items_use_learned_lengths_once_approved(app: App) -> None:
    for n in range(8):
        finish(app, f"problem set {n + 1}", 180, n + 1)
    app.at("2026-10-12T09:00")
    learn_nightly(app.conn, app.now_utc)
    assert kv_get(app.conn, "learned_durations")["model"]["n"] == 8
    before = app.do("add", text="problem set 9 #CS")["item"]["estimate"]["method"]
    assert before != "learned"  # suggest mode: waits for approval
    app.do("learn_module", module="durations", use=True)
    flexible = app.do("add", text="problem set 10 #CS")["item"]
    hard = app.do("add", text="problem set 11 #CS due fri 17:00")["item"]
    assert flexible["estimate"]["method"] == "learned" and abs(flexible["duration_min"] - 180) <= 30
    assert hard["duration_min"] > flexible["duration_min"]  # the cautious p80 for hard work


def test_a_sick_week_teaches_nothing(app: App) -> None:
    app.do("pace", name="Easy", for_days=14)
    for n in range(8):
        finish(app, f"problem set {n + 1}", 400, n + 1)
    app.at("2026-10-12T09:00")
    learn_nightly(app.conn, app.now_utc)
    assert kv_get(app.conn, "learned_durations") is None


def test_hours_where_planned_work_keeps_slipping_get_a_price_once_approved(app: App) -> None:
    for day in (5, 12, 19, 26):  # four Mondays: a half hour of the week needs 4 observations
        app.at(f"2026-10-{day:02d}T08:00")
        late = app.do("add", text="deep work @deep ~1h")["item"]["id"]
        early = app.do("add", text="morning work @deep ~1h")["item"]["id"]
        app.do("pin", id=late, start=f"2026-10-{day:02d}T15:00", kind="locked")
        app.do("pin", id=early, start=f"2026-10-{day:02d}T10:00", kind="locked")
        replan(app.conn, app.now_utc)  # 10:00 always happens; 15:00 never does
        app.at(f"2026-10-{day:02d}T18:00").do("review_submit", entries=[
            {"block_key": f"T{late}@2026-10-{day:02d}T15:00", "status": "not_done"},
            {"block_key": f"T{early}@2026-10-{day:02d}T10:00", "status": "done"},
        ])  # fmt: skip
        app.do("drop", id=late)
        app.do("done", id=early)
    app.at("2026-10-28T09:00")
    learn_nightly(app.conn, app.now_utc)
    learned = app.do("learning")["energy"]
    assert learned["worst"] and learned["worst"][0]["time"] in ("15:00", "15:30") and not learned["in_use"]
    weekday, cell = 0, 30  # Monday 15:00
    assert take_snapshot(app.conn, app.now_utc).settings["energy_map"][weekday][cell] == 0
    app.do("learn_module", module="energy", use=True)
    assert take_snapshot(app.conn, app.now_utc).settings["energy_map"][weekday][cell] > 0


def test_a_reset_forgets_both(app: App) -> None:
    for n in range(8):
        finish(app, f"problem set {n + 1}", 180, n + 1)
    app.at("2026-10-12T09:00")
    learn_nightly(app.conn, app.now_utc)
    app.do("learn_reset", module="durations")
    assert kv_get(app.conn, "learned_durations") is None


def test_the_learning_query_says_how_many_timed_things_lengths_wait_for(app: App) -> None:
    """Insights' "So far" (27 Oct): lengths are learned from five finished things you timed; done without a time
    teaches nothing."""
    assert app.do("learning")["progress"]["lengths"] == {"have": 0, "need": 5}
    for n in range(3):
        finish(app, f"problem set {n + 1}", 90, n + 1)
    untimed = app.do("add", text="essay #CS ~1h")["item"]["id"]
    app.do("done", id=untimed)
    assert app.do("learning")["progress"]["lengths"] == {"have": 3, "need": 5}
    assert app.do("learning")["progress"]["order"] == {"have": 0, "need": 4}
