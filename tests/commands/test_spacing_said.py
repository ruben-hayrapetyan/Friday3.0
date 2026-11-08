"""Friday says when it planned a repeat's time closer than you asked (C50's last part, 8 Nov). Glass box: which
planned times are closer, read as you'd read them, and the words. Black box through the commands: weekly laundry kept
7 days apart, a trip covering the next one's due, so it goes the next day, not late, and the plan's notices and the
block's "why" say so; with room, nothing is said."""

from pathlib import Path

from friday.core.items import Item
from friday.core.time import format_local, parse_utc, to_local
from friday.planner.service import replan
from friday.planner.spacing import Closer, LastDone, amount, closer, closer_words, let_go, spaced
from tests.commands.helpers import TZ, App, new_app
from tests.commands.test_series_spacing import laundry, laundry_done_monday_then_planned, laundry_ids, weekly_laundry

DAY = 1440
MON = parse_utc("2026-11-02T14:00Z")  # Monday 9am, New York


def three(gap: float = 7.0) -> tuple[list[Item], dict[int, float]]:
    return [laundry(1, "2026-11-03T05:00Z"), laundry(2, "2026-11-10T05:00Z"), laundry(3, "2026-11-17T05:00Z")], {7: gap}


def test_a_time_a_day_after_the_one_before_is_closer_than_a_week() -> None:
    items, gaps = three()
    found = closer(items, gaps, {}, {1: MON, 2: MON + DAY, 3: MON + 8 * DAY})
    assert found == [Closer(2, 7, 1.0, 7.0, "days", since_last=False)]  # 3 is a week after 2: as asked


def test_the_first_open_time_counts_from_the_last_one_you_did() -> None:
    items, gaps = three()
    done = LastDone(MON - 3 * DAY, MON - 3 * DAY + 180, None)
    assert closer(items, gaps, {7: done}, {1: MON}) == [Closer(1, 7, 3.0, 7.0, "days", since_last=True)]


def test_closer_is_as_you_would_read_it_not_by_minutes() -> None:
    items, gaps = three()
    assert closer(items, gaps, {}, {1: MON, 2: MON + 7 * DAY - 40}) == []  # 6.97 days reads as 7
    assert closer(items, gaps, {}, {1: MON, 2: MON + 7 * DAY - 150})[0].apart == 6.9


def test_a_gap_under_two_days_is_counted_in_hours() -> None:
    items, gaps = three(gap=1.5)
    (found,) = closer(items, gaps, {}, {1: MON, 2: MON + 20 * 60})
    assert (found.apart, found.asked, found.unit) == (20.0, 36.0, "hours")


def test_a_time_not_in_the_plan_ends_the_count() -> None:
    items, gaps = three()
    assert closer(items, gaps, {}, {1: MON, 3: MON + DAY}) == []  # 2 isn't planned: 3 isn't measured against 1


def test_done_and_fixed_times_and_other_repeats_are_left_out() -> None:
    items, gaps = three()
    items[1] = Item(**{**items[1].__dict__, "status": "done"})
    other = Item(**{**laundry(4, "2026-11-04T05:00Z").__dict__, "series_id": 8})
    assert closer([*items, other], gaps, {}, {1: MON, 2: MON + DAY, 3: MON + 2 * DAY, 4: MON + 60}) == [
        Closer(3, 7, 2.0, 7.0, "days", since_last=False)
    ]


def test_the_words() -> None:
    assert amount(1.0, "days") == "1 day" and amount(5.6, "days") == "5.6 days" and amount(20.0, "hours") == "20 hours"
    assert closer_words(Closer(2, 7, 5.6, 7.0, "days", since_last=True)) == (
        "5.6 days after the last one you did, closer than the 7 days you asked, so it isn't late"
    )


def test_still_late_after_coming_closer_a_time_waits_for_nothing() -> None:
    items, gaps = three()
    done = LastDone(MON - DAY, MON - DAY + 180, None)
    moved, waits, originals = spaced(items, gaps, {7: done})
    back, kept = let_go(moved, waits, originals, late={2: 10.0})
    assert [w.item_id for w in kept] == [3]  # 2's wait on 1 gone, 3's on 2 kept
    assert back[1] == originals[2] and back[0] == moved[0]
    assert let_go(moved, waits, originals, late={}) == (moved, waits)


def trip_over_the_next_due(app: App) -> int:
    """Weekly laundry 7 days apart; a trip from Wednesday to past the next one's due (midnight Monday)."""
    series = weekly_laundry(app)
    app.do("series_spacing", id=series, days=7)
    app.do("add", text="Trip", when="fixed", start="2026-11-04T08:00", end="2026-11-09T23:59")
    replan(app.conn, app.now_utc)
    return series


def test_with_a_trip_the_next_laundry_goes_closer_and_the_plan_says_so(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-02T09:00", horizon_days=14)
    trip_over_the_next_due(app)
    status = app.do("status")
    assert not any("Laundry" in title for title in status["late"])
    said = [n for n in status["notices"] if n.startswith("Laundry on ")]
    assert len(said) == 1 and "after the one before, closer than the 7 days you asked, so it isn't late" in said[0]


def test_the_block_says_why_it_is_closer(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-02T09:00", horizon_days=14)
    trip_over_the_next_due(app)
    ids = sorted(laundry_ids(app))
    second = min((b for b in app.table("blocks") if b["item_id"] == ids[1]), key=lambda b: b["start_utc"])
    key = block_key(second)
    assert "closer than the 7 days you asked, so it isn't late" in app.do("why", key=key)["sentence"]
    first = min((b for b in app.table("blocks") if b["item_id"] == ids[0]), key=lambda b: b["start_utc"])
    assert "closer" not in app.do("why", key=block_key(first))["sentence"]


def block_key(block: dict) -> str:
    return f"T{block['item_id']}@{format_local(to_local(parse_utc(block['start_utc']), TZ))}"


def test_with_room_nothing_is_said(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-02T09:00", horizon_days=14)
    laundry_done_monday_then_planned(app, 7)
    assert not [n for n in app.do("status")["notices"] if "closer than" in n]
