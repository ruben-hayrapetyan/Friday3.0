"""A repeating task's times kept apart (planner/spacing.py, PROGRESS.md C50). Glass box: the next time after the last
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
        duration_min=180,
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
    app.do("log", id=first, start="2026-11-02T09:00", end="2026-11-02T12:00")
    app.do("done", id=first)
    app.at("2026-11-02T12:30")
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
    app.do("add", text="Trip", when="fixed", start="2026-11-04T08:00", end="2026-11-09T21:00")
    replan(app.conn, app.now_utc)
    late = app.do("status")["late"]
    assert not any("Laundry" in title for title in late)
