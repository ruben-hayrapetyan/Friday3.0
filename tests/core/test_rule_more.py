"""Rules read by their kinds' words once the grammar can't (core/rule_more.py; 8 Nov). Glass box: each reader on the
sentence as the grammar hands it over, what it takes and what it leaves. Black box: sentences through `read`, as the
Rules box reads them, with those that must still go to the AI. The whole system: a rule said a new way, added, and
the plan following it (tests/commands/test_rules_said_new_ways.py)."""

import pytest

from friday.core import rule_more
from friday.core.rule_text import read


def test_pace_takes_days_and_paces_from_any_clause_and_fills_the_rest_of_the_week() -> None:
    r = rule_more.read_pace(" on saturdays i can grind , on sundays go easy , rest of the week just normal ")
    assert r and dict(r.paces or ()) == {"sat": "Push", "sun": "Easy"} | dict.fromkeys(
        ("mon", "tue", "wed", "thu", "fri"), "Normal"
    )
    r = rule_more.read_pace(" go light on the days i have choir , which is tues and thurs ")
    assert r and r.paces == (("tue", "Easy"), ("thu", "Easy"))


def test_pace_leaves_parts_of_days_kinds_of_work_and_one_offs() -> None:
    others = (
        " thursday afternoons could be lighter ",  # part of a day: lighter free time
        " only schedule light stuff on fridays ",  # a kind of work on a day
        " push my dentist appt to next tuesday ",  # a one-off move
        " a pace with a time: easy on fridays after 5pm ",
    )
    for said in others:
        assert rule_more.read_pace(said) is None, said


def test_a_pace_without_its_days_or_days_without_a_pace_is_not_read() -> None:
    assert rule_more.read_pace(" go easy , i'm tired ") is None
    assert rule_more.read_pace(" mondays and tuesdays ") is None


def test_ahead_names_the_event_left_once_the_condition_and_its_verbs_go() -> None:
    r = rule_more.read_ahead(" book club is an only-if-im-ahead thing ")
    assert r and r.events == ("book club",)
    r = rule_more.read_ahead(" never go to happy hour unless i'm ahead ")
    assert r and r.events == ("happy hour",)
    assert rule_more.read_ahead(" i like going to the big friday night party with friends if i'm ahead ") is None


def test_deadlines_need_lateness_and_something_against_it_and_not_another_kinds_words() -> None:
    assert rule_more.read_deadlines(" no late homework . strictly ")
    assert rule_more.read_deadlines(" i'd rather work extra than submit anything late ")
    assert rule_more.read_deadlines(" no late nights ") is None  # a late night isn't late work
    assert rule_more.read_deadlines(" late quizzes don't count so skip the prep ") is None  # pointless late
    assert rule_more.read_deadlines(" never steal my lunch break for deadlines ") is None  # a meal kept


def test_meals_learned_and_kept_are_told_apart_by_their_words() -> None:
    learned = rule_more.read_meals_learned(" idk when i eat lunch , just learn it from my week ")
    assert learned and learned.kind == "meals_learned" and learned.events == ("lunch",)
    kept = rule_more.read_meals_kept(" food > work . don't drop my meals when things get busy ")
    assert kept and kept.kind == "meals_kept" and kept.events == ("breakfast", "lunch", "dinner")
    assert rule_more.read_meals_kept(" lunch before 1pm ") is None  # a meal's window, the grammar's


def test_after_strips_the_asking_and_refuses_meals_negations_and_whole_days() -> None:
    r = rule_more.read_after(" go to the gym straight after work ")
    assert r and (r.subject, r.event) == ("gym", "work")
    r = rule_more.read_after(" after soccer , do reading ")
    assert r and (r.subject, r.event) == ("reading", "soccer")
    for said in (
        " piano practice right after dinner ",
        " nothing right after the gym ",
        " easy week after spring break ",
    ):
        assert rule_more.read_after(said) is None, said


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("fridays: easy. saturdays: push. sundays: normal", "pace"),
        ("no late homework. strictly.", "deadlines"),
        ("book club is an only-if-im-ahead thing", "ahead"),
        ("fill the cracks in my schedule with little to-dos", "fit_gaps"),
        ("slow uploads can run while i do other work, just not during class", "runs_while_working"),
        ("figure out my eating pattern on ur own", "meals_learned"),
        ("go to the gym straight after work", "after"),
    ],
)
def test_a_rule_said_a_new_way_reads_without_the_ai(text: str, kind: str) -> None:
    reading, _ = read(text)
    assert reading and reading.kind == kind


@pytest.mark.parametrize(
    "text",
    [
        "no work right after practice, I'm dead",  # not after an event: no such rule
        "front-load the week so friday is light",  # a week's shape
        "push my dentist appt to next tuesday",  # a one-off move
        "don't plan reading responses once they're overdue",  # pointless when late: a setting
        "readings as late as possible but problem sets 2 days early",  # two rules
    ],
)
def test_what_isnt_one_rule_friday_has_still_goes_to_the_ai(text: str) -> None:
    assert read(text)[0] is None


