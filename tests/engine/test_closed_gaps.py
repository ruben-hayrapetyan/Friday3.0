"""Empty time between two pieces of work, from what you see (5 Nov: "why does it leave a gap between the second 17.3
and what came before it"): a piece moves up to meet the work before it when that costs nothing more; the room you
asked for, time the work can't have, and room after an event stay."""

from friday.engine.compile import compile_problem
from friday.engine.evaluate import evaluate
from friday.engine.gaps import closed_gaps
from friday.engine.problem import STAGES
from friday.engine.scheduler import schedule
from tests.engine.configs import fast
from tests.engine.helpers import at, item, plan, problem

EVENING = at(0, "21:30")  # slots 0–7: 21:30 to 23:30, bedtime 23:30


def evening(rules=("late_night",), extra=(), **build):  # noqa: ANN001, ANN201
    """A problem set and a reading due tomorrow, from 21:30."""
    problem_set = item("assignment", 1, duration_units=4, due_utc=at(1, "09:00"))
    reading = item("reading", 2, duration_units=2, due_utc=at(1, "09:00"), **build.pop("reading", {}))
    return problem([problem_set, reading, *build.pop("more", [])], rules, extra, now=EVENING, slots=8, **build)


def closed(p, placed):  # noqa: ANN001, ANN201
    c = compile_problem(p)
    return c, c.plan_from_owner(closed_gaps(c, c.owner_from_plan(placed)))


def test_the_reading_after_a_quarter_hour_gap_late_at_night_moves_up_to_meet_the_problem_set() -> None:
    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))  # the problem set to 22:30, the reading from 22:45
    p = evening()
    c, after = closed(p, gap)
    assert after == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))
    assert evaluate(p, after).rule_totals["late_night"] < evaluate(p, gap).rule_totals["late_night"]


def test_pieces_close_up_one_after_another() -> None:
    p = evening(rules=(), more=[item("chore", 3, duration_units=1, due_utc=at(1, "09:00"))])
    _, after = closed(p, plan(item_1=(0, 1), item_2=(3, 4), item_3=(6,)))
    assert after == plan(item_1=(0, 1), item_2=(2, 3), item_3=(4,))


def test_a_break_you_set_between_blocks_keeps_the_gap() -> None:
    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))
    breaks = [dict(type="buffer", name="breathing_room", weight=3, params=dict(minutes="15m"))]
    _, after = closed(evening(extra=breaks), gap)
    assert after == gap


def test_a_gap_the_last_plan_had_closes_though_keeping_the_plan_steady_is_a_rule() -> None:
    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))
    p = evening(rules=("late_night", "minimize_changes"),
                current={1: [(EVENING, EVENING + 60)], 2: [(EVENING + 75, EVENING + 105)]})  # fmt: skip
    _, after = closed(p, gap)
    assert after == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))


def test_time_the_reading_can_t_have_stays_empty() -> None:
    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))
    _, after = closed(evening(reading={"release_utc": EVENING + 75}), gap)  # open from 22:45
    assert after == gap


def test_room_after_an_event_and_at_the_start_of_the_time_stays() -> None:
    talk = item("commitment", 3, title="Talk", when="fixed", start_utc=EVENING, end_utc=EVENING + 30)
    _, after = closed(evening(rules=(), more=[talk]), plan(item_1=(3, 4, 5, 6), item_2=()))
    assert after == plan(item_1=(3, 4, 5, 6), item_2=())  # after the talk, 22:00 free before it
    _, after = closed(evening(rules=()), plan(item_1=(2, 3, 4, 5), item_2=()))
    assert after == plan(item_1=(2, 3, 4, 5), item_2=())  # nothing before it to meet


def test_a_pinned_piece_stays_where_you_put_it() -> None:
    from friday.planner.build import Pin  # noqa: PLC0415

    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))
    _, after = closed(evening(pins=[Pin(2, EVENING + 75, EVENING + 105, "preferred")]), gap)
    assert after["item:2"] == (5, 6)


def test_closing_gaps_never_costs_more_in_any_stage_than_the_steady_plan_did() -> None:
    gap = plan(item_1=(0, 1, 2, 3), item_2=(5, 6))
    p = evening(rules=("late_night", "energy", "finish_early", "chunk_cost"))
    _, after = closed(p, gap)
    before, now = evaluate(p, gap).stage_values, evaluate(p, after).stage_values
    assert all(now[s] <= before[s] for s in STAGES)


def test_a_warm_replan_from_a_plan_with_a_gap_returns_it_closed() -> None:
    # Only keeping the plan steady held the reading: the plan you had stood, gap and all, until this pass.
    p = evening(rules=("minimize_changes",), current={1: [(EVENING, EVENING + 60)], 2: [(EVENING + 75, EVENING + 105)]})
    result = schedule(p, fast(), warm=True)
    assert result.plan == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))
