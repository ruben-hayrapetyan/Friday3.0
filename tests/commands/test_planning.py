"""Progress, the timer, the review, pins, paces and the queries that read the plan."""

import pickle
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.service import plan_snapshot, replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def planned(app: App, text: str) -> int:
    item_id = app.do("add", text=text)["item"]["id"]
    replan(app.conn, app.now_utc)
    return item_id


def progress_units(app: App, item_id: int) -> int:
    return build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(item_id, 0)


def test_a_slider_sets_the_total_and_later_work_adds_to_it(app: App) -> None:
    item_id = app.do("add", text="essay due wed ~4h")["item"]["id"]
    app.do("log", id=item_id, start="2026-10-19T07:45", end="2026-10-19T08:45")
    assert app.do("progress", id=item_id, share=0.5)["item"]["remaining_min"] == 120
    app.do("log", id=item_id, start="2026-10-19T08:45", end="2026-10-19T09:00")
    assert app.do("item", id=item_id)["item"]["remaining_min"] == 105


def test_the_last_quarter_hour_of_an_item_is_planned_before_its_due(app: App) -> None:
    item_id = app.do("add", text="essay due tue 17:00 ~1h")["item"]["id"]  # Assignment: 30 min chunks at least
    app.do("log", id=item_id, start="2026-10-19T07:45", end="2026-10-19T08:30")
    replan(app.conn, app.now_utc)
    blocks = [b for b in app.do("plan")["blocks"] if b["item_id"] == item_id]
    assert [(b["start"], b["end"]) for b in blocks] and all(b["end"] <= "2026-10-20T17:00" for b in blocks)


def test_starting_a_timer_stops_the_running_one_and_makes_a_tentative_item_real(app: App) -> None:
    first = app.do("add", text="tidy ~1h")["item"]["id"]
    maybe = app.do("add", text="store run maybe sat-sun ~1h")["item"]["id"]
    app.do("start", id=first)
    app.at("2026-10-19T09:20")
    app.do("start", id=maybe)
    assert [(p["item_id"], p["minutes"], p["source"]) for p in app.table("progress")] == [(first, 20, "timer")]
    assert app.do("item", id=maybe)["item"]["certainty"] == "planned"
    assert app.do("status")["timer"]["item_id"] == maybe


def test_stop_with_done_completes_the_item(app: App) -> None:
    item_id = app.do("add", text="tidy ~1h")["item"]["id"]
    app.do("start", id=item_id)
    app.at("2026-10-19T09:50")
    assert "marked it done" in app.do("stop", done=True)["message"]
    assert app.do("item", id=item_id)["item"]["status"] == "done"


def test_logging_something_that_happened_makes_a_fixed_item(app: App) -> None:
    item = app.do("log", title="coffee with Sam", start="2026-10-19T07:45", end="2026-10-19T08:30")["item"]
    assert (item["when"], item["start"], item["end"]) == ("fixed", "2026-10-19T07:45", "2026-10-19T08:30")


