"""Glass box: learn/beat_plan.py, planner/planned_late.py and planner/cushion.py's `shortened`, tested against how
they work inside (the merge of sittings, the night's midpoint split, the reach from the night's start, the rounding,
the record's backfill and pruning). Times are plain minutes; a night here runs 1000–1600, its midpoint 1300."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from friday.core.items import Item
from friday.core.time import format_utc
from friday.learn import beat_plan as bp
from friday.learn.beat_plan import Event, Finish, How, Night, later_nights, merged, overlap, read, speeds
from friday.planner import planned_late as pl
from friday.planner.cushion import shortened
from friday.planner.store import kv_get, kv_set
from tests.commands.helpers import App, new_app

NIGHT = Night("mon", 1000, 1600)


def finish(*worked: tuple[int, int], planned: int | None = 60, actual: int | None = None, **kw) -> Finish:
    return Finish(1, "essay", kw.pop("kind", "Assignment"), planned, actual, tuple(worked), kw.pop("scalable", True))


class TestMerged:
    def test_overlapping_and_touching_sittings_become_one_run(self) -> None:
        assert merged([(10, 20), (15, 30), (30, 40), (50, 60)]) == [(10, 40), (50, 60)]

    def test_empty_and_backwards_sittings_are_dropped(self) -> None:
        assert merged([(10, 10), (20, 15), (1, 2)]) == [(1, 2)]

    def test_order_given_does_not_matter(self) -> None:
        assert merged([(50, 60), (10, 20)]) == [(10, 20), (50, 60)]

    def test_overlap_counts_only_inside_the_window(self) -> None:
        assert overlap([(0, 100), (150, 300)], 50, 200) == 50 + 50


class TestRead:
    def test_a_minute_worked_twice_counts_once(self) -> None:
        how = read(finish((1000, 1060), (1030, 1090)), [NIGHT], [])
        assert how.evening_min == 90

    def test_the_night_splits_at_its_midpoint_into_evening_and_morning(self) -> None:
        how = read(finish((1250, 1350)), [NIGHT], [])
        assert (how.evening_min, how.morning_min) == (50, 50)

    def test_reach_is_from_the_night_s_start_to_the_last_evening_minute(self) -> None:
        how = read(finish((900, 1045), (1100, 1130)), [NIGHT], [])
        assert how.reach == {"mon": 130}

    def test_reach_stops_at_the_midpoint_when_work_runs_into_the_morning(self) -> None:
        assert read(finish((1200, 1500)), [NIGHT], []).reach == {"mon": 300}

    def test_work_only_in_the_morning_half_reaches_no_evening(self) -> None:
        how = read(finish((1400, 1500)), [NIGHT], [])
        assert how.reach == {} and how.morning_min == 100

    def test_two_nights_of_the_same_evening_keep_the_furthest_reach(self) -> None:
        week_later = Night("mon", 11080, 11680)
        how = read(finish((1000, 1030), (11080, 11200)), [NIGHT, week_later], [])
        assert how.reach == {"mon": 120} and how.evening_min == 150

    def test_events_are_named_once_and_only_past_fifteen_minutes(self) -> None:
        events = [Event("Club", 100, 200), Event("Club", 300, 400), Event("Lunch", 200, 260)]
        how = read(finish((150, 210), (300, 330)), [], events)
        assert how.events == ("Club",) and how.event_min == 50 + 30 + 10

    def test_speed_needs_both_lengths(self) -> None:
        assert read(finish(planned=60, actual=30), [], []).speed == 0.5
        assert read(finish(planned=None, actual=30), [], []).speed is None
        assert read(finish(planned=0, actual=30), [], []).speed is None
        assert read(finish(planned=60, actual=None), [], []).speed is None


class TestWays:
    def how(self, **kw) -> How:
        return How(finish(*kw.pop("worked", ())), kw.pop("speed", None), kw.pop("evening", 0), kw.pop("morning", 0),
                   kw.pop("events", 0))  # fmt: skip

    def test_each_way_past_its_threshold_in_a_fixed_order(self) -> None:
        how = self.how(speed=0.5, evening=15, morning=15, events=15)
        assert how.ways == ("faster", "nights", "mornings", "events")

    def test_just_under_every_threshold_is_daytime_when_timed(self) -> None:
        assert self.how(speed=bp.FASTER, evening=14, morning=14, events=14).ways == ("daytime",)

    def test_sittings_without_a_length_are_daytime(self) -> None:
        assert self.how(worked=((0, 10),)).ways == ("daytime",)

    def test_nothing_recorded_is_untold(self) -> None:
        assert self.how().ways == ("untold",)


def night_how(reach: dict[str, int]) -> How:
    return How(finish(), None, max(reach.values(), default=0), 0, 0, reach)


class TestLaterNights:
    def test_the_median_reach_rounded_up_to_a_quarter_hour(self) -> None:
        found = later_nights([night_how({"mon": 20}), night_how({"tue": 50}), night_how({"wed": 100})], {})
        assert found is not None and found.extra_min == 60  # median 50 → 60
        assert dict(found.margins) == {"mon": 60, "tue": 60, "wed": 60} and found.cases == 3

    def test_margins_grow_from_today_s_and_stop_at_four_hours(self) -> None:
        found = later_nights([night_how({"mon": 90})] * 3, {"mon": 200})
        assert found is not None and dict(found.margins) == {"mon": 240}

    def test_an_evening_already_at_four_hours_is_left_out(self) -> None:
        assert later_nights([night_how({"mon": 90})] * 3, {"mon": 240}) is None

    def test_evenings_come_in_week_order(self) -> None:
        found = later_nights([night_how({"sun": 30}), night_how({"mon": 30}), night_how({"fri": 30})], {})
        assert found is not None and list(found.margins) == ["mon", "fri", "sun"]

    def test_an_evening_reached_under_fifteen_minutes_is_not_grown(self) -> None:
        hows = [night_how({"mon": 30, "tue": 10})] * 3
        found = later_nights(hows, {})
        assert found is not None and list(found.margins) == ["mon"]

    def test_two_finishes_are_not_enough(self) -> None:
        assert later_nights([night_how({"mon": 30})] * 2, {}) is None


def speed_how(speed: float, kind: str = "Reading", scalable: bool = True) -> How:
    return How(finish(kind=kind, scalable=scalable), speed, 0, 0, 0)


class TestSpeeds:
    def test_the_median_share_rounded_up_to_a_twentieth(self) -> None:
        (found,) = speeds([speed_how(0.61), speed_how(0.62), speed_how(0.9)])
        assert (found.kind, found.share, found.cases) == ("Reading", 0.65, 3)

    def test_a_share_already_on_a_twentieth_stays(self) -> None:
        (found,) = speeds([speed_how(0.65)] * 3)
        assert found.share == 0.65  # 0.65 × 20 is 13.000000000000002 in floats

    def test_never_under_half(self) -> None:
        (found,) = speeds([speed_how(0.2)] * 3)
        assert found.share == bp.SHARE_FLOOR

    def test_a_median_at_the_threshold_is_not_faster(self) -> None:
        assert speeds([speed_how(bp.FASTER)] * 3) == []

    def test_lengths_friday_estimated_or_unknown_kinds_are_left_out(self) -> None:
        assert speeds([speed_how(0.5, scalable=False)] * 3) == []
        assert speeds([speed_how(0.5, kind=None)] * 3) == []  # type: ignore[arg-type]

    def test_the_kind_with_most_finishes_comes_first(self) -> None:
        found = speeds([speed_how(0.5, "Reading")] * 3 + [speed_how(0.5, "Assignment")] * 4)
        assert [s.kind for s in found] == ["Assignment", "Reading"]


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


class TestPlannedLate:
    def save_plan(self, app: App, at: int, late: dict[str, float], status: str = "replaced") -> None:
        app.conn.execute(
            "INSERT INTO plans (user_id, created_utc, generation, reason, status, stage_values, solve_seconds, "
            "report) VALUES (1, ?, 0, 'test', ?, '{}', 0, ?)",
            [format_utc(at), status, json.dumps({"late_hours": late})],
        )

    def test_the_first_write_reads_back_the_saved_plans_keeping_each_item_s_worst(self, app: App) -> None:
        self.save_plan(app, app.now_utc - 600, {"7": 2.0})
        self.save_plan(app, app.now_utc - 300, {"7": 1.0, "8": 0.5})
        self.save_plan(app, app.now_utc - 100, {"9": 4.0}, status="preview")  # never your plan
        pl.remember(app.conn, 1, {}, app.now_utc)
        assert pl.planned_late(app.conn, 1) == {7: 2.0, 8: 0.5}

    def test_plans_older_than_the_window_are_not_read_back(self, app: App) -> None:
        self.save_plan(app, app.now_utc - (pl.KEPT_DAYS + 1) * 1440, {"7": 2.0})
        pl.remember(app.conn, 1, {}, app.now_utc)
        assert pl.planned_late(app.conn, 1) == {}

    def test_later_plans_raise_but_never_lower_the_most(self, app: App) -> None:
        pl.remember(app.conn, 1, {7: 1.0}, app.now_utc)
        pl.remember(app.conn, 1, {7: 3.0}, app.now_utc + 60)
        pl.remember(app.conn, 1, {7: 0.5}, app.now_utc + 120)
        assert pl.planned_late(app.conn, 1) == {7: 3.0}
        assert kv_get(app.conn, pl.KEY)["7"]["last"] == format_utc(app.now_utc + 120)

    def test_entries_not_shown_late_for_the_window_are_dropped(self, app: App) -> None:
        pl.remember(app.conn, 1, {7: 1.0}, app.now_utc)
        pl.remember(app.conn, 1, {8: 1.0}, app.now_utc + (pl.KEPT_DAYS + 1) * 1440)
        assert pl.planned_late(app.conn, 1) == {8: 1.0}

    def test_a_plan_with_nothing_late_leaves_the_record_unwritten(self, app: App) -> None:
        kv_set(app.conn, pl.KEY, {"7": {"hours": 1.0, "last": "2020-01-01T00:00Z"}})
        pl.remember(app.conn, 1, {}, app.now_utc)
        assert pl.planned_late(app.conn, 1) == {7: 1.0}  # not pruned: nothing was written


ITEM = Item(title="read ch. 3", amount="fixed", duration_units=8, duration_source="you", min_chunk_units=4)


class TestShortened:
    def test_your_length_is_planned_at_the_share_rounded_up_to_a_quarter_hour(self) -> None:
        out = shortened(ITEM, 0.55)
        assert out.duration_units == 5 and out.min_chunk_units == 4

    def test_the_kind_s_default_length_too(self) -> None:
        assert shortened(replace(ITEM, duration_source="preset"), 0.5).duration_units == 4

    def test_a_sitting_never_needs_more_than_the_whole(self) -> None:
        out = shortened(replace(ITEM, duration_units=4), 0.5)
        assert (out.duration_units, out.min_chunk_units) == (2, 2)

    def test_friday_s_estimates_events_and_open_amounts_are_left_alone(self) -> None:
        for item in (
            replace(ITEM, duration_source="estimate"),
            replace(ITEM, when="fixed"),
            replace(ITEM, amount="open"),
            replace(ITEM, duration_units=None),
        ):
            assert shortened(item, 0.5) == item

    def test_no_share_or_a_whole_one_changes_nothing(self) -> None:
        assert shortened(ITEM, None) == ITEM and shortened(ITEM, 1.0) == ITEM and shortened(ITEM, 0) == ITEM

    def test_never_under_a_quarter_hour(self) -> None:
        assert shortened(replace(ITEM, duration_units=1, min_chunk_units=1), 0.5).duration_units == 1


def test_a_shortened_item_is_its_full_length_again_once_its_work_reaches_the_shortened_one() -> None:
    from friday.planner.cushion import past_shortened

    short = shortened(replace(ITEM, duration_units=28), 0.75)
    assert (short.duration_units, short.full_units) == (21, 28)
    assert past_shortened(short, 20).duration_units == 21  # still within the shortened length
    back = past_shortened(short, 22)  # past it, still open: the rest of the full length is planned
    assert (back.duration_units, back.full_units) == (28, None)
    assert past_shortened(replace(ITEM, duration_units=8), 9) == replace(ITEM, duration_units=8)  # never shortened
