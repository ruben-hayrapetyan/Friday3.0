"""Explanations and what gives (tests/features.toml: explain), the whole pipeline: a real `fridayd serve` on the real
clock, its worker planning each change, and each question the Plan page asks sent over HTTP as it asks it: what the
latest plan changed (`changes`), what moving a block would cost (`why_not`), the plan with rules weighed otherwise
(`preview_weights`), ways out of late work (`triage`) and of a full week (`lighten`), each applied the way its button
applies it and the plan read back. The next hours are kept awake whatever the time (sleep starts 14 hours from now)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import WEEKDAYS, Friday, zone_for_hour
from tests.system.test_decisions_pipeline import planned

# about noon now (24 Nov): `lighten` is asked for the week from Friday's day, and before 4am that day is yesterday's
# last hour, so the week is six days ahead; run at 3am, the plan put all of the novel notes on the seventh, after it,
# and there was nothing in the week to lighten
TZ = zone_for_hour(12)


def quarter() -> datetime:
    """The next quarter hour, local: where the plan's slots start."""
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    return now + timedelta(minutes=15 - now.minute % 15)


def at(minutes: int) -> str:
    return (quarter() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def awake(friday: Friday) -> None:
    bed = quarter() + timedelta(hours=14)
    times = {"bedtime": bed.strftime("%H:%M"), "wake": (bed + timedelta(hours=8)).strftime("%H:%M"), "margin_min": 0}
    friday.c("settings_set", key="sleep", value=dict.fromkeys(WEEKDAYS, times))


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("explain"))
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"timezone": TZ})
    awake(server)
    planned(server)
    yield server
    server.stop()


def ask(friday: Friday, verb: str, **body: Any) -> Any:
    """A query whose input has a mapping in it, asked by POST as the app asks it."""
    answer = friday.http.post(f"/api/q/{verb}", json=body)
    assert answer.status_code == 200, answer.text
    return answer.json()


def refused(friday: Friday, verb: str, method: str = "get", **given: Any) -> dict:
    answer = friday.http.get(f"/api/q/{verb}", params=given) if method == "get" else \
        friday.http.post(f"/api/q/{verb}", json=given)  # fmt: skip
    assert answer.status_code == 422, answer.text
    return answer.json()


def week_blocks(friday: Friday, title: str) -> list[dict]:
    return [b for b in friday.q("plan", start=at(-60), end=at(60 * 24 * 14))["blocks"] if b["title"] == title]