def test_the_review_writes_done_partial_and_not_done_and_replaces_assumptions(app: App) -> None:
    a = planned(app, "essay due tue ~1h")
    app.do("pin", id=a, start="2026-10-19T09:00", kind="locked")
    b = app.do("add", text="email ~1h")["item"]["id"]
    app.do("pin", id=b, start="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert progress_units(app, a) == 4 and progress_units(app, b) == 4  # assumed, not written
    sheet = app.do("review")
    assert [blk["key"] for blk in sheet["blocks"]] == [f"T{a}@2026-10-19T09:00", f"T{b}@2026-10-19T10:00"]
    app.do("review_submit", entries=[{"block_key": f"T{a}@2026-10-19T09:00", "status": "partial", "share": 0.5}])
    assert progress_units(app, a) == 2 and progress_units(app, b) == 4  # b wasn't mentioned: done by default
    assert app.do("review")["reviewed"]


def test_a_block_carried_across_a_replan_stays_one_block_with_its_key(app: App) -> None:
    item = planned(app, "essay due tue 17:00 ~2h")
    app.do("pin", id=item, start="2026-10-19T09:00", end="2026-10-19T11:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T09:07")
    replan(app.conn, app.now_utc)
    spans = [(b["key"], b["end"]) for b in app.do("plan", start="2026-10-19T00:00")["blocks"] if b["item_id"] == item]
    assert spans == [(f"T{item}@2026-10-19T09:00", "2026-10-19T11:00")]


def test_a_timed_block_is_recorded_once_not_again_by_the_review(app: App) -> None:
    essay = planned(app, "essay due tue ~2h")
    app.do("pin", id=essay, start="2026-10-19T09:00", end="2026-10-19T11:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T10:30")
    app.do("stop")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    # The session stands for the 09:00 block; the half hour replanned after it is still the review's to settle.
    assert [b["key"] for b in app.do("review")["blocks"]] == [f"T{essay}@2026-10-19T10:30"]
    app.do("review_submit")
    assert app.do("item", id=essay)["item"]["done_min"] == 90 + 30


def test_a_finished_looking_item_is_listed_for_confirmation(app: App) -> None:
    item_id = app.do("add", text="tidy ~1h")["item"]["id"]
    app.do("log", id=item_id, start="2026-10-19T07:45", end="2026-10-19T08:45")
    assert [i["id"] for i in app.do("review")["finished"]] == [item_id]


def test_a_pin_places_the_item_and_unpin_lets_friday_decide(app: App) -> None:
    item_id = app.do("add", text="email ~1h")["item"]["id"]
    app.do("pin", id=item_id, start="2026-10-19T15:00", kind="locked")
    replan(app.conn, app.now_utc)
    blocks = [b for b in app.do("plan")["blocks"] if b["item_id"] == item_id]
    assert [(b["start"], b["end"], b["pinned"]) for b in blocks] == [("2026-10-19T15:00", "2026-10-19T16:00", "locked")]
    app.do("unpin", id=item_id)
    assert app.table("pins") == []


def test_a_new_pin_replaces_the_ones_it_overlaps_and_the_one_it_moves_from(app: App) -> None:
    item_id = app.do("add", text="essay ~3h split")["item"]["id"]
    for start, end in (("2026-10-19T10:00", "2026-10-19T11:00"), ("2026-10-19T14:00", "2026-10-19T15:00")):
        app.do("pin", id=item_id, start=start, end=end)
    app.do("pin", id=item_id, start="2026-10-19T10:15", end="2026-10-19T11:15")  # a nudge
    app.do("pin", id=item_id, start="2026-10-20T09:00", end="2026-10-20T10:00",
           from_start="2026-10-19T14:00", from_end="2026-10-19T15:00")  # a drag  # fmt: skip
    assert sorted((p["start_utc"], p["end_utc"]) for p in app.table("pins")) == [
        ("2026-10-19T14:15Z", "2026-10-19T15:15Z"),
        ("2026-10-20T13:00Z", "2026-10-20T14:00Z"),
    ]


def test_now_shows_the_current_block_and_safe_swaps(app: App) -> None:
    first = planned(app, "essay due tue 17:00 ~2h")
    other = app.do("add", text="email ~30m")["item"]["id"]
    replan(app.conn, app.now_utc)
    shown = app.do("now")
    assert shown["current_source"] == "block" and shown["current"]["item_id"] in (first, other)
    waiting = other if shown["current"]["item_id"] == first else first
    assert waiting in [s["item_id"] for s in shown["swaps"]]


def test_why_explains_a_block_and_why_not_names_the_wall(app: App) -> None:
    item_id = planned(app, "essay due mon 12:00 ~1h")
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["item_id"] == item_id)
    assert app.do("why", key=key)["sentence"].startswith("Due Mon 19 Oct 12pm; it could all start")
    answer = app.do("why_not", key=key, start="2026-10-19T13:00")
    assert answer["wall"] and "due" in answer["wall"].lower()


def test_a_rules_list_can_be_previewed_with_changed_params_and_nothing_is_saved(app: App) -> None:
    item_id = planned(app, "essay ~2h")
    rules = app.do("settings")["rules"]
    assert not app.do("preview_weights", rules=rules)["removed"]
    forbid_all_day = {"start": "00:00", "end": "23:59", "price": "forbid"}
    no_work = {"type": "time_preference", "name": "no_work", "params": forbid_all_day}
    removed = app.do("preview_weights", rules=[*rules, no_work])["removed"]
    assert {b["item_id"] for b in removed} == {item_id}
    assert app.do("settings")["rules"] == rules
    with pytest.raises(FieldError, match="rules"):
        app.do("preview_weights", rules=[*rules, {"type": "daily_load", "name": "x", "params": {"threshold": "lots"}}])


