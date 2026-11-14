"""Work one after another, from what you see (14 Nov: "there is a large chunk of time that doesn't make any sense why
there is that kind of a gap between events. it should generally be the case, unless specified by a rule, [that work
is] scheduled one after another"): a night the work has to cut short is cut short once, its work straight on rather
than spread through it; and what runs by itself leaves you free beside it ("why is there nothing being scheduled
while laundry is running?")."""

from friday.engine.scheduler import schedule
from tests.engine.configs import fast
from tests.engine.helpers import at, item, problem

# 8.5 hours of sleep before a 7:30 wake: asleep by 11pm, and bedtime's margin is the wall from 00:30.
SLEEP = {"type": "sleep_min", "name": "sleep", "params": {"hours": 8.5, "price": 40.0}}
COURSES = {"type": "same_course", "name": "course", "weight": 2}


def blocks(plan: dict[str, tuple[int, ...]]) -> list[tuple[int, int]]:
    """Every run of slots in the plan, whoever's, as (first, last)."""
    slots = sorted(s for placed in plan.values() for s in placed)
    out: list[tuple[int, int]] = []
    for s in slots:
        if out and s == out[-1][1] + 1:
            out[-1] = (out[-1][0], s)
        else:
            out.append((s, s))
    return out


def test_two_courses_a_short_night_must_take_go_straight_on() -> None:
    """From 10:30pm, an hour of math and half an hour of chemistry due at 00:30: the night is short either way, and a
    quarter hour between them (no switch straight on) used to cost nothing, since the sleep rule priced only the
    quarter hours worked. Only the rules named: a steep late-night price would hide it (yours is all but off)."""
    math = item("assignment", 1, title="Math 1920 HW", duration_units=4, due_utc=at(1, "00:30"))
    chem = item("assignment", 2, title="Chem 2090 PS", duration_units=2, due_utc=at(1, "00:30"))
    p = problem([math, chem], ["late_work"], [SLEEP, COURSES], now=at(0, "22:30"), slots=8)
    result = schedule(p, fast())
    assert result.evaluation.deadline_misses == []
    assert blocks(result.plan) == [(0, 5)]  # 10:30pm to midnight, no gap


def test_a_broken_night_takes_no_more_work_than_it_must() -> None:
    """The problem set due at 00:30 takes the night; the reading due Wednesday has Tuesday evening free, and goes
    there, not into the rest of a night already short."""
    problem_set = item("assignment", 1, duration_units=6, due_utc=at(1, "00:30"))
    reading = item("reading", 2, duration_units=2, due_utc=at(2, "09:00"))
    busy = item("commitment", 3, title="Work shift", when="fixed", start_utc=at(1, "08:00"), end_utc=at(1, "19:00"))
    p = problem([problem_set, reading, busy], ["late_work"], [SLEEP], now=at(0, "22:30"), slots=None, days=2)
    result = schedule(p, fast())
    night = [s for s in result.plan["item:2"] if p.grid.start[s] < at(1, "07:30")]
    assert night == []
    assert result.evaluation.deadline_misses == []


def test_work_goes_on_while_something_runs_by_itself() -> None:
    """Laundry needs you for its first quarter hour and runs an hour and three quarters; the only time left for an
    hour's reading is while it runs, and nothing keeps the reading from it."""
    laundry = item(
        "chore", 1, title="Laundry", background=True, duration_units=8, due_utc=at(0, "21:00"), firmness="hard"
    )
    reading = item("reading", 2, duration_units=4, due_utc=at(0, "21:00"))
    rule = {"type": "runs_while_working", "name": "runs", "params": {"price": "forbid"}}
    p = problem([laundry, reading], ["late_work", "unscheduled"], [rule], now=at(0, "19:00"), slots=8)
    assert p.items["item:1"].runs_units == 7
    result = schedule(p, fast())
    assert result.plan["item:1"] == (0,)
    assert len(result.plan["item:2"]) == 4 and min(result.plan["item:2"]) >= 1  # beside the running laundry
    assert result.evaluation.deadline_misses == []
