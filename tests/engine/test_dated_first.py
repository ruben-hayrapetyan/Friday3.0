"""Work that's due before work that isn't (29 Oct: "why is friday scheduling 'Email professors for research
opportunities' that doesn't have a deadline over something that has one but that hasn't been scheduled"). Three causes,
each pinned here: the annealer never took an undated task's time for dated work it had left out; undated work's
place was held in the wellbeing stage, above soft lateness; and soft lateness had been learned down to a thirtieth."""

from friday.engine.compile import compile_problem
from friday.engine.problem import NEVER_LEARNED
from friday.engine.scheduler import dated_first, stage_values
from tests.engine.helpers import MON10, item, problem

RULES = ["soft_late", "unscheduled", "minimize_changes"]


def undated_and_due(**build):  # noqa: ANN201
    """An hour of room; an undated chore holding it from the last plan; a reading due at its end with none."""
    chore = item("chore", 1, duration_units=4, shape="split", min_chunk_units=1)
    reading = item("chore", 2, duration_units=4, shape="split", min_chunk_units=1, due_utc=MON10 + 60, firmness="soft")
    return problem([chore, reading], RULES, slots=4, current={1: [(MON10, MON10 + 60)]}, **build)


def test_the_undated_task_s_time_goes_to_the_reading_with_none() -> None:
    p = undated_and_due()
    c = compile_problem(p)
    owner = c.owner_from_plan({"item:1": (0, 1, 2, 3), "item:2": ()})
    after = dated_first(c, owner)
    assert c.plan_from_owner(after) == {"item:1": (), "item:2": (0, 1, 2, 3)}
    assert stage_values(c, after) < stage_values(c, owner)


def test_nothing_changes_when_the_dated_work_has_its_time() -> None:
    p = undated_and_due()
    c = compile_problem(p)
    owner = c.owner_from_plan({"item:1": (), "item:2": (0, 1, 2, 3)})
    assert (dated_first(c, owner) == owner).all()


def test_a_pin_on_the_undated_task_keeps_its_time() -> None:
    from friday.planner.build import Pin  # noqa: PLC0415

    p = undated_and_due(pins=[Pin(1, MON10, MON10 + 60, "preferred")])
    c = compile_problem(p)
    owner = c.owner_from_plan({"item:1": (0, 1, 2, 3), "item:2": ()})
    assert c.plan_from_owner(dated_first(c, owner))["item:1"] == (0, 1, 2, 3)


def test_soft_lateness_is_never_learned_from_your_moves() -> None:
    assert "soft_late" in NEVER_LEARNED
    p = undated_and_due(multipliers={"soft_late": 0.03})
    assert (
        next(r for r in p.rules if r.name == "soft_late").effective_weight
        == next(r for r in undated_and_due().rules if r.name == "soft_late").effective_weight
    )
