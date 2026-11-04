"""Black box: learn/beat_plan.py from what it promises (its docstring), not how it works. Work a plan showed late
and you finished on time is read for where its time came from; what happens in three finishes is offered, never
smaller than half a length, never past a four-hour margin, never shrinking a night.

The week: Monday 19 Oct 2026 in minutes from an arbitrary zero; nights run 00:30 (bedtime 11:30pm and its hour of
margin) to 7:30."""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.learn.beat_plan import Event, Finish, Night, read, summarize

DAY = 1440
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def night(day: int) -> Night:
    """The night beginning on day `day` (0 is Monday): 00:30 to 7:30 the next morning."""
    return Night(WEEKDAYS[day % 7], (day + 1) * DAY + 30, (day + 1) * DAY + 7 * 60 + 30)


def at(day: int, hour: float) -> int:
    return round(day * DAY + hour * 60)


NIGHTS = [night(d) for d in range(-1, 8)]


def essay(*worked: tuple[int, int], planned: int | None = 120, actual: int | None = None, kind: str = "Essay",
          scalable: bool = True, item_id: int = 1) -> Finish:  # fmt: skip
    return Finish(item_id, "essay", kind, planned, actual, worked, scalable)


class TestOneFinish:
    def test_done_in_half_the_time_is_faster(self) -> None:
        assert read(essay(planned=120, actual=60), NIGHTS, []).ways == ("faster",)

    def test_work_at_1am_is_a_later_night(self) -> None:
        how = read(essay((at(1, 0.5), at(1, 2))), NIGHTS, [])  # Tuesday 00:30–2:00: Monday's night
        assert how.ways == ("nights",) and how.reach == {"mon": 90}

    def test_work_before_your_alarm_is_an_early_morning(self) -> None:
        assert read(essay((at(1, 5.5), at(1, 7))), NIGHTS, []).ways == ("mornings",)

    def test_work_through_a_club_meeting_names_it(self) -> None:
        how = read(essay((at(0, 18), at(0, 20))), NIGHTS, [Event("Robotics club", at(0, 18), at(0, 19))])
        assert how.ways == ("events",) and how.events == ("Robotics club",)

    def test_an_afternoon_at_the_planned_pace_is_daytime(self) -> None:
        assert read(essay((at(0, 14), at(0, 16)), actual=120), NIGHTS, []).ways == ("daytime",)

    def test_nothing_recorded_is_untold(self) -> None:
        assert read(essay(), NIGHTS, []).ways == ("untold",)

    def test_work_right_up_to_your_bedtime_s_margin_is_not_a_late_night(self) -> None:
        assert read(essay((at(0, 22), at(1, 0.5))), NIGHTS, []).ways == ("daytime",)

    def test_several_ways_at_once_are_all_named(self) -> None:
        how = read(essay((at(1, 0.5), at(1, 1.5)), actual=60), NIGHTS, [])
        assert set(how.ways) == {"faster", "nights"}


def late_nights(n: int, hours_past: float = 1.0) -> list:
    """`n` finishes, each worked from 00:30 on its own evening for `hours_past`."""
    return [read(essay((at(d, 24.5), at(d, 24.5 + hours_past)), item_id=d), NIGHTS, []) for d in range(n)]


class TestPatterns:
    def test_three_late_nights_offer_those_evenings_a_later_night(self) -> None:
        found = summarize(late_nights(3), {d: 60 for d in WEEKDAYS})
        assert found.nights is not None
        assert dict(found.nights.margins) == {"mon": 120, "tue": 120, "wed": 120}
        assert found.counts == {"nights": 3}

    def test_two_late_nights_offer_nothing(self) -> None:
        assert summarize(late_nights(2), {}).nights is None

    def test_reading_done_in_half_its_length_three_times_is_offered_at_half(self) -> None:
        hows = [read(essay(planned=60, actual=30, kind="Reading", item_id=n), NIGHTS, []) for n in range(3)]
        (offer,) = summarize(hows, {}).speeds
        assert (offer.kind, offer.share, offer.cases) == ("Reading", 0.5, 3)

    def test_lengths_friday_estimated_itself_are_not_offered(self) -> None:
        hows = [read(essay(planned=60, actual=30, scalable=False), NIGHTS, []) for _ in range(5)]
        assert summarize(hows, {}).speeds == []

    def test_kinds_are_judged_apart(self) -> None:
        fast = [read(essay(planned=60, actual=30, kind="Reading"), NIGHTS, []) for _ in range(2)]
        slow = [read(essay(planned=60, actual=30, kind="Essay"), NIGHTS, []) for _ in range(2)]
        assert summarize(fast + slow, {}).speeds == []

    def test_nothing_finished_offers_nothing(self) -> None:
        found = summarize([], {})
        assert (found.nights, found.speeds, dict(found.counts)) == (None, [], {})


sittings = st.lists(
    st.tuples(st.integers(-DAY, 8 * DAY), st.integers(1, 6 * 60)).map(lambda t: (t[0], t[0] + t[1])), max_size=6
)
finishes = st.builds(
    essay,
    planned=st.one_of(st.none(), st.integers(15, 600)),
    actual=st.one_of(st.none(), st.integers(1, 900)),
    kind=st.sampled_from(["Essay", "Reading"]),
    scalable=st.booleans(),
).flatmap(lambda f: sittings.map(lambda w: Finish(f.item_id, f.title, f.kind, f.planned_min, f.actual_min,
                                                  tuple(w), f.scalable)))  # fmt: skip
margins = st.dictionaries(st.sampled_from(WEEKDAYS), st.integers(0, 240))


class TestAlways:
    @settings(max_examples=150, deadline=None)
    @given(st.lists(finishes, max_size=12), margins)
    def test_offers_stay_in_bounds_and_never_shrink_a_night(self, found: list[Finish], now: dict[str, int]) -> None:
        summary = summarize([read(f, NIGHTS, []) for f in found], now)
        if summary.nights is not None:
            assert summary.nights.cases >= 3 and summary.nights.extra_min % 15 == 0
            for evening, margin in summary.nights.margins.items():
                assert now.get(evening, 0) < margin <= 240
        for speed in summary.speeds:
            assert 0.5 <= speed.share < 0.85 and speed.cases >= 3
            assert round(speed.share * 20, 6) == round(speed.share * 20)

    @settings(max_examples=150, deadline=None)
    @given(finishes)
    def test_every_finish_has_a_way_and_minutes_never_exceed_the_work(self, found: Finish) -> None:
        how = read(found, NIGHTS, [Event("Lecture", at(0, 10), at(0, 11))])
        assert how.ways and set(how.ways) <= {"faster", "nights", "mornings", "events", "daytime", "untold"}
        worked = sum(hi - lo for lo, hi in found.worked)
        assert 0 <= how.evening_min + how.morning_min <= worked and 0 <= how.event_min <= worked

    @settings(max_examples=100, deadline=None)
    @given(st.lists(finishes, max_size=8), margins)
    def test_the_order_of_finishes_doesnt_change_the_offers(self, found: list[Finish], now: dict[str, int]) -> None:
        hows = [read(f, NIGHTS, []) for f in found]
        forward, backward = summarize(hows, now), summarize(hows[::-1], now)
        assert forward.nights == backward.nights and forward.speeds == backward.speeds
        assert dict(forward.counts) == dict(backward.counts)
