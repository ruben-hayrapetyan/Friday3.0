"""Bugs an audit found in the commands and the planner (2026-10-25), each kept fixed: a day override that kept only
what it was last told, a merge that tied a copy to itself, a series stop that broke on a step or a timer and whose
undo lost the calendar link, the slider and an unreviewed block counted twice, a waiting plan that dropped the
day's past blocks, last week's work counted in this week's, yesterday's unreviewed work counting for nothing until
the night after, a shove after midnight on the day before, and a second other way picked unlike it was shown."""

from pathlib import Path

import pytest

from friday.planner.prepare import build_input
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def overrides(app: App) -> list[dict]:
    return app.table("day_overrides")


def test_day_override_keeps_the_days_other_overrides(app: App) -> None:
    app.do("day_override", date="2026-10-22", cap_hours=2.0)
    # triage's "Use the sleep margin" step, or Claude's "I'll go to bed late Thursday", sets one field only
    app.do("day_override", date="2026-10-22", margin_min=0)
    row = overrides(app)[0]
    assert row["margin_min"] == 0
    assert row["cap_hours"] == 2.0, row


def test_merging_two_copies_both_before_the_same_exam(app: App) -> None:
    exam = app.do("add", title="CS exam", when="fixed", start="2026-10-23T10:00", end="2026-10-23T12:00")["item"]["id"]
    a = app.do("add", title="Study guide", duration_min=60, before=[exam])["item"]["id"]
    b = app.do("add", title="Study guide", duration_min=60, before=[exam])["item"]["id"]
    groups = app.do("duplicates")["groups"]
    assert groups, "they are found as copies"
    app.do("duplicates_merge", groups=[{"keep": a, "drop": [b]}])  # raises sqlite3.IntegrityError if buggy


def test_stopping_a_series_whose_occurrence_holds_a_step(app: App) -> None:
    out = app.do("add", title="Weekly review", duration_min=60, every="day")
    series_id = out["series_id"]
    occ = app.conn.execute(
        "SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date LIMIT 1 OFFSET 1", [series_id]
    ).fetchone()["id"]
    app.do("add", title="Clear inbox", duration_min=15, parent_id=occ)
    app.do("series_stop", id=series_id)  # raises sqlite3.IntegrityError (FOREIGN KEY) if buggy


def test_slider_after_an_assumed_block_isnt_counted_twice(app: App) -> None:
    item = app.do("add", text="essay due wed ~2h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    print([(b["start"], b["end"]) for b in app.do("plan", start="2026-10-19T00:00")["blocks"] if b["item_id"] == item])
    app.at("2026-10-19T10:00")
    # the 09:00-10:00 block is unreviewed, so it counts as done (60 min)
    units = build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0)
    assert units == 4
    # now you say "about half done": the total is 60 of 120 minutes
    shown = app.do("progress", id=item, share=0.5)["item"]
    assert shown["remaining_min"] == 60
    units = build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0)
    assert units == 4, f"planner thinks {units * 15} min are done, the item shows 60"


def test_resolve_keeps_todays_past_blocks(app: App) -> None:
    from friday.planner.service import plan_snapshot, save_plan

    item = app.do("add", text="essay due wed ~2h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:00")
    before = build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0)
    assert before == 4
    # a solve that lands as "waiting" (a lock conflict): save it the way save_plan does for such a plan
    snapshot = take_snapshot(app.conn, app.now_utc)
    assembled = plan_snapshot(snapshot, warm=True)
    assembled.status = "waiting"
    save_plan(app.conn, snapshot, assembled, "replan")
    app.do("resolve")  # accept the waiting plan as it is
    after = build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0)
    review = [b["key"] for b in app.do("review")["blocks"]]
    assert after == 4 and review, f"progress {after * 15} min, review blocks {review}"


def test_stats_this_week_leaves_out_last_week(app: App) -> None:
    item = app.do("add", text="tidy ~1h")["item"]["id"]
    app.at("2026-10-18T20:00")  # Sunday evening, last week
    app.do("done", id=item)
    app.at("2026-10-19T09:00")  # Monday morning
    assert app.do("stats")["done_this_week"] == 0


