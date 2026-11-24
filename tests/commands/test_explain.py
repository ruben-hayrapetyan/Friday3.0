"""Explanations of the plan (DESIGN §16): the `why` sentence (room to spare, pins, the event a block follows, a
day's pace), `why_not` refusals, and the cost per rule in the plan or on one day."""

from datetime import timedelta
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def why_of(app: App, item_id: int) -> str:
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["item_id"] == item_id)
    return app.do("why", key=key)["sentence"]


def test_why_says_how_much_room_work_has_before_its_due(app: App) -> None:
    tight = app.do("add", text="PS due mon 11:00 ~2h")["item"]["id"]
    soon = app.do("add", text="lab due tue 17:00 ~30m")["item"]["id"]
    later = app.do("add", text="essay due thu 17:00 ~30m")["item"]["id"]
    app.do("replan")
    assert why_of(app, tight).startswith("Due Mon 19 Oct 11am; no room to spare: it has to happen as planned")
    assert why_of(app, soon).startswith("Due Tue 20 Oct 5pm; it could all start 31 h later and still be on time")
    assert why_of(app, later).startswith("Due Thu 22 Oct 5pm; it could all start 3 days later and still be on time")


def test_why_names_your_pin_the_event_it_follows_and_the_days_pace(app: App) -> None:
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("add", title="Seminar", when="fixed", start="2026-10-19T13:00", end="2026-10-19T14:00", buffer_after_min=15)
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T14:15", kind="locked")
    app.do("pace", name="easy")
    app.do("replan")
    assert why_of(app, essay) == "You pinned it here. Starts right after Seminar + 15 min. Easy pace that day."


def test_why_after_an_event_with_no_buffer_names_only_the_event(app: App) -> None:
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("add", title="Seminar", when="fixed", start="2026-10-19T13:00", end="2026-10-19T14:00")
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T14:00", kind="locked")
    app.do("replan")
    assert why_of(app, essay) == "You pinned it here. Starts right after Seminar."


def test_why_for_a_block_not_in_the_plan_says_so(app: App) -> None:
    app.do("add", text="essay ~1h")
    app.do("replan")
    with pytest.raises(FieldError, match="no block T1@2026-10-25T03:00 in the current plan"):
        app.do("why", key="T1@2026-10-25T03:00")


def test_why_not_refuses_a_start_outside_the_horizon(app: App) -> None:
    app.do("add", text="essay ~1h")
    app.do("replan")
    key = app.do("plan")["blocks"][0]["key"]
    with pytest.raises(FieldError, match="outside the planning horizon") as refused:
        app.do("why_not", key=key, start="2026-11-30T10:00")
    assert refused.value.field == "start"


def test_rule_totals_for_the_whole_plan_or_one_day(app: App) -> None:
    app.do("add", text="PS due mon 11:00 ~2h")
    app.do("replan")
    whole = app.do("rule_totals")
    assert whole["finish_early"] > 0 and "late_work" in whole
    assert app.do("rule_totals", day="2026-10-19") == {"finish_early": whole["finish_early"]}
    assert app.do("rule_totals", day="2030-01-01") == {}


def test_changes_still_answer_after_an_add_the_plan_placed_is_taken_back(app: App) -> None:
    app.do("add", text="essay ~2h")
    lab = app.full("add", payload={"text": "lab ~1h"})
    app.do("replan")
    app.do("undo", command_id=lab.command_id)
    out = app.do("changes")  # was: FieldError "That item (T2) isn't there any more"
    titles = [b["title"] for b in out["added"]] + [b["title"] for b in out["removed"]]
    assert "essay" in titles
    assert "lab" not in titles  # taken back: not named as if it were still there


def test_why_not_with_nowhere_else_says_what_rules_the_rest_out(app: App) -> None:
    # 17 Nov, a client: "Nowhere else it can go (No other place fits)" beside a free afternoon said nothing of why
    app.do("add", title="Meeting", when="fixed", start="2026-10-19T09:15", end="2026-10-19T09:30")
    app.do("add", title="Print it", preset="Assignment", duration_min=15, due="2026-10-19T09:30", firmness="hard")
    app.do("replan")
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["title"] == "Print it")
    answer = app.do("why_not", key=key)
    assert answer["wall"] and answer["wall"] != "No other place fits"


def test_try_elsewhere_offers_free_time_when_the_plan_dropped_a_lock(app: App) -> None:
    # 17 Nov, a client: "Nowhere else it can go (No other place fits)" for a 15-minute task, beside a free afternoon.
    # A lock the planner couldn't keep (an hour's laundry in one sitting, locked for the half hour before a meeting)
    # became a preferred pin for the plan; Try elsewhere asked with the lock in force, so the plan broke it as it was
    # and every other time "didn't fit".
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("add", title="Lunch", when="fixed", start="2026-10-19T12:00", end="2026-10-19T13:00")
    app.do("add", title="Meeting", when="fixed", start="2026-10-19T13:45", end="2026-10-19T14:00")
    laundry = app.do("add", title="laundry", duration_min=60, shape="one_sitting")["item"]["id"]
    app.do("add", title="print lab 10 instructions", preset="Assignment", duration_min=15, due="2026-10-19T23:59",
           firmness="hard")  # fmt: skip
    app.do("replan")
    app.do("pin", id=laundry, start="2026-10-19T13:15", end="2026-10-19T13:45", kind="locked")
    app.do("replan")
    assert "A lock on laundry couldn't be kept and became a preferred pin" in app.do("status")["notices"]
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["title"] == "print lab 10 instructions")
    answer = app.do("why_not", key=key)
    assert answer["to_start"] is not None and answer["wall"] is None
    # and the half hour the lock no longer holds is free, as it is in the plan (was "Locked: laundry")
    there = app.do("why_not", key=key, start="2026-10-19T13:15")
    assert there["to_start"] == "2026-10-19T13:15" and there["wall"] is None


