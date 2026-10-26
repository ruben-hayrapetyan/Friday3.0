"""Categories, the filter and what counts as busy, as personal's Mac app had them (COMBINED.md 17, 28)."""

from friday.core.calendars import (
    BusySettings,
    Category,
    CategorySettings,
    EventFilter,
    calendar_counts,
    category_of,
    is_filtered,
    left_out,
)

RULES = CategorySettings(
    categories=(
        Category(name="Professor office hours", slug="faculty", color="sapgreen", pattern=r"office hours — prof"),
        Category(name="Office hours & advising", slug="advising", color="green", pattern="office hours|advising"),
        Category(name="Classes", slug="class", color="blue", pattern=r"\b(lec|disc|lab)\b"),
    ),
    filter=EventFilter(label="TA & Advising Hours", pattern="office hours|drop.?in", except_=("faculty",)),
)


def test_the_first_category_that_matches_the_title_wins() -> None:
    assert category_of("MATH 1920 Office Hours — Prof. Strong", RULES).slug == "faculty"
    assert category_of("CS 2110 Office Hours", RULES).slug == "advising"
    assert category_of("CS 2110 Lec", RULES).slug == "class"
    assert category_of("Dinner", RULES) is None


def test_the_filter_spares_the_categories_it_excepts() -> None:
    assert is_filtered("CS 2110 Office Hours", RULES)
    assert is_filtered("Chem drop-in", RULES)
    assert not is_filtered("MATH 1920 Office Hours — Prof. Strong", RULES)
    assert not is_filtered("CS 2110 Lec", RULES)


def test_a_broken_pattern_matches_nothing() -> None:
    broken = CategorySettings(categories=(Category(name="Bad", color="red", pattern="(unclosed"),))
    assert category_of("anything (unclosed", broken) is None


def test_room_bookings_dont_count_until_you_count_them() -> None:
    assert not calendar_counts("Library Rooms", BusySettings())
    assert calendar_counts("Library Rooms", BusySettings(calendars={"Library Rooms": True}))
    assert calendar_counts("Classes", BusySettings())
    assert not calendar_counts("Classes", BusySettings(calendars={"Classes": False}))


def test_events_left_out_of_planning_say_why() -> None:
    busy = BusySettings()
    assert left_out("Problem Set 8 due", "Classes", False, RULES, busy) == "reminder"
    assert left_out("Applications deadline", "Personal", False, RULES, busy) == "reminder"
    assert left_out("Thesis deadline check-in with advisor", "Personal", False, RULES, busy) is None
    assert left_out("Meeting: project due date review", "Personal", False, RULES, busy) is None
    assert left_out("Lunch with Sam", "Personal", True, RULES, busy) == "free"
    assert left_out("CS 2110 Office Hours", "Classes", False, RULES, busy) == "filtered"
    assert left_out("Study room 3", "Library Rooms", False, RULES, busy) == "calendar"
    assert left_out("CS 2110 Lec", "Classes", False, RULES, busy) is None
    counted = BusySettings(count_filtered=True, count_free=True, count_reminders=True)
    assert left_out("CS 2110 Office Hours", "Classes", True, RULES, counted) is None