def test_window_direction_comes_from_the_cue_and_the_negation() -> None:
    assert rule_more.direction(" nite cutoff is 10 ", False) == "before"
    assert rule_more.direction(" earliest i'm willing to crack a book is 8 ", False) == "after"
    assert rule_more.direction(" dont gimme anything til 10:30 ", True) == "after"  # nothing until then
    assert rule_more.direction(" work until 10 ", False) == "before"
    assert rule_more.direction(" nothing past 9:40pm ", True) == "before"


def test_a_bare_hour_that_ends_the_day_is_the_evening() -> None:
    assert rule_more.clock_of("10", "before") == "22:00" and rule_more.clock_of("10", "after") == "10:00"
    assert rule_more.clock_of("5", None) == "17:00" and rule_more.clock_of("9:30am", "before") == "09:30"


def test_a_subject_is_what_is_left_or_nothing_when_the_words_tell_of_the_person() -> None:
    assert rule_more.subject_left(" mentally heavy stuff ") == "deep work"
    assert rule_more.subject_left(" cramming for exams ") == "exam prep"
    assert rule_more.subject_left(" problem sets ") == "problem sets"
    assert rule_more.subject_left(" ") == "work"
    assert rule_more.subject_left(" i bartend ") is None


@pytest.mark.parametrize(
    ("text", "rel", "at", "until", "days"),
    [
        ("nothing on the calendar after 9:40pm thx", "before", "21:40", None, None),
        ("M–F: studying ends at 9:45pm", "before", "21:45", None, ("mon", "tue", "wed", "thu", "fri")),
        ("pls nothing past a quarter to ten, i'm a grandpa", "before", "21:45", None, None),
        ("dont gimme anything til 1030", "after", "10:30", None, None),
        ("studying happens 0830-1630 and not outside it", "between", "08:30", "16:30", None),
    ],
)
def test_a_window_said_a_new_way_reads_with_its_times_and_days(text: str, rel: str, at: str, until, days) -> None:  # noqa: ANN001
    reading, _ = read(text)
    assert reading and reading.kind == "window"
    assert (reading.rel, reading.at, reading.until, reading.days) == (rel, at, until, days)


@pytest.mark.parametrize(
    "text",
    [
        "no work during movie night on thursdays",  # an event's name, not the night
        "always eat lunch, no matter how behind I am",  # "am" isn't the morning (a meal kept, read whole)
        "duolingo 15 min every morning",  # a routine to add
        "I have class MWF 9-10:15",  # an event
        "friday night is the only night I'll work past 10:30",  # an exception Friday can't say as a window
    ],
)
def test_what_only_looks_like_a_window_isnt_read_as_one(text: str) -> None:
    reading, _ = read(text)
    assert reading is None or reading.kind != "window"


def test_days_pieces_must_agree_and_a_reason_without_days_is_dropped() -> None:
    r = rule_more.read_days(" sat: off. sun: off. ")
    assert r and r.rel == "on" and set(r.days or ()) == {"mon", "tue", "wed", "thu", "fri"}
    r = rule_more.read_days(" orgo is a no-go on sundays ")
    assert r and r.subject == "orgo" and "sun" not in (r.days or ())
    r = rule_more.read_days(" don't make me study on the weekends, i work retail ")
    assert r and r.rel == "on" and set(r.days or ()) == {"mon", "tue", "wed", "thu", "fri"}
    assert rule_more.read_days(" thurs only ") is None  # names nothing
    assert rule_more.read_days(" tuesdays are for cs only ") is None  # one kind kept to a day: no such rule


def test_cap_needs_an_amount_a_day_and_a_limit_word() -> None:
    r = rule_more.read_cap(" i tap out after 5.5 hours a day ")
    assert r and (r.subject, r.amount) == ("work", 5.5)
    assert rule_more.read_cap(" 40 min of violin a day or my wrist hurts ") is None  # a minimum, maybe
    assert rule_more.read_cap(" my weekly limit is 30 hrs total ") is None  # a week's cap: no such rule
    assert rule_more.read_cap(" max 2 hours of orgo a day, and only on weekdays ") is None  # two rules


def test_early_turns_hours_and_weeks_into_days_and_finds_what_them_is() -> None:
    assert (r := rule_more.read_early(" lab reports: aim to have them ready 48 hours ahead ")) and r.amount == 2.0
    r = rule_more.read_early(" never leave essays to the last day, finish them 1 day early ")
    assert r and (r.subject, r.amount) == ("essays", 1.0)
    assert rule_more.read_early(" start lab reports a week before due ") is None  # starting early: no such rule


def test_free_joins_touching_parts_and_keeps_lighter_to_parts_of_days() -> None:
    r = rule_more.read_free(" keep saturday afternoons and evenings free ")
    assert r and (r.at, r.until, r.days) == ("12:00", "22:00", ("sat",))
    r = rule_more.read_free(" make tuesday mornings less packed ")
    assert r and r.amount == 0.5 and r.days == ("tue",)
    assert rule_more.read_free(" keep friday nights and saturday mornings free ") is None  # two stretches
    assert rule_more.read_free(" block out 4-6 on friday for the dentist ") is None  # once: an event
