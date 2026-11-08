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
    for said in (" thursday afternoons could be lighter ", " only schedule light stuff on fridays ",
                 " push my dentist appt to next tuesday ", " a pace with a time: easy on fridays after 5pm "):  # fmt: skip
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
