"""moved_rule, from inside (5 Nov: "change jasons bday to nov 6 yearly"): which parts of a rule follow a moved day."""

from datetime import date

from friday.core.recurrence import moved_rule

THU, FRI = date(2026, 11, 5), date(2026, 11, 6)
MON, TUE, WED = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)


def test_a_rule_naming_no_day_is_kept_as_it_is_since_its_first_date_says_the_day() -> None:
    assert moved_rule("FREQ=YEARLY", THU, FRI) == "FREQ=YEARLY"
    assert moved_rule("FREQ=WEEKLY;INTERVAL=2", THU, FRI) == "FREQ=WEEKLY;INTERVAL=2"


def test_the_moved_weekday_is_replaced_and_the_others_stay() -> None:
    assert moved_rule("FREQ=WEEKLY;BYDAY=MO,WE", MON, TUE) == "FREQ=WEEKLY;BYDAY=TU,WE"
    assert moved_rule("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", MON, date(2026, 11, 13)) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR"


def test_moving_onto_a_weekday_it_has_already_or_from_one_it_lacks_cant_be_said() -> None:
    assert moved_rule("FREQ=WEEKLY;BYDAY=MO,WE", MON, WED) is None
    assert moved_rule("FREQ=WEEKLY;BYDAY=TU", MON, WED) is None
    assert moved_rule("FREQ=MONTHLY;BYDAY=2MO", MON, TUE) is None  # the second Monday


def test_a_month_day_and_a_month_follow_the_new_date() -> None:
    assert moved_rule("FREQ=MONTHLY;BYMONTHDAY=5", THU, FRI) == "FREQ=MONTHLY;BYMONTHDAY=6"
    assert moved_rule("FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=5", THU, date(2026, 12, 1)) == (
        "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=1"
    )
    assert moved_rule("FREQ=MONTHLY;BYMONTHDAY=5,20", THU, FRI) is None


def test_set_positions_and_year_days_cant_be_moved() -> None:
    assert moved_rule("FREQ=MONTHLY;BYDAY=MO,TU;BYSETPOS=-1", MON, TUE) is None
    assert moved_rule("FREQ=YEARLY;BYYEARDAY=309", THU, FRI) is None


def test_the_end_moves_later_with_every_time_but_not_with_one_weekday_of_several() -> None:
    assert moved_rule("FREQ=WEEKLY;UNTIL=20261210T235959", THU, FRI) == "FREQ=WEEKLY;UNTIL=20261211T235959"
    assert moved_rule("FREQ=WEEKLY;BYDAY=MO;UNTIL=20261207T235959", MON, TUE) == (
        "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261208T235959"
    )
    assert moved_rule("FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261209T235959", MON, TUE) == (
        "FREQ=WEEKLY;BYDAY=TU,WE;UNTIL=20261209T235959"
    )
    assert moved_rule("FREQ=WEEKLY;UNTIL=20261210T235959", FRI, THU) == "FREQ=WEEKLY;UNTIL=20261210T235959"
