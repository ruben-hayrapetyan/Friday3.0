"""personal's start for an overloaded week (COMBINED.md 54): Moore–Hodgson keeps as many tasks on time as can be."""

from friday.engine.compile import compile_problem
from friday.engine.construct import fewest_late_order
from tests.engine.helpers import MON10, item, problem


def test_the_long_task_is_set_aside_so_the_short_ones_are_on_time() -> None:
    # 8 slots (2 h) of room; a 6-unit task due first, then two 2-unit tasks due at the end
    long_ = item("assignment", 1, duration_units=6, due_utc=MON10 + 90, importance=3)
    short_a = item("assignment", 2, duration_units=2, due_utc=MON10 + 120, importance=3)
    short_b = item("assignment", 3, duration_units=2, due_utc=MON10 + 120, importance=3)
    c = compile_problem(problem([long_, short_a, short_b], ["late_work", "late_tasks"]))
    order = [c.keys[i] for i in fewest_late_order(c)]
    assert order == ["item:2", "item:3", "item:1"]


def test_nothing_is_set_aside_when_everything_fits() -> None:
    a = item("assignment", 1, duration_units=2, due_utc=MON10 + 60, importance=3)
    b = item("assignment", 2, duration_units=2, due_utc=MON10 + 120, importance=3)
    c = compile_problem(problem([a, b], ["late_work"]))
    assert [c.keys[i] for i in fewest_late_order(c)] == ["item:1", "item:2"]