def block_under_way(app: App, minutes: int, into: int) -> dict:
    """An essay's block, with the clock `into` minutes past its start."""
    app.do("add", title="essay", duration_min=minutes, due="2026-10-20T17:00", firmness="hard")
    app.do("replan")
    block = next(b for b in app.do("plan")["blocks"] if b["title"] == "essay")
    app.at(f"2026-10-19T{int(block['start'][11:13]):02d}:{int(block['start'][14:16]) + into:02d}")
    return block


def test_try_elsewhere_on_the_block_under_way_offers_a_place_for_the_rest_of_it(app: App) -> None:
    # 17 Nov: on the block you were in, Try elsewhere was refused ("has no block at that time") and the card said
    # "Nowhere else is better"; the calendar cuts the block at now, and the rest's key was refused too
    block = block_under_way(app, 60, 20)  # 9:00-10:00 at 9:20: the plan holds 9:30-10:00 of it
    pieces = [b["key"] for b in app.do("plan")["blocks"] if b["title"] == "essay"]
    assert pieces == ["T1@2026-10-19T09:00", "T1@2026-10-19T09:15"]
    for key in pieces:
        answer = app.do("why_not", key=key)
        assert answer["to_start"] is not None and answer["note"] is None
        assert parse_local(answer["to_end"]) - parse_local(answer["to_start"]) == timedelta(minutes=30)
        assert app.do("why", key=key)["sentence"]  # the card's why too
    assert block["key"] == pieces[0]


def test_try_elsewhere_on_a_block_with_nothing_left_being_timed_or_gone_by_says_so(app: App) -> None:
    block = block_under_way(app, 15, 5)
    assert app.do("why_not", key=block["key"]) == {
        "key": block["key"], "to_start": None, "to_end": None, "wall": None, "difference": {}, "total": 0,
        "note": "It's under way, so there's nothing of it left to move. Not doing it now? Drag it to a later time.",
    }  # fmt: skip
    app.do("start", id=block["item_id"])
    assert app.do("why_not", key=block["key"])["note"] == (
        "You're timing it now. Stop the timer, and what's left of it can go elsewhere."
    )
    app.at("2026-10-19T09:30")  # a past block's card has Try elsewhere too
    assert app.do("why_not", key=block["key"])["note"] == "Its time has gone by, so there's nothing of it to move."


def test_a_meal_with_nowhere_else_says_its_time_and_whats_around_it(app: App) -> None:
    # 17 Nov: "Nowhere else it can go (Past its due)" for a lunch: its half hour tried at 2:15 ran past its time
    app.do("settings_set", key="event_kinds", value={"other": {"before_min": 0, "after_min": 0}})
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=15, ideal_min=30, max_min=30)  # fmt: skip
    app.do("add", title="CHEM 2090 Lecture", when="fixed", start="2026-10-19T11:30", end="2026-10-19T14:00")
    app.do("replan")
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["title"] == "Lunch" and "10-19" in b["start"])
    assert key == "T1@2026-10-19T14:00"
    assert app.do("why_not", key=key)["wall"] == "Lunch goes between 11:30am and 2:30pm, around CHEM 2090 Lecture"
    app.do("settings_set", key="clock", value="24h")
    assert app.do("why_not", key=key)["wall"] == "Lunch goes between 11:30 and 14:30, around CHEM 2090 Lecture"
    app.at("2026-10-19T12:00")  # begun: by when it goes
    assert app.do("why_not", key=key)["wall"] == "Lunch goes by 14:30, around CHEM 2090 Lecture"


# 23 Nov, the agreement check (web/scripts/agreement-check.mjs): a late item's block said "no room to spare: it has to
# happen as planned" while the Plan page said it will be late. The block now says it's late, as the Plan page does.
def test_a_late_items_block_says_its_late_not_that_it_has_no_room_to_spare(app: App) -> None:
    app.do("add", title="Class", when="fixed", start="2026-10-19T10:00", end="2026-10-19T23:00")
    report = app.do("add", title="Lab report", due="2026-10-19T12:00", duration_min=180, firmness="hard")["item"]["id"]
    app.do("replan")
    [late] = [i for i in app.do("status")["late_items"] if i["item_id"] == report]
    said = why_of(app, report)
    assert "no room to spare" not in said and "on time" not in said
    assert said.startswith("Due Mon 19 Oct 12pm; the plan finishes it about ") and said.split("about ")[1].startswith(
        late_words(late["hours"])
    )


def late_words(hours: float) -> str:
    """The web's lateBy: whole days from a day, else to the quarter hour (web/src/lib/format.ts)."""
    if hours >= 24:
        days = round(hours / 24)
        return f"{days} day{'' if days == 1 else 's'}"
    m = max(15, round(hours * 60 / 15) * 15)
    return f"{m // 60}h {m % 60}m" if m // 60 and m % 60 else f"{m // 60}h" if m // 60 else f"{m}m"


# 23 Nov, the agreement check: the late list read the saved plan's lateness of any item, so until the next plan a
# finished or deleted task still "will be late" on the Plan page.
@pytest.mark.parametrize("gone", ["done", "drop"])
def test_finished_or_deleted_work_isnt_late(app: App, gone: str) -> None:
    app.do("add", title="Class", when="fixed", start="2026-10-19T10:00", end="2026-10-19T23:00")
    report = app.do("add", title="Lab report", due="2026-10-19T12:00", duration_min=180, firmness="hard")["item"]["id"]
    app.do("replan")
    assert [i["item_id"] for i in app.do("status")["late_items"]] == [report]
    app.do(gone, id=report)
    assert app.do("status")["late_items"] == []
