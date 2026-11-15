"""A repeating task's times kept apart (planner/spacing.py). Glass box: the next time after the last
one done, the waits between the rest, and never a wait that would make one late. Black box through the commands: the
repeat's field set and cleared, a rule in words setting it. The whole system: weekly laundry planned with a week
between, where before it went on Sunday and again on Tuesday."""

from dataclasses import replace
from pathlib import Path

import pytest

from friday.core.items import FieldError, Item
from friday.core.time import format_utc, parse_utc
from friday.planner.spacing import LastDone, after_last, loosened, spaced, wait
from tests.commands.helpers import App, new_app

DAY = 1440


def laundry(item_id: int, due: str, units: int = 12) -> Item:
    return Item(id=item_id, title="Laundry", when="window", amount="fixed", duration_units=units, due_utc=due,
                series_id=7, status="todo")  # fmt: skip


def test_the_next_time_waits_the_gap_after_the_last_one_started() -> None:
    nxt = laundry(2, "2026-11-16T01:00Z")  # due Mon 8pm local
    done = LastDone(started_utc=parse_utc("2026-11-08T22:00Z"), done_utc=parse_utc("2026-11-09T01:00Z"),
                    due_utc=parse_utc("2026-11-09T01:00Z"))  # fmt: skip
    out = after_last(nxt, 7 * DAY, done)
    assert out.release_utc == "2026-11-15T22:00Z" and out.due_utc == nxt.due_utc


def test_done_late_the_next_due_moves_by_as_much() -> None:
    nxt = laundry(2, "2026-11-16T01:00Z")
    late = LastDone(started_utc=parse_utc("2026-11-11T22:00Z"), done_utc=parse_utc("2026-11-12T01:00Z"),
                    due_utc=parse_utc("2026-11-09T01:00Z"))  # three days late  # fmt: skip
    out = after_last(nxt, 7 * DAY, late)
    assert out.due_utc == "2026-11-19T01:00Z" and out.release_utc == "2026-11-18T22:00Z"


def test_a_gap_that_cant_fit_is_shortened_rather_than_made_late() -> None:
    nxt = laundry(2, "2026-11-16T01:00Z")
    done = LastDone(parse_utc("2026-11-08T22:00Z"), parse_utc("2026-11-09T01:00Z"), parse_utc("2026-11-09T01:00Z"))
    out = after_last(nxt, 10 * DAY, done)  # ten days apart can't fit before the due a week later
    assert parse_utc(out.due_utc or "") - parse_utc(out.release_utc or "") == 3 * 60  # its own three hours left


def test_later_times_wait_on_the_one_before_by_the_gap_less_its_length() -> None:
    a, b = laundry(1, "2026-11-09T01:00Z"), laundry(2, "2026-11-16T01:00Z")
    assert wait(a, b, 7 * DAY) == 7 * DAY - 3 * 60  # start to start, a week
    assert wait(a, b, 9 * DAY) == 7 * DAY - 3 * 60  # never more than lets b fit before its due


def test_spaced_touches_only_repeats_with_a_gap() -> None:
    a, b = laundry(1, "2026-11-09T01:00Z"), laundry(2, "2026-11-16T01:00Z")
    other = replace(laundry(3, "2026-11-10T01:00Z"), series_id=8)
    items, waits, originals = spaced([a, b, other], {7: 7.0}, {})
    assert items == [a, b, other]  # nothing done yet: nothing moved
    assert [(w.item_id, w.depends_on_id) for w in waits] == [(2, 1)] and set(originals) == {1, 2}


def test_a_spaced_time_that_would_be_late_gets_its_own_window_back() -> None:
    a, b = laundry(1, "2026-11-09T01:00Z"), laundry(2, "2026-11-16T01:00Z")
    done = LastDone(parse_utc("2026-11-08T22:00Z"), parse_utc("2026-11-09T01:00Z"), parse_utc("2026-11-09T01:00Z"))
    items, waits, originals = spaced([a, b], {7: 7.0}, {7: done})
    assert items[0].release_utc  # the first open one moved after the last done
    back, kept = loosened(items, waits, originals, late={1: 2.0})
    assert (
        parse_utc(back[0].release_utc or "") == parse_utc(items[0].release_utc or "") - 3 * 60
    )  # 2 h late, 3 h sooner
    assert kept == waits  # the wait is on the next, which isn't late
    back, kept = loosened(items, waits, originals, late={2: 5.25})
    assert kept[0].lag_min == waits[0].lag_min - (5 * 60 + 15) - 60  # as late as it was, and an hour
    back, kept = loosened(items, waits, originals, late={2: 200.0})
    assert kept == []  # a wait that would go to nothing goes


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-02T09:00", horizon_days=14)


def weekly_laundry(app: App) -> int:
    """Laundry every Monday by 8pm, any time in the week before (as yours is: from the Monday before at 8pm)."""
    return app.do(
        "series_add", title="Laundry", every="mon", due_offset_min=20 * 60, release_offset_min=20 * 60 - 7 * DAY,
        duration_min=180, preset="Assignment",  # as yours was on 8 Nov, before a dated to-do became a Task (C97)
    )["id"]  # fmt: skip


def test_the_field_is_set_and_cleared_through_its_command(app: App) -> None:
    series = weekly_laundry(app)
    app.do("series_spacing", id=series, days=7)
    assert app.table("series")[0]["min_gap_days"] == 7.0
    app.do("series_spacing", id=series, days=None)
    assert app.table("series")[0]["min_gap_days"] is None
    with pytest.raises(FieldError):
        app.do("series_spacing", id=series, days=0)


