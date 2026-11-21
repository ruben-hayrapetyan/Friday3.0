"""Work in a window of slots, as the rules that keep travel time and buffers clear measure it (20 Nov: a user's plans
took minutes; asking every item about every slot of every window was 4.3 million questions a plan for 330 items).
Each slot's items are listed once: the same terms, in the same order, without asking the others."""

from friday.engine.rules import BuildContext
from tests.engine.helpers import item, problem


class Counted(frozenset):
    asked = 0

    def __contains__(self, slot: object) -> bool:
        Counted.asked += 1
        return super().__contains__(slot)


def made() -> BuildContext:
    found = problem([item("assignment", n) for n in range(1, 41)], slots=None, days=3)
    return BuildContext(found)


def test_the_same_terms_in_the_same_order_as_asking_every_item() -> None:
    ctx = made()
    every = list(ctx.problem.items.values())
    some = every[::3]
    for start in range(0, ctx.grid.S - 4, 7):
        window = range(start, start + 4)
        for among in (None, some, every):
            asked = ctx.busy_units_asking(window, every if among is None else among)
            assert ctx.busy_units(window, among).terms == asked.terms
            assert list(ctx.busy_units(window, among).terms) == list(asked.terms)


def test_a_window_asks_no_item_about_its_slots() -> None:
    ctx = made()
    for found in ctx.problem.items.values():
        found.allowed_set = Counted(found.allowed_set)
    ctx.allowed_at()  # the index, made once per plan
    Counted.asked = 0
    for start in range(0, ctx.grid.S - 2):
        ctx.busy_units(range(start, start + 2))
    assert Counted.asked == 0