def today() -> str:
    """The planning day: it starts at 4am."""
    return (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date().isoformat()


def test_triage_offers_nothing_when_nothing_is_late(friday: Friday) -> None:
    assert friday.q("triage") == {"late": {}, "options": []}


@pytest.fixture(scope="module")
def week(friday: Friday) -> dict[str, int]:
    """An essay due before the day's busy afternoon that can't be done by then, and long notes due in ten days."""
    friday.c("add", title="busy", when="fixed", start=at(120), end=at(480))
    essay = friday.c("add", title="essay", duration_min=180, firmness="hard", due=at(120))["item"]["id"]
    notes = friday.c("add", title="novel notes", duration_min=600, firmness="hard", due=at(60 * 24 * 10))["item"]["id"]
    planned(friday)
    friday.until(lambda: "essay" in friday.q("status")["late"] and week_blocks(friday, "novel notes"), timeout=300)
    return {"essay": essay, "notes": notes}


def test_changes_names_the_commands_and_the_blocks_they_added(friday: Friday, week: dict[str, int]) -> None:
    out = friday.q("changes")
    titles = [i["input"].get("title") for i in out["inputs"] if i["command"] == "add"]
    # the worker may have planned the first adds apart: the latest plan names at least the last
    assert titles[-1] == "novel notes" and set(titles) <= {"busy", "essay", "novel notes"}
    assert all(i["actor"] == "you" for i in out["inputs"] if i["command"] == "add")
    added = {b["item_id"] for b in out["added"]}
    assert week["notes"] in added and added <= {week["essay"], week["notes"]}  # the event isn't planned work
    plan = {b["key"] for b in friday.q("plan", start=at(-60), end=at(60 * 24 * 14))["blocks"]}
    assert {b["key"] for b in out["added"]} <= plan  # what it says was added is in the plan
    assert out["late_hours"] == friday.q("status")["late"]
    assert set(out["rule_totals_after"]) >= {r["name"] for r in friday.q("settings")["rules"]}


def test_why_not_says_what_moving_a_block_to_its_best_other_place_costs(friday: Friday, week: dict) -> None:
    (block,) = week_blocks(friday, "novel notes")[:1]
    out = friday.q("why_not", key=block["key"])
    assert out["key"] == block["key"] and out["wall"] is None and out["note"] is None
    assert out["to_start"] != block["start"]
    length = datetime.fromisoformat(block["end"]) - datetime.fromisoformat(block["start"])
    assert datetime.fromisoformat(out["to_end"]) - datetime.fromisoformat(out["to_start"]) == length
    assert sum(out["difference"].values()) == out["total"]


def test_why_not_to_a_later_day_costs_more_and_over_an_event_names_the_wall(friday: Friday, week: dict) -> None:
    block = week_blocks(friday, "novel notes")[0]
    best = friday.q("why_not", key=block["key"])["total"]
    later = friday.q("why_not", key=block["key"], start=at(60 * 24 * 3))
    assert later["wall"] is None and later["to_start"] >= at(60 * 24 * 3)[:10]
    assert later["total"] >= best and sum(later["difference"].values()) == later["total"]
    over = friday.q("why_not", key=block["key"], start=at(200))
    assert over["wall"] == "Busy: busy"


def test_why_not_moves_nothing(friday: Friday, week: dict) -> None:
    before = friday.q("status")["plan_id"], [b["key"] for b in week_blocks(friday, "novel notes")]
    friday.q("why_not", key=week_blocks(friday, "novel notes")[0]["key"], start=at(60 * 24 * 2))
    assert (friday.q("status")["plan_id"], [b["key"] for b in week_blocks(friday, "novel notes")]) == before


def test_why_not_refuses_a_block_not_in_the_plan_or_a_start_it_cant_try(friday: Friday, week: dict) -> None:
    said = refused(friday, "why_not", key="T999999@2026-01-01T00:00")
    assert said == {"field": "key", "message": "key: no block T999999@2026-01-01T00:00 in the current plan"}
    key = week_blocks(friday, "novel notes")[0]["key"]
    far = (datetime.now(ZoneInfo(TZ)) + timedelta(days=200)).strftime("%Y-%m-%dT10:00")
    outside = refused(friday, "why_not", key=key, start=far)
    assert outside["message"] == "start: that start is outside the planning horizon"
    assert "is not a time like" in refused(friday, "why_not", key=key, start="whenever")["message"]


def test_preview_weights_with_a_rule_off_leaves_it_out_and_saves_nothing(friday: Friday, week: dict) -> None:
    status = friday.q("status")
    out = ask(friday, "preview_weights", off=["late_work"])
    assert out["rule_totals_before"] == friday.q("rule_totals")
    assert out["rule_totals_before"]["late_work"] > 0  # the essay is late
    assert "late_work" not in out["rule_totals_after"]
    assert out["late_hours"] and set(out["late_hours"]) == {"essay"}
    after = friday.q("status")
    assert (after["plan_id"], after["generation"]) == (status["plan_id"], status["generation"])


def test_preview_weights_with_a_weight_changed_counts_it_so(friday: Friday, week: dict) -> None:
    out = ask(friday, "preview_weights", weights={"late_work": 0})
    assert out["rule_totals_before"]["late_work"] > 0 and out["rule_totals_after"]["late_work"] == 0
    assert out["inputs"] == []  # nothing was run to make it


def test_preview_weights_tries_a_whole_rules_list_and_refuses_a_bad_one(friday: Friday, week: dict) -> None:
    out = ask(friday, "preview_weights", rules=[{"name": "x", "type": "nope"}])
    assert out["notices"] == ["Rule x is off: no rule type 'nope' is loaded"]
    assert "late_work" not in out["rule_totals_after"]  # only the list tried
    said = refused(friday, "preview_weights", "post", rules=[{"name": "late_night", "type": "late_night",
                                                              "weight": "heavy"}])  # fmt: skip
    assert said["field"] == "rules" and "weight: Input should be a valid number" in said["message"]


def test_lighten_offers_to_start_work_due_later_after_the_week(friday: Friday, week: dict) -> None:
    out = friday.q("lighten", start=today(), days=7)
    (option,) = [o for o in out["options"] if "novel notes" in o["action"]]
    day_after = datetime.fromisoformat(today()) + timedelta(days=7)
    assert option["action"] == f"Start novel notes on {day_after:%a} {day_after.day}"
    assert option["steps"] == [{"command": "edit", "input": {"id": week["notes"],
                                                             "release": f"{day_after:%Y-%m-%d}T04:00"}}]  # fmt: skip
    assert option["hours_moved"] > 0
    assert any(e.startswith("Still done by its due") for e in option["side_effects"])
    assert not any("essay" in o["action"] for o in out["options"])  # late work isn't put off


def test_applying_a_way_to_lighten_moves_that_work_past_the_week(friday: Friday, week: dict) -> None:
    (option,) = [o for o in friday.q("lighten", start=today(), days=7)["options"] if "novel notes" in o["action"]]
    for step in option["steps"]:
        friday.c(step["command"], **step["input"])
    release = option["steps"][0]["input"]["release"]
    assert friday.q("item", id=week["notes"])["item"]["release"] == release
    planned(friday)
    assert all(b["start"] >= release for b in week_blocks(friday, "novel notes"))
    assert "novel notes" not in friday.q("status")["late"]  # still on time


def test_lighten_refuses_days_it_cant_take_and_offers_nothing_past_the_forecast(friday: Friday, week: dict) -> None:
    assert refused(friday, "lighten", start=today(), days=8)["detail"][0]["loc"] == ["query", "days"]
    assert refused(friday, "lighten", start="next week")["detail"][0]["loc"] == ["query", "start"]
    far = (datetime.now(ZoneInfo(TZ)) + timedelta(days=700)).date().isoformat()
    assert friday.q("lighten", start=far, days=7) == {"options": []}


def test_triage_offers_ways_out_of_late_work_each_saving_hours(friday: Friday, week: dict) -> None:
    out = friday.q("triage")
    assert out["late"] == friday.q("status")["late"] and set(out["late"]) == {"essay"}
    saved = [o["late_hours_saved"] for o in out["options"]]
    assert saved and saved == sorted(saved, reverse=True) and all(s > 0 for s in saved)
    due = datetime.fromisoformat(friday.q("item", id=week["essay"])["item"]["due"])
    (later,) = [o for o in out["options"] if o["action"] == "Move essay's due 1 day later"]
    a_day_on = (due + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    assert later["steps"] == [{"command": "edit", "input": {"id": week["essay"], "due": a_day_on}}]


def test_applying_a_triage_option_makes_the_work_on_time(friday: Friday, week: dict) -> None:
    (option,) = [o for o in friday.q("triage")["options"] if o["action"] == "Move essay's due 3 days later"]
    for step in option["steps"]:
        friday.c(step["command"], **step["input"])
    planned(friday)
    assert friday.until(lambda: "essay" not in friday.q("status")["late"])
    assert friday.q("triage") == {"late": {}, "options": []}


def test_what_changed_after_dropping_work_lists_its_blocks_removed(friday: Friday, week: dict) -> None:
    keys = {b["key"] for b in week_blocks(friday, "essay")}
    assert keys
    friday.c("drop", id=week["essay"])
    planned(friday)

    def after_drop() -> dict | None:
        out = friday.q("changes")
        return out if any(i["command"] == "drop" for i in out["inputs"]) else None

    out = friday.until(after_drop)
    assert {b["key"] for b in out["removed"] if b["item_id"] == week["essay"]} == keys
    assert week_blocks(friday, "essay") == []