def test_changes_lists_moves_and_the_commands_behind_them(app: App) -> None:
    item_id = planned(app, "email ~1h")
    app.do("pin", id=item_id, start="2026-10-19T15:00", kind="locked")
    replan(app.conn, app.now_utc)
    changes = app.do("changes")
    assert [m["item_id"] for m in changes["moved"]] == [item_id]
    assert [(i["actor"], i["command"]) for i in changes["inputs"]] == [("you", "pin")]


def test_triage_offers_ways_to_make_late_work_less_late(app: App) -> None:
    app.do("add", title="busy", when="fixed", start="2026-10-19T12:00", end="2026-10-20T04:00")
    app.do("add", text="essay due mon 12:00 ~4h !5")
    found = app.do("triage")
    late = found["late"]["essay"]  # the last hour lands the next morning, 20.5 h after the due
    assert late == 20.5 and found["options"][0]["late_hours_saved"] == late


def test_every_triage_option_runs_as_ordinary_commands(app: App) -> None:
    app.do("add", title="busy", when="fixed", start="2026-10-19T12:00", end="2026-10-20T04:00")
    app.do("add", text="essay due mon 12:00 ~4h !5")
    app.do("add", title="lunch", preset="Routine", release="2026-10-19T09:00", due="2026-10-19T12:00",
           min_min=20, ideal_min=30, max_min=45)  # fmt: skip
    chore = app.do("add", text="tidy ~1h")["item"]["id"]
    app.do("pin", id=chore, start="2026-10-19T10:00", kind="locked")
    options = app.do("triage")["options"]
    assert {o["action"].split()[0] for o in options} == {"Move", "Drop", "Make"}
    for option in options:
        for step in option["steps"]:
            assert app.full(step["command"], payload=step["input"], preview=True).preview


def test_pace_save_and_delete_follow_their_rules(app: App) -> None:
    assert "capacity 0.8" in app.do("pace_save", name="Gentle", capacity=0.8)["message"]
    assert app.do("paces")["paces"]["Gentle"]["capacity"] == 0.8
    with pytest.raises(FieldError, match="default"):
        app.do("pace_delete", name="Normal")
    app.do("pace", name="gentle")
    with pytest.raises(FieldError, match="in use"):
        app.do("pace_delete", name="Gentle")


def test_custom_dials_start_from_the_dials_in_effect(app: App) -> None:
    app.do("pace", name="easy")
    out = app.do("pace", growth=0.5, for_days=2)
    assert out["label"] == "Custom" and out["dials"]["capacity"] == 0.6 and out["end_date"] == "2026-10-20"


def test_a_day_override_moves_that_nights_bedtime(app: App) -> None:
    app.do("day_override", date="2026-10-19", bedtime="21:00")
    night = build_input(take_snapshot(app.conn, app.now_utc))
    assert night.day_overrides
    problem = build_problem(night)
    tonight = problem.nights[problem.grid.slots[0].date]
    assert tonight.bedtime_utc == app.now_utc + 12 * 60  # 21:00 is twelve hours after 09:00


def test_a_saved_snapshot_replans_to_the_same_plan(app: App) -> None:
    app.do("add", text="essay due tue 17:00 ~3h")
    app.do("add", text="email ~30m")
    snapshot = take_snapshot(app.conn, app.now_utc)
    again = pickle.loads(pickle.dumps(snapshot))
    assert plan_snapshot(snapshot, warm=False).blocks == plan_snapshot(again, warm=False).blocks


def test_an_empty_list_still_plans(app: App) -> None:
    assert replan(app.conn, app.now_utc) is not None
    assert app.do("plan")["blocks"] == []


def test_plan_changing_commands_return_ghosts_at_once(app: App) -> None:
    planned(app, "email ~1h")
    ghosts = app.full("add", payload={"text": "essay due mon 13:00 ~1h"}).provisional
    assert ghosts is not None and any(g.title == "essay" and g.end <= "2026-10-19T13:00" for g in ghosts)


