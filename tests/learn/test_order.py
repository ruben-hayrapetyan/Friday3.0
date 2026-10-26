"""The order you work in: kinds you start ahead of what's planned, learned and offered as an order to plan in."""

from friday.learn.order import Choice, before, reordered, suggest


def test_a_kind_chosen_over_another_most_times_is_offered_first() -> None:
    choices = [Choice("Reading", "Assignment")] * 4 + [Choice("Assignment", "Reading")]
    found = suggest(choices, [], [])
    assert found is not None and (found.first, found.then, found.chose, found.of) == ("Reading", "Assignment", 4, 5)


def test_too_few_or_too_mixed_or_already_so_or_refused_is_not_offered() -> None:
    assert suggest([Choice("Reading", "Assignment")] * 3, [], []) is None  # three times isn't a habit yet
    mixed = [Choice("Reading", "Assignment")] * 4 + [Choice("Assignment", "Reading")] * 2
    assert suggest(mixed, [], []) is None  # 4 of 6 is under three in four
    clear = [Choice("Reading", "Assignment")] * 5
    assert suggest(clear, ["Reading", "Assignment"], []) is None  # already planned that way
    assert suggest(clear, [], [("Reading", "Assignment")]) is None  # you said no
    assert suggest([Choice("Reading", "Reading")] * 6, [], []) is None  # one kind over itself says nothing


def test_the_order_puts_the_kind_just_ahead_of_the_other() -> None:
    assert reordered(["Assignment", "Exam prep", "Reading"], "Reading", "Assignment") == [
        "Reading", "Assignment", "Exam prep"]  # fmt: skip
    assert reordered(["Exam prep"], "Reading", "Assignment") == ["Exam prep", "Reading", "Assignment"]
    assert before(["Reading", "Assignment"], "Reading", "Assignment")
    assert before(["Reading"], "Reading", "Assignment") and not before([], "Reading", "Assignment")
