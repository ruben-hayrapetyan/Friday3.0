"""A change list names only real changes (Friday Notes, 23 Nov: Pace's "9 items change" listed "HW 12: Sun 19:45 →
Sun 19:45" and "Post-lab 10: Sat 11:15 → Sat 11:15"). The same time cut into sessions another way isn't a change:
sessions back to back are one stretch when plans are compared."""

from friday.planner.assemble import per_item
from friday.planner.snapshot import BlockRow


def test_back_to_back_sessions_are_one_stretch() -> None:
    cut = per_item([BlockRow(1, 1185, 1215), BlockRow(1, 1215, 1260)])
    whole = per_item([BlockRow(1, 1185, 1260)])
    assert cut == whole == {1: [(1185, 1260)]}


def test_sessions_with_a_gap_stay_apart() -> None:
    assert per_item([BlockRow(1, 1185, 1215), BlockRow(1, 1230, 1260)]) == {1: [(1185, 1215), (1230, 1260)]}