def test_undoing_series_stop_brings_back_the_calendar_link(app: App) -> None:
    from friday.planner.store import event_links

    source = app.conn.execute("INSERT INTO sources (user_id, kind, name) VALUES (1, 'gcal', 'School')").lastrowid
    raw = app.conn.execute(
        "INSERT INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, content, status) "
        "VALUES (1, ?, 'chem_1', '2026-10-19T12:00Z', 'h', '{}', 'extracted')",
        [source],
    ).lastrowid
    lecture = '{"title": "CHEM", "preset": "Class", "start": "2026-10-20T12:20", "end": "2026-10-20T13:10"}'
    app.conn.execute(
        "INSERT INTO suggestions (user_id, raw_input_id, batch, command, input, quotes, created_utc) "
        "VALUES (1, ?, 'repeat:chem', 'add', ?, '{}', '2026-10-19T12:00Z')",
        [raw, lecture],
    )
    app.do("repeats_import", repeats=[{"batch": "repeat:chem"}])
    item = app.conn.execute("SELECT id, series_id FROM items WHERE title = 'CHEM'").fetchone()
    assert item["id"] in event_links(app.conn)
    app.do("series_stop", id=item["series_id"])
    stop_id = app.results[-1].command_id
    app.do("undo", command_id=stop_id)
    assert app.conn.execute("SELECT 1 FROM items WHERE id = ?", [item["id"]]).fetchone(), "the item is back"
    assert item["id"] in event_links(app.conn), app.table("suggestions")


def test_series_stop_with_a_running_timer_on_todays_occurrence(app: App) -> None:
    out = app.do("add", title="Practice piano", duration_min=60, every="day")
    occ = app.conn.execute(
        "SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date LIMIT 1", [out["series_id"]]
    ).fetchone()["id"]
    app.do("start", id=occ)
    app.at("2026-10-19T09:40")
    app.do("series_stop", id=out["series_id"])
    stop_id = app.results[-1].command_id
    app.do("undo", command_id=stop_id)
    assert app.table("timer"), "the running timer (40 min so far) is gone for good"


def test_nightly_close_day_closes_the_day_that_just_ended(app: App) -> None:
    item = app.do("add", text="essay due fri ~3h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0) >= 4  # assumed today
    app.at("2026-10-20T03:30")  # the nightly job, at its default time (jobs.nightly_replan_at)
    print(app.do("close_day")["message"])
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T09:00")  # Tuesday morning: Monday wasn't reviewed
    units = build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item, 0)
    assert units >= 4, f"Monday's assumed hour counts for nothing on Tuesday ({units} units)"


def test_shove_a_time_range_after_midnight_means_the_coming_day(app: App) -> None:
    app.at("2026-10-20T01:00")  # 1am Tuesday, before the 04:00 day start
    out = app.do("shove", range="12:00-13:30", decision="shove_anyway")
    item = app.do("item", id=out["created"][0])["item"]
    assert item["start"] == "2026-10-20T12:00", (item["start"], out["message"])


def test_a_second_way_picked_in_the_same_week_keeps_the_first_ones_weights(app: App) -> None:
    app.do("other_way_pick", weights={"energy": 2.0, "buffer": 0.5}, seed=2, rule_totals={})
    app.do("other_way_pick", weights={"energy": 3.0}, seed=3, rule_totals={})
    way = next(r for r in app.table("kv") if r["key"] == "other_way")
    import json

    kept = json.loads(way["value"])
    assert kept["weights"] == {"energy": 6.0, "buffer": 0.5} and kept["seed"] == 5  # as the ways were made, on top


def test_a_shove_into_the_night_runs_past_midnight(app: App) -> None:
    out = app.do("shove", range="11pm-12am 2026-10-20", decision="shove_anyway")
    item = app.do("item", id=out["created"][0])["item"]
    assert (item["start"], item["end"]) == ("2026-10-20T23:00", "2026-10-21T00:00")
    with pytest.raises(Exception, match="isn't a time range"):
        app.do("shove", range="13:30-12:00", decision="shove_anyway")  # backwards, not a night
