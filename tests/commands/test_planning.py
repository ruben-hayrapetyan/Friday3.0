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


def test_lunch_keeps_its_travel_time_clear_on_both_sides(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    lunch = app.do("add", text="Lunch tomorrow 11:30am-2:30pm 15m")["item"]["id"]
    app.do("edit", id=lunch, buffer_before_min=15, buffer_after_min=15)
    app.do("add", text="essay ~3h", release="2026-10-20T11:00", due="2026-10-20T15:00")
    app.do("replan")
    day = [b for b in app.do("plan")["blocks"] if b["start"].startswith("2026-10-20")]
    ((eat_from, eat_to),) = [(_minutes(b["start"][11:]), _minutes(b["end"][11:])) for b in day if b["title"] == "Lunch"]
    essay = [(_minutes(b["start"][11:]), _minutes(b["end"][11:])) for b in day if b["title"] == "essay"]
    assert sum(b - a for a, b in essay) == 180
    assert all(b <= eat_from - 15 or a >= eat_to + 15 for a, b in essay), day  # to get there, and back


def _minutes(clock: str) -> int:
    return int(clock[:2]) * 60 + int(clock[3:5])


def test_a_weekly_pace_from_a_rule_sets_those_days_every_week(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    out = app.do("rule_add", text="go easier on saturday and go harder on sunday")
    assert out["message"] == "Every week: Easy on Saturdays, Push on Sundays"
    assert app.do("settings")["pace"]["weekly"] == {"sat": "Easy", "sun": "Push"}
    days = {d["date"]: d["pace"] for d in app.do("calendar", days=14)["days"]}
    assert days["2026-10-24"] == days["2026-10-31"] == "Easy" and days["2026-10-25"] == "Push"
    assert days["2026-10-23"] is None  # a Friday keeps the default
    assert not any(r["name"].startswith("you:") for r in app.do("rules"))  # a setting, not a planner rule
    app.do("rule_add", text="saturdays are normal")
    assert app.do("settings")["pace"]["weekly"] == {"sun": "Push"}


def test_a_quarter_hour_lunch_fills_a_half_hour_slot_past_the_fine_days(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="time", value={"timezone": "America/New_York", "horizon_days": 7, "fine_days": 2})
    app.do("add", text="Lunch every day 11:30am-2:30pm 15m")
    app.do("replan")  # a 15-minute maximum in 30-minute slots broke W4, and the whole plan failed
    lunches = [b for b in app.do("plan")["blocks"] if b["title"] == "Lunch"]
    later = [b for b in lunches if b["start"] >= "2026-10-22"]
    assert later and all(_minutes(b["end"][11:]) - _minutes(b["start"][11:]) == 30 for b in later)
    assert all(_minutes(b["end"][11:]) - _minutes(b["start"][11:]) == 15 for b in lunches if b["start"] < "2026-10-21")


def test_asking_for_deadlines_first_says_it_is_on_and_switches_it_back_on(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    out = app.do("rule_add", text="push when necessary for work not to be late")
    assert out["message"].startswith("Already on")
    assert not any(r["name"].startswith("you:") for r in app.do("rules"))  # nothing added
    app.do("rule_set", name="late_tasks", enabled=False)
    assert app.do("rule_add", text="don't let work be late")["message"].startswith("Deadlines come first is back on")
    assert all(r["enabled"] for r in app.do("rules") if r["name"] in ("late_work", "late_tasks"))


def test_an_optional_event_gives_way_only_when_work_would_be_late(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Gym", when="fixed", start="2026-10-20T08:00", end="2026-10-20T12:00")
    app.do("add", text="essay ~2h", release="2026-10-20T08:00", due="2026-10-20T12:00")
    app.do("replan")
    assert app.do("status")["late"]  # the gym walls off the only time there is
    out = app.do("rule_add", text="gym is optional")
    assert out["message"].startswith("Added: Gym is optional")
    app.do("replan")
    essay = [b for b in app.do("plan")["blocks"] if b["title"] == "essay"]
    assert essay and all("2026-10-20T08:00" <= b["start"] < "2026-10-20T12:00" for b in essay)
    assert not app.do("status")["late"]
    assert "Skip Gym on Tue at 8am: essay needs the time" in app.do("status")["notices"]


def test_an_optional_event_keeps_its_time_when_the_work_fits_elsewhere(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Gym", when="fixed", start="2026-10-20T08:00", end="2026-10-20T12:00")
    app.do("add", text="essay ~2h due tue 12pm")
    app.do("rule_add", text="gym is optional")
    app.do("replan")
    essay = [b for b in app.do("plan")["blocks"] if b["title"] == "essay"]
    assert essay and not any("2026-10-20T07:45" <= b["start"] < "2026-10-20T12:15" for b in essay)


def test_an_event_you_go_to_only_when_ahead_gives_its_time_before_a_late_night(tmp_path: Path) -> None:
    # 3 hours from 6pm: either the club's 6 to 8pm, or work until 11pm. Optional keeps the club and works late; only
    # when ahead skips the club, so nothing runs past 10pm.
    def evening(rule: str) -> list[dict]:
        folder = tmp_path / rule.split()[-1]
        folder.mkdir()
        app = new_app(folder)
        app.do("add", title="Climbing Club", when="fixed", start="2026-10-20T18:00", end="2026-10-20T20:00")
        app.do("add", text="essay ~3h", release="2026-10-20T18:00", due="2026-10-21T00:30")
        app.do("rule_add", text=rule)
        app.do("replan")
        return [b for b in app.do("plan")["blocks"] if b["title"] == "essay"], app.do("status")["notices"]

    kept, _ = evening("climbing club is optional")
    assert kept and not any(b["start"] < "2026-10-20T20:00" for b in kept)
    taken, notices = evening("climbing club only if i'm ahead")
    assert any(b["start"] < "2026-10-20T20:00" for b in taken)
    assert all(b["end"] <= "2026-10-20T22:00" for b in taken)
    assert any(n.startswith("Skip Climbing Club on Tue at 6pm: essay needs the time") for n in notices)


def test_an_event_you_go_to_only_when_ahead_says_go_when_the_work_fits(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Climbing Club", when="fixed", start="2026-10-20T18:00", end="2026-10-20T20:00")
    app.do("add", title="Climbing Club", when="fixed", start="2026-11-03T18:00", end="2026-11-03T20:00")
    app.do("add", text="essay ~1h due thu 5pm")
    app.do("rule_add", text="climbing club only if i'm ahead")
    app.do("replan")
    essay = [b for b in app.do("plan")["blocks"] if b["title"] == "essay"]
    assert essay and not any("2026-10-20T18:00" <= b["start"] < "2026-10-20T20:00" for b in essay)
    notices = app.do("status")["notices"]
    assert "Go to Climbing Club on Tue at 6pm: you’re ahead" in notices
    assert not any("Nov" in n or n.count("Go to") > 1 for n in notices)  # only the coming week's is said


def test_no_work_the_night_before_an_early_event(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Climbing Club", when="fixed", start="2026-10-21T06:00", end="2026-10-21T08:00")
    said = "if i am going to climbing club the next day then the previous day must end at 10:00"
    assert app.do("rule_read", text=said)["strength"] == "Always"  # "must": what the Rules page adds it with
    app.do("rule_add", text=said, strength="Always")
    app.do("add", text="essay ~2h")
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    essay = next(i for i in problem.items.values() if i.title == "essay")
    late_tuesday = [
        s for s, slot in enumerate(problem.grid.slots) if str(slot.date) == "2026-10-20" and slot.day_minute >= 22 * 60
    ]
    late_monday = [
        s for s, slot in enumerate(problem.grid.slots) if str(slot.date) == "2026-10-19" and slot.day_minute >= 22 * 60
    ]
    assert late_tuesday and not set(late_tuesday) & essay.allowed_set  # Tuesday night, before Wednesday's club
    assert set(late_monday) & essay.allowed_set  # Monday night is as usual


def test_an_evening_kept_free_until_midnight_keeps_the_night_after_it_too(tmp_path: Path) -> None:
    from friday.engine.rules import BuildContext

    app = new_app(tmp_path)
    app.do("add", text="read a paper ~1h")
    app.do("rule_add", text="keep friday from 8pm to 11:59pm free")
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    rule = next(r for r in problem.rules if r.type == "reserve" and r.name.startswith("you:"))  # Fridays only
    slots = {v[2] for m in rule.measures(BuildContext(problem)) for v in m.expr.terms if v[0] == "x"}
    assert any(problem.grid.slots[s].day_minute >= 24 * 60 for s in slots)  # 12am to bedtime on Friday night too


def test_short_term_first_makes_long_term_work_wait_for_this_weeks_short_term_work(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~2h due wed")["item"]["id"]
    app.do("add", text="thesis ~2h due dec 20")  # short term, but not due this week: doesn't hold anything up
    book = app.do("add", text="read a book ~2h")["item"]["id"]
    app.do("edit", id=book, long_term=True)
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert not problem.items[f"item:{book}"].depends_on
    app.do("settings_set", key="short_term_first", value=True)
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert [d.key for d in problem.items[f"item:{book}"].depends_on] == [f"item:{essay}"]
    app.do("replan")
    blocks = app.do("plan")["blocks"]
    essay_end = max(b["end"] for b in blocks if b["item_id"] == essay)
    assert all(b["start"] >= essay_end for b in blocks if b["item_id"] == book)


def test_a_bedtime_after_the_day_starts_is_that_night_not_that_morning(tmp_path: Path) -> None:
    # Bed at 4:30am, up at noon: the night runs 4:30am to noon the next morning, not from 4:30 this morning, which
    # left no waking hour to plan in.
    app = new_app(tmp_path, now="2026-10-19T12:00")
    late = {"bedtime": "04:30", "wake": "12:00", "margin_min": 60}
    app.do("settings_set", key="sleep", value=dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), late))
    essay = app.do("add", title="Essay", duration_min=4 * 60, due="2026-10-21T23:59")["item"]["id"]
    app.do("replan")
    blocks = app.do("item", id=essay)["blocks"]
    assert (
        sum(_minutes(b["end"][11:]) - _minutes(b["start"][11:]) for b in blocks if b["end"][:10] == b["start"][:10]) > 0
    )
    assert not app.do("status")["late"]
    assert all(not ("04:30" <= b["start"][11:] < "12:00") for b in blocks)  # none in the night


def test_a_lock_over_an_event_says_why_it_wasnt_kept(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", title="Essay", duration_min=120, due="2026-10-22T23:59")["item"]["id"]
    app.do("add", title="Seminar", when="fixed", start="2026-10-20T14:00", end="2026-10-20T16:00")
    app.do("pin", id=essay, start="2026-10-20T14:00", end="2026-10-20T16:00", kind="locked")
    app.do("replan")
    said = "Your lock on Essay (Tue 2pm) is during Seminar, so Friday planned it elsewhere: move the lock, or make "
    assert said + "Seminar optional" in app.do("status")["notices"]
    assert not any("2026-10-20T14:00" <= b["start"] < "2026-10-20T16:00" for b in app.do("item", id=essay)["blocks"])


def test_travel_time_around_an_event_by_name(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    out = app.do("rule_add", text="30 minutes before and after gym")
    assert out["message"] == "Added: 30 min before and after Gym"
    app.do("add", title="Gym", when="fixed", start="2026-10-19T12:00", end="2026-10-19T13:00")
    app.do("add", title="Essay", duration_min=10 * 60, due="2026-10-19T23:59")  # the day fills up to the gym's sides
    app.do("replan")
    near = [
        b
        for b in app.do("plan", start="2026-10-19T00:00", end="2026-10-20T04:00")["blocks"]
        if b["title"] == "Essay" and b["start"] < "2026-10-19T13:30" and b["end"] > "2026-10-19T11:30"
    ]
    assert near == []  # 11:30 to 1:30 kept: the gym and half an hour each side
    assert not any("is off" in n for n in app.do("status")["notices"])  # not taken for an unknown rule


def test_the_night_before_holds_only_when_you_go(tmp_path: Path) -> None:
    # Climbing club only when you're ahead, and no work after 10pm the night before it. Every other hour is taken, so
    # a 3-hour essay due when the Wednesday evening club ends needs the club's time and Tuesday night: the plan gives
    # the club's time to the essay, so you aren't going, and the night before is free to work.
    app = new_app(tmp_path)
    app.do("add", title="Climbing Club", when="fixed", start="2026-10-21T18:00", end="2026-10-21T20:00")
    app.do("rule_add", text="climbing club only if i'm ahead")
    app.do("rule_add", text="no work after 10pm the night before climbing club", strength="Always")
    for start, end in (("2026-10-19T07:00", "2026-10-20T01:00"), ("2026-10-20T07:00", "2026-10-20T22:00"),
                       ("2026-10-21T07:00", "2026-10-21T18:00")):  # fmt: skip
        app.do("add", title="Lab", when="fixed", start=start, end=end)
    app.do("add", title="Essay", duration_min=3 * 60, due="2026-10-21T20:00")
    app.do("replan")
    blocks = [
        b for b in app.do("plan", start="2026-10-19T00:00", end="2026-10-22T04:00")["blocks"] if b["title"] == "Essay"
    ]
    assert any("2026-10-21T18:00" <= b["start"] < "2026-10-21T20:00" for b in blocks)  # the club's time, used
    assert any(b["end"] > "2026-10-20T22:00" and b["start"] < "2026-10-21T04:00" for b in blocks)  # the night, too
    assert not app.do("status")["late"]


def test_the_night_before_holds_when_you_go(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Climbing Club", when="fixed", start="2026-10-21T06:00", end="2026-10-21T08:00")
    app.do("rule_add", text="no work after 10pm the night before climbing club", strength="Always")
    app.do("add", title="Essay", duration_min=10 * 60, due="2026-10-21T12:00")
    app.do("replan")
    blocks = [
        b for b in app.do("plan", start="2026-10-19T00:00", end="2026-10-22T00:00")["blocks"] if b["title"] == "Essay"
    ]
    assert not any(b["end"] > "2026-10-20T22:00" and b["start"] < "2026-10-21T04:00" for b in blocks)


def test_late_work_takes_climbing_club_before_the_gym(tmp_path: Path) -> None:
    # Gym is optional, climbing club only when you're ahead: when work would be late, the club's evening goes first
    # (its price is a preference) and the gym's morning only when the club isn't enough (a wellbeing cost). With one
    # rule making both optional, the plan took the gym's morning first.
    def tuesday(hours: int) -> list[dict]:
        folder = tmp_path / str(hours)
        folder.mkdir()
        app = new_app(folder)
        app.do("add", title="Gym", when="fixed", start="2026-10-20T08:00", end="2026-10-20T10:00")
        app.do("add", title="Climbing Club", when="fixed", start="2026-10-20T18:00", end="2026-10-20T20:00")
        for start, end in (("2026-10-19T09:00", "2026-10-20T08:00"), ("2026-10-20T10:00", "2026-10-20T18:00"),
                           ("2026-10-20T20:00", "2026-10-21T02:00")):  # fmt: skip
            app.do("add", title="Lab", when="fixed", start=start, end=end)
        app.do("rule_add", text="gym is optional")
        app.do("rule_add", text="climbing club only if i'm ahead")
        app.do("add", title="Essay", duration_min=hours * 60, due="2026-10-21T02:00")
        app.do("replan")
        assert not app.do("status")["late"]
        return [
            b
            for b in app.do("plan", start="2026-10-19T00:00", end="2026-10-21T04:00")["blocks"]
            if b["title"] == "Essay"
        ]

    two = tuesday(2)
    assert two and all("2026-10-20T18:00" <= b["start"] < "2026-10-20T20:00" for b in two)  # the club's, not the gym's
    four = tuesday(4)
    assert any(b["start"] < "2026-10-20T10:00" for b in four) and any(b["start"] >= "2026-10-20T18:00" for b in four)


def test_exam_prep_as_close_to_the_exam_as_possible(tmp_path: Path) -> None:
    # A quiz on Friday at 1:25pm and an interview at 10am, prep for each due at it: with no rule the prep is spread
    # through the week; as close as possible, it ends right before each; a day of buffer for the quiz, a day before.
    def prep(rules: list[str]) -> dict[str, list[dict]]:
        folder = tmp_path / str(len(list(tmp_path.iterdir())))
        folder.mkdir()
        app = new_app(folder)
        quiz = app.do("add", title="Math 1920 Quiz 3", when="fixed", start="2026-10-23T13:25", end="2026-10-23T14:15",
                      event_kind="exam")["item"]["id"]  # fmt: skip
        talk = app.do("add", title="KelAI interview", when="fixed", start="2026-10-23T10:00", end="2026-10-23T11:00")
        app.do("add", title="Prep: Math 1920 Quiz 3", preset="Exam prep", duration_min=120, due="2026-10-23T13:25",
               before=[quiz])  # fmt: skip
        app.do("add", title="Prep for interview", preset="Exam prep", duration_min=180, due="2026-10-23T10:00",
               before=[talk["item"]["id"]])  # fmt: skip
        for rule in rules:
            app.do("rule_add", text=rule)
        app.do("replan")
        blocks = app.do("plan", start="2026-10-19T00:00", end="2026-10-24T00:00")["blocks"]
        return {t: [b for b in blocks if b["title"] == t] for t in ("Prep: Math 1920 Quiz 3", "Prep for interview")}

    spread = prep([])
    assert any(b["start"] < "2026-10-21" for b in spread["Prep: Math 1920 Quiz 3"] + spread["Prep for interview"])
    close = prep(["I prefer all sessions of exam prep tasks to be done as close to the exam as possible"])
    assert all(b["start"] >= "2026-10-22T12:00" for b in close["Prep: Math 1920 Quiz 3"])
    assert all(b["start"] >= "2026-10-22T12:00" for b in close["Prep for interview"])
    buffered = prep(["prep for the math quiz closer to the math quiz (with 1 day of buffer)"])
    quiz = buffered["Prep: Math 1920 Quiz 3"]
    assert quiz and all(b["end"] <= "2026-10-22T13:25" for b in quiz) and any(b["start"] >= "2026-10-22" for b in quiz)


def test_a_replan_with_nothing_changed_keeps_the_plan(tmp_path: Path) -> None:
    # Past the first week a 45-minute task fills an hour (two 30-minute slots). Rebuilt from the saved plan for a warm
    # start, that hour was cut to the 45 minutes, the task dropped as too short and placed anew, so every tick (a
    # replan each 15 minutes) moved blocks with nothing changed. Now the plan you have holds unless one is better.
    app = new_app(tmp_path, horizon_days=14)
    for n in range(12):
        app.do("add", title=f"run {n}", duration_min=45, release="2026-10-26T08:00", due=f"2026-10-{27 + n % 4}T20:00")
    app.do("add", text="essay ~3h due fri 5pm")
    app.do("replan")

    def blocks() -> list[tuple]:
        plan = app.do("plan", start="2026-10-19T09:00", end="2026-11-02T00:00")
        return sorted((b["item_id"], b["start"], b["end"]) for b in plan["blocks"])

    app.do("replan")
    first = blocks()
    assert any(b[1] >= "2026-10-26T04:00" for b in first)  # some in the second week's 30-minute slots
    for _ in range(3):
        app.do("replan")
        assert blocks() == first
