"""What Friday learned never overrules what you said (29 Oct: "make sure that there is guards against any of friday's
learned behaviours and the rules contradicting"). In the planner: your learned morning routine is never planned in
("if it assumes that i have a 45 minute morning routine then how does it give me work at 8am sharp?"), and a night
counts back from an early event you go to (Gym at 7:30 when Friday took you to be up at 8). Weekdays 23:30–07:30."""

from friday.engine.rules.prices import SleepMin
from tests.engine.helpers import at, item, problem

SEVEN = [{"type": "sleep_min", "name": "seven", "params": {"hours": 7.0}}]


def gym(day: int, start: str, minutes: int = 90):  # noqa: ANN201
    return item(
        "commitment", 90 + day, title="Gym", when="fixed", start_utc=at(day, start), end_utc=at(day, start) + minutes
    )


def night(p, day: int):  # noqa: ANN001, ANN201
    return next(n for d, n in p.nights.items() if d.weekday() == day)


def free(p, start: int, end: int) -> list[bool]:  # noqa: ANN001
    """Whether each slot between two moments may hold work."""
    return [not p.core[s] for s in range(p.grid.S) if start <= p.grid.start[s] < end]


def test_the_morning_routine_is_never_planned_in() -> None:
    p = problem([item("chore", 1, duration_units=4)], now=at(1, "06:00"), slots=None, days=2, routine_min={"tue": 45})
    assert night(p, 0).core == (at(1, "00:30"), at(1, "08:15"))  # up at 7:30, ready at 8:15
    assert free(p, at(1, "07:30"), at(1, "08:30")) == [False, False, False, True]


def test_ready_to_work_ends_the_routine() -> None:
    p = problem([item("chore", 1, duration_units=4)], now=at(1, "06:00"), slots=None, days=2, routine_min={"tue": 45},
                woke_utc=at(1, "07:30"), ready_today=True)  # fmt: skip
    assert free(p, at(1, "07:30"), at(1, "08:00")) == [True, True]


def test_a_night_counts_back_from_an_early_event_you_go_to() -> None:
    p = problem([item("chore", 1, duration_units=4), gym(1, "06:30")], extra=SEVEN, now=at(0, "20:00"), slots=None,
                days=2, routine_min={"tue": 30})  # fmt: skip
    assert night(p, 0).wake_utc == at(1, "06:00")  # up at 6 for Gym at 6:30, routine and all
    sleep = next(r for r in p.rules if isinstance(r, SleepMin))
    kept = [bool(sleep.kept[s]) for s in range(p.grid.S) if at(0, "22:30") <= p.grid.start[s] < at(0, "23:30")]
    assert kept == [False, False, True, True]  # the seven hours run from 11pm to 6am


def test_an_event_after_you_re_ready_moves_nothing() -> None:
    p = problem([item("chore", 1, duration_units=4), gym(1, "09:00")], now=at(0, "20:00"), slots=None, days=2,
                routine_min={"tue": 30})  # fmt: skip
    assert night(p, 0).wake_utc == at(1, "07:30")


def test_a_whole_day_event_isn_t_one_to_get_up_for() -> None:
    allday = item("commitment", 70, title="Birthday", when="fixed", start_utc=at(1, "00:00"), end_utc=at(2, "00:00"))
    p = problem([item("chore", 1, duration_units=4), allday], now=at(0, "20:00"), slots=None, days=2)
    assert night(p, 0).wake_utc == at(1, "07:30")
