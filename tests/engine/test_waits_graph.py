"""The graph of what waits for what (engine/waits.py, 23 Nov): a topological order that prefers the earliest deadline
among what's ready, and loops found rather than planned."""

from friday.engine.waits import Waits, loops, topological


def test_nothing_comes_before_what_it_waits_for_and_deadlines_order_the_rest() -> None:
    # essay waits for outline, which waits for reading; quiz waits for nothing. Preferred by deadline: essay first.
    waits = Waits({"essay": ("outline",), "outline": ("reading",), "reading": (), "quiz": ()})
    order, circles = topological(waits, ["essay", "quiz", "outline", "reading"])
    assert order == ["quiz", "reading", "outline", "essay"]  # quiz is ready and preferred; the chain in its order
    assert circles == []


def test_a_loop_is_found_and_what_waits_for_it_is_not_in_it() -> None:
    waits = Waits({"a": ("b",), "b": ("a",), "c": ("a",), "d": ()})
    order, circles = topological(waits, ["a", "b", "c", "d"])
    assert order == ["d"]  # nothing in or behind the loop can be placed
    assert circles == [["a", "b"]]
    assert loops(waits, ["a", "b", "c"]) == [["a", "b"]]


def test_waiting_for_itself_is_a_loop() -> None:
    assert loops(Waits({"a": ("a",)}), ["a"]) == [["a"]]