def test_quick_add_warns_when_your_estimates_run_long(app: App) -> None:
    for n in range(5):
        item_id = app.do("add", text=f"PS{n} #cs ~1h")["item"]["id"]
        app.do("done", id=item_id, actual_min=90)
    warnings = app.do("add", text="PS9 #cs ~1h")["warnings"]
    assert "your estimates for cs run ×1.50: maybe 90 min" in warnings


def test_kind_order_doubles_the_first_kinds_importance_and_leaves_the_rest() -> None:
    from types import SimpleNamespace

    from friday.planner.build import importance

    order = ("Exam prep", "Assignment", "Reading")

    def of(preset: str) -> float:
        return importance(SimpleNamespace(preset=preset, importance=3), order)  # type: ignore[arg-type]

    assert (of("Exam prep"), of("Assignment"), of("Reading"), of("Chore")) == (6, 4.5, 3, 3)


def test_short_term_first_puts_long_term_work_last() -> None:
    from types import SimpleNamespace

    from friday.planner.build import importance

    def of(long_term: bool, first: bool) -> float:
        item = SimpleNamespace(preset="Reading", importance=4, long_term=long_term)
        return importance(item, ("Assignment", "Reading"), first)  # type: ignore[arg-type]

    assert (of(False, True), of(True, True), of(True, False)) == (4, 1, 4)


def test_a_rule_change_lets_the_next_replan_move_things_once(app: App) -> None:
    app.do("add", text="essay ~3h due fri")
    replan(app.conn, app.now_utc)
    assert build_input(take_snapshot(app.conn, app.now_utc)).minimize_changes_scale == 1.0
    app.do("rule_add", text="avoid work after 9pm")
    assert build_input(take_snapshot(app.conn, app.now_utc)).minimize_changes_scale == 0.0
    replan(app.conn, app.now_utc)
    assert build_input(take_snapshot(app.conn, app.now_utc)).minimize_changes_scale == 1.0


def test_a_pace_switch_loosens_the_next_replan_by_its_setting(app: App) -> None:
    app.do("pace", name="Easy")
    assert build_input(take_snapshot(app.conn, app.now_utc)).minimize_changes_scale == 0.2


def test_ghosts_show_only_what_the_command_changed(app: App) -> None:
    app.do("add", text="term paper ~20h due 11-30")  # far off: the plan places this week's share, not all of it
    replan(app.conn, app.now_utc)
    saved = {(b["item_id"], b["start"]) for b in app.do("plan")["blocks"]}
    ghosts = app.full("add", payload={"text": "email prof ~30m"}).provisional
    new = {g.title for g in ghosts or [] if (g.item_id, g.start) not in saved}
    assert new == {"email prof"}  # the paper's other 15 hours weren't painted into this week


def test_starting_a_task_in_a_short_gap_times_it_and_leaves_the_plan_whole(app: App) -> None:
    app.at("2026-10-19T09:22")
    app.do("add", text="lecture at mon 10:00 for 1h /class")
    mastering = planned(app, "mastering physics one-sitting ~2h due fri")
    before = [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == mastering]
    app.do("start", id=mastering)
    shown = app.do("now")
    assert shown["current"]["item_id"] == mastering and shown["current_source"] == "timer"
    assert shown["current"]["start"] == "2026-10-19T09:22" and shown["current"]["end"] <= "2026-10-19T10:00"
    assert [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == mastering] == before
    assert app.do("status")["timer"]["elapsed_s"] == 0
    app.at("2026-10-19T09:52")
    assert app.do("status")["timer"]["elapsed_s"] == 30 * 60
    assert "30 min" in app.do("stop")["message"]


def test_diagnose_reads_the_last_hours_back_in_order(app: App) -> None:
    essay = planned(app, "essay ~2h due fri")
    app.at("2026-10-19T09:30").do("report", where="plan", message="the calendar went blank")
    found = app.at("2026-10-19T10:00").do("diagnose", hours=2)
    assert [h["kind"] for h in found][-2:] == ["plan", "report"]  # after the fixture's own setup commands
    assert any(h["kind"] == "command" and "essay ~2h due fri" in h["summary"] for h in found)
    assert found[-2]["summary"].startswith("P") and "the calendar went blank" in found[-1]["summary"] and essay
