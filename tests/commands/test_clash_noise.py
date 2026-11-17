"""17 Nov, your screenshot: "Spread hard work evenly" clashed with "At least 7 h of sleep a night": "Fri: keeping it
moves CUAI HW to 1:30am from 10pm". On your plan, weighing the spread rule 20 times over kept your work only 5% more
even (26 of 484), while a plan made from scratch happened to put CUAI HW later: the search's noise, called a clash, and
said without what the rule gains. Now a rule clashes only when keeping it gains at least a tenth of its cost, and the
card names both sides."""

from datetime import datetime
from types import SimpleNamespace as NS

from friday.core.time import to_utc
from pathlib import Path

from friday.planner.snapshot import take_snapshot
from friday.planner.views import CLASH_FACTOR, clash_of, cost_said, kept_said
from tests.commands.helpers import new_app

TZ = "America/New_York"
SNAPSHOT = NS(settings={"time": NS(timezone=TZ, day_start="04:00")}, now_utc=to_utc(datetime(2026, 11, 16, 9), TZ))


def plan(days: dict[str, dict[str, int]]) -> NS:
    return NS(report={"rule_totals_by_day": days}, blocks=[])


def block(start: str, end: str) -> NS:
    return NS(start_utc=to_utc(datetime.fromisoformat(start), TZ), end_utc=to_utc(datetime.fromisoformat(end), TZ))


# your plan's numbers for the spread rule, by day (late nights the rule that paid); weighed ×20 it's the after plan's
BEFORE = {"2026-11-19": {"even_load": 55, "late_night": 1324}, "2026-11-20": {"even_load": 105, "late_night": 1625},
          "2026-11-21": {"even_load": 324, "late_night": 2886}}  # fmt: skip
AFTER = {"2026-11-19": {"even_load": 950, "late_night": 1700}, "2026-11-20": {"even_load": 2090, "late_night": 1900},
         "2026-11-21": {"even_load": 6480, "late_night": 3363}}  # fmt: skip


def test_a_rule_kept_no_better_than_noise_clashes_with_nothing(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    snapshot = take_snapshot(app.conn, app.now_utc)
    # 26 of its 484 kept, late nights 1128 dearer: was a clash with late nights
    assert clash_of(snapshot, "even_load", plan(BEFORE), plan(AFTER)) is None
    # kept a good deal better (a third of its cost), it's a clash
    kept = {d: {**t, "even_load": BEFORE[d]["even_load"] * 2 // 3 * CLASH_FACTOR} for d, t in AFTER.items()}
    assert clash_of(snapshot, "even_load", plan(BEFORE), plan(kept)) is not None


def test_what_keeping_a_rule_gains_is_its_cost_saved_by_day() -> None:
    from friday.planner.views import gain_of

    before = {"d1": {"r": 100}, "d2": {"r": 50}}
    after = {"d1": {"r": 40 * CLASH_FACTOR}, "d2": {"r": 60 * CLASH_FACTOR}}
    assert gain_of(before, after, "r") == 60  # d1 saves 60; d2 got dearer, no gain


def test_the_card_names_what_the_rule_gains_and_that_it_takes_sleep() -> None:
    was = [block("2026-11-20T22:00", "2026-11-21T00:00")]
    now = [block("2026-11-21T01:30", "2026-11-21T03:30")]
    lead = kept_said("even_load", "CUAI HW", was, now, SNAPSHOT)
    assert lead == "Spreading your work more evenly"
    said = cost_said("sleep_min", "CUAI HW", was, now, SNAPSHOT)
    assert said == "moves CUAI HW to 1:30am from 10pm, into your sleep"
    assert kept_said("energy", "Lab", was, now, SNAPSHOT) == "Putting hard work at your sharpest hours"