def test_a_rule_in_words_sets_the_gap_on_the_repeat_it_names(app: App) -> None:
    series = weekly_laundry(app)
    assert app.do("rule_read", text="laundry at least 7 days apart")["reading"]["kind"] == "spacing"
    app.do("rule_add", text="laundry at least 7 days apart")
    assert [r["min_gap_days"] for r in app.table("series") if r["id"] == series] == [7.0]
    with pytest.raises(FieldError, match="repeat"):
        app.do("rule_add", text="dishes at least 2 days apart")  # no such repeating task


def laundry_done_monday_then_planned(app: App, days: float | None) -> int:
    """The first laundry done Monday 9 to noon; the next one's first planned start."""
    from friday.planner.service import replan

    series = weekly_laundry(app)
    app.do("series_spacing", id=series, days=days)
    first = min((r for r in app.table("items") if r["title"] == "Laundry"), key=lambda r: r["due_utc"])["id"]
    app.at("2026-11-02T12:30").do("log", id=first, start="2026-11-02T09:00", end="2026-11-02T12:00")
    app.do("done", id=first)
    replan(app.conn, app.now_utc)
    return min(parse_utc(b["start_utc"]) for b in app.table("blocks") if b["item_id"] in laundry_ids(app))


def test_the_next_laundry_waits_a_week_after_the_last_where_it_went_the_next_day(tmp_path: Path) -> None:
    started = parse_utc("2026-11-02T14:00Z")  # Monday 9am, New York
    (tmp_path / "plain").mkdir()
    (tmp_path / "spaced").mkdir()
    plain = laundry_done_monday_then_planned(new_app(tmp_path / "plain", now="2026-11-02T09:00", horizon_days=14), None)
    assert plain - started < 2 * DAY  # as on 8 Nov: the next one the day after
    spaced = laundry_done_monday_then_planned(new_app(tmp_path / "spaced", now="2026-11-02T09:00", horizon_days=14), 7)
    assert spaced - started >= 7 * DAY


def laundry_ids(app: App) -> set[int]:
    return {r["id"] for r in app.table("items") if r["title"] == "Laundry"}


def test_format_round_trip() -> None:
    assert format_utc(parse_utc("2026-11-16T01:00Z")) == "2026-11-16T01:00Z"


def test_with_little_room_the_next_laundry_is_closer_rather_than_late(app: App) -> None:
    """A trip fills the week after Tuesday: a week from the first laundry there's no room before the next is due, so
    it goes closer, not late."""
    from friday.planner.service import replan

    series = weekly_laundry(app)
    app.do("series_spacing", id=series, days=7)
    app.do("add", text="Trip", when="fixed", start="2026-11-04T08:00", end="2026-11-09T23:59")  # past its due
    replan(app.conn, app.now_utc)
    late = app.do("status")["late"]
    assert not any("Laundry" in title for title in late)


def test_a_next_time_that_starts_later_than_the_gap_keeps_its_own_start() -> None:
    nxt = replace(laundry(2, "2026-11-16T01:00Z"), release_utc="2026-11-15T23:00Z")  # starts after the week's wait
    done = LastDone(parse_utc("2026-11-08T22:00Z"), parse_utc("2026-11-09T01:00Z"), parse_utc("2026-11-09T01:00Z"))
    out = after_last(nxt, 7 * DAY, done)
    assert out.release_utc == "2026-11-15T23:00Z" and out.due_utc == "2026-11-16T01:00Z"


def gym(item_id: int) -> Item:
    """One of this week's three gym times: the week Monday to Monday, an hour each."""
    return Item(id=item_id, title="Gym", when="window", amount="fixed", duration_units=4, series_id=9, status="todo",
                release_utc="2026-11-16T05:00Z", due_utc="2026-11-23T05:00Z")  # fmt: skip


def test_times_of_one_week_wait_the_gap_on_each_other() -> None:
    """15 Nov, a client: "3 times a week" at least 2 days apart shared one due, and a wait of nothing between them."""
    times = [gym(1), gym(2), gym(3)]
    _, waits, _ = spaced(times, {9: 2.0}, {})
    assert [(w.item_id, w.depends_on_id) for w in waits] == [(2, 1), (3, 2)]
    assert [w.lag_min + 60 for w in waits] == [2 * DAY, 2 * DAY]  # 2880 minutes from one start to the next


def test_a_week_too_short_for_the_gap_spreads_its_times_evenly() -> None:
    times = [gym(1), gym(2), gym(3)]
    _, waits, _ = spaced(times, {9: 5.0}, {})  # 5 days apart can't fit three in a week
    assert [w.lag_min for w in waits] == [(7 * DAY - 3 * 60) // 2] * 2  # as far apart as the week lets them


def gym_three_a_week_planned(app: App, days: float | None) -> list[int]:
    from friday.planner.service import replan

    series = app.do("series_add", title="Gym", every="week", per_window=3, duration_min=60, preset="Habit")["id"]
    app.do("series_spacing", id=series, days=days)
    replan(app.conn, app.now_utc)
    gyms = {r["id"]: r for r in app.table("items") if r["title"] == "Gym"}
    first_week = min(r["due_utc"] for r in gyms.values())
    ids = {i for i, r in gyms.items() if r["due_utc"] == first_week}
    return sorted(min(b["start_utc"] for b in app.table("blocks") if b["item_id"] == i) for i in ids)


def test_three_gym_times_a_week_are_planned_two_days_apart(app: App) -> None:
    starts = [parse_utc(s) for s in gym_three_a_week_planned(app, 2)]
    assert len(starts) == 3
    assert all(b - a >= 2 * DAY for a, b in zip(starts, starts[1:], strict=False))
