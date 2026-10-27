"""Rules from sentences: what the grammar reads, and the planner rule each reading becomes."""

import re

import pytest

from friday.core.rule_text import Reading, read, sentence, spec


@pytest.mark.parametrize(
    ("text", "reading", "strength"),
    [
        ("I prefer eating lunch before 1pm", Reading("window", "lunch", rel="before", at="13:00"), "Prefer"),
        (
            "No work after 10pm on weekdays",
            Reading("window", "work", rel="before", at="22:00", days=("mon", "tue", "wed", "thu", "fri")),
            "Prefer",
        ),
        (
            "deep work in the morning",
            Reading("window", "deep work", rel="between", at="08:00", until="12:00"),
            "Prefer",
        ),
        ("gym between 5 and 7", Reading("window", "gym", rel="between", at="17:00", until="19:00"), "Prefer"),
        (
            "no work between 11:30pm and 7am",
            Reading("window", "work", rel="not_between", at="23:30", until="07:00"),
            "Prefer",
        ),
        (
            "no reading in the morning",
            Reading("window", "reading", rel="not_between", at="08:00", until="12:00"),
            "Prefer",
        ),
        ("never work on sundays", Reading("days", "work", rel="not_on", days=("sun",)), "Always"),
        ("reading only on weekends", Reading("days", "reading", rel="on", days=("sat", "sun")), "Prefer"),
        (
            "keep saturday mornings free",
            Reading("free", "work", rel="between", at="08:00", until="12:00", days=("sat",)),
            "Prefer",
        ),
        ("really keep evenings free", Reading("free", "work", rel="between", at="17:00", until="22:00"), "Strongly"),
        ("at most 6 hours a day", Reading("cap", "work", amount=6.0), "Prefer"),
        ("no more than 2h of reading a day", Reading("cap", "reading", amount=2.0), "Prefer"),
        ("finish things a day early", Reading("early", "work", amount=1.0), "Prefer"),
        ("gym right after class", Reading("after", "gym", event="class"), "Prefer"),
    ],
)
def test_the_grammar_reads(text: str, reading: Reading, strength: str) -> None:
    assert read(text) == (reading, strength)


def test_no_work_between_two_times_avoids_those_hours_not_the_rest() -> None:
    night = Reading("window", "work", rel="not_between", at="07:00", until="10:00")
    assert sentence(night) == "No work between 7am and 10am"
    assert spec(night, "Strongly", "you:mornings", [], [])["params"] == {"start": "07:00", "end": "10:00", "price": 6.0}
    gym = spec(Reading("window", "gym", rel="between", at="17:00", until="19:00"), "Prefer", "you:gym", [], [])
    assert (gym["params"]["start"], gym["params"]["end"]) == ("19:00", "17:00")  # the other hours


def test_what_it_cannot_read_is_none() -> None:
    assert read("make me a sandwich")[0] is None


def test_a_reading_becomes_a_planner_rule_in_your_words() -> None:
    lunch = Reading("window", "lunch", rel="before", at="13:00")
    assert sentence(lunch) == "Lunch before 1pm"
    soft = spec(lunch, "Prefer", "you:lunch", [], ["Reading"])
    assert (soft["type"], soft["scope"], soft["params"]) == (
        "time_preference",
        {"title": "lunch"},
        {"start": "13:00", "end": "04:00", "price": 2.0},
    )
    assert spec(lunch, "Always", "you:lunch", [], [])["params"]["price"] == "forbid"
    cap = spec(Reading("cap", "reading", amount=2.0), "Strongly", "you:cap", [], ["Reading"])
    assert (cap["type"], cap["scope"], cap["weight"], cap["params"]) == (
        "daily_load",
        {"preset": "Reading"},
        15.0,
        {"threshold": "2h"},
    )


@pytest.mark.parametrize(
    ("text", "paces"),
    [
        ("go easier on saturday and go harder on sunday", (("sat", "Easy"), ("sun", "Push"))),
        ("take it easy on weekends", (("sat", "Easy"), ("sun", "Easy"))),
        ("saturdays are easy, sundays are hard", (("sat", "Easy"), ("sun", "Push"))),
        ("go easy on saturdays and sundays", (("sat", "Easy"), ("sun", "Easy"))),
        ("push on sundays", (("sun", "Push"),)),
    ],
)
def test_a_pace_for_some_weekdays_every_week(text: str, paces: tuple) -> None:
    reading, _ = read(text)
    assert reading is not None and reading.kind == "pace" and reading.paces == paces


def test_pace_words_alone_or_beside_other_rules_read_as_before() -> None:
    assert read("no work on sundays")[0] == Reading("days", "work", rel="not_on", days=("sun",))
    mixed = read("go easier on saturday and no work on sunday")[0]
    assert mixed is None or mixed.kind != "pace"  # half a pace isn't read as all of one
    assert sentence(read("go easier on saturday and go harder on sunday")[0]) == "Easy on Saturdays, Push on Sundays"


@pytest.mark.parametrize(
    "text",
    ["push when neccessary for work not to be late", "push when necessary for work not to be late",
     "don't let work be late", "work harder if needed so nothing is late"],
)  # fmt: skip
def test_working_more_so_nothing_is_late_reads_as_deadlines_first(text: str) -> None:
    reading, _ = read(text)
    assert reading is not None and reading.kind == "deadlines" and sentence(reading) == "Deadlines come first"


def test_rules_that_mention_due_dates_still_read_as_themselves() -> None:
    assert read("finish essays 2 days before they're due")[0] == Reading("early", "essays", amount=2.0)


@pytest.mark.parametrize(
    "text",
    [
        "gym and climbing club are optional",
        "make the gym sessions on tuesday and thursday as well as climbing club be not mandatory",
        "skip gym and climbing club if there is too much work",
        "gym and climbing club can be skipped",
    ],
)
def test_events_that_give_way_to_work(text: str) -> None:
    reading, _ = read(text)
    assert reading == Reading("optional", "events", events=("gym", "climbing club"))
    assert sentence(reading) == "Gym and Climbing Club are optional: work takes the time when it must"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["params"]["titles"]) == ("skippable", ["gym", "climbing club"])


@pytest.mark.parametrize(
    "text",
    [
        "i usually don't go to the climbing club becasue of my workload so I will only go if I am ahead of my work",
        "climbing club only if i'm ahead",
        "Climbing club only when I'm caught up on work",
        "only go to climbing club when I'm on top of my work",
        "I only go to the climbing club if I have time",
        "skip climbing club unless I'm ahead",
        "I usually skip climbing club because of work",
        "I usually skip climbing club",
    ],
)
def test_events_you_go_to_only_when_ahead(text: str) -> None:
    reading, _ = read(text)
    assert reading == Reading("ahead", "events", events=("climbing club",))
    assert sentence(reading) == "Climbing Club only when you’re ahead: work takes its time first"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["stage"]) == ("skippable", "preferences")  # below every late night, not above it
    assert rule["params"] == {"titles": ["climbing club"], "price": 1.0, "ahead": True}


def test_optional_and_ahead_read_apart() -> None:
    assert read("gym and climbing club only if I am ahead of my work")[0] == Reading(
        "ahead", "events", events=("gym", "climbing club")
    )
    assert read("skip gym if there is too much work")[0] == Reading("optional", "events", events=("gym",))
    assert read("gym is optional")[0].kind == "optional"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("text", "strength"),
    [
        ("if i am going to climbing club the next day then the previous day must end at 10:00", "Always"),
        ("no work after 10pm the night before climbing club", "Prefer"),
        ("stop working at 10 the night before climbing club", "Prefer"),
    ],
)
def test_the_night_before_an_event_ends_early(text: str, strength: str) -> None:
    reading, read_strength = read(text)
    assert (
        reading == Reading("night_before", "work", at="22:00", events=("climbing club",)) and read_strength == strength
    )
    assert sentence(reading) == "No work after 10pm the night before Climbing Club"
    rule = spec(reading, "Always", "you:x", [], [])
    assert (rule["type"], rule["params"]) == (
        "before_event",
        {"titles": ["climbing club"], "after": "22:00", "price": "forbid"},
    )


def test_a_lighter_stretch_keeps_about_half_of_it_free() -> None:
    reading, _ = read("Keep Friday and Saturday nights lighter")
    assert reading == Reading("free", "work", rel="between", at="22:00", until="02:00", days=("fri", "sat"), amount=0.5)
    assert sentence(reading) == "Keep Fri, Sat 10pm–2am lighter"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["params"]["free"]) == ("reserve", "2h")  # half of four hours: less work, not none
    assert read("lighter friday evenings")[0].amount == 0.5 and read("keep saturday mornings free")[0].amount is None


def test_midnight_ends_a_span_at_midnight_not_noon() -> None:
    reading, strength = read("never work between 9pm and midnight")
    assert reading == Reading("window", "work", rel="not_between", at="21:00", until="00:00")
    assert spec(reading, strength, "x", [], [])["params"] == {"start": "21:00", "end": "00:00", "price": "forbid"}
    assert read("keep fridays from 6pm to midnight free")[0].until == "00:00"  # type: ignore[union-attr]


def test_a_free_span_said_without_am_or_pm_is_the_evening() -> None:
    reading, _ = read("keep saturdays from 6 to 9 free")
    assert (reading.at, reading.until) == ("18:00", "21:00")  # type: ignore[union-attr]
    assert read("keep saturdays from 9 to 11am free")[0].at == "09:00"  # type: ignore[union-attr]


@pytest.mark.parametrize("text", ["rest on sundays", "I rest on Sundays", "rest sundays", "off on sundays"])
def test_resting_on_a_day(text: str) -> None:
    assert read(text)[0] == Reading("days", "work", rel="not_on", days=("sun",))


@pytest.mark.parametrize(
    ("text", "before", "after", "said"),
    [
        ("30 minutes before and after gym", 30, 30, "30 min before and after Gym"),
        ("leave 15 min around the gym", 15, 15, "15 min before and after Gym"),
        ("a 20 minute buffer around gym", 20, 20, "20 min before and after Gym"),
        ("keep 30 mins either side of gym", 30, 30, "30 min before and after Gym"),
        ("20 min before gym and 40 after", 20, 40, "20 min before Gym and 40 min after"),
        ("45 minutes after gym", 0, 45, "45 min after Gym"),
        ("1 hour before gym", 60, 0, "1 h before Gym"),
    ],
)
def test_time_kept_around_events(text: str, before: int, after: int, said: str) -> None:
    reading, _ = read(text)
    assert reading == Reading("around", "events", events=("gym",), before_min=before, after_min=after)
    assert sentence(reading) == said
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["params"]) == ("travel", {"titles": ["gym"], "before_min": before, "after_min": after})


def test_around_leaves_other_rules_alone() -> None:
    assert read("gym right after class")[0].kind == "after"  # type: ignore[union-attr]
    assert read("no work after 10pm")[0].kind == "window"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "text",
    [
        "I prefer eating lunch before 1pm",
        "No work after 10pm on weekdays",
        "deep work in the morning",
        "no work between 11:30pm and 7am",
        "never work on sundays",
        "reading only on weekends",
        "keep saturday mornings free",
        "keep friday and saturday evenings lighter",
        "keep saturday from 2 to 5 free",
        "no more than 2h of reading a day",
        "finish things 2 days early",
        "gym right after class",
        "go easier on saturdays",
        "gym and climbing club are optional",
        "climbing club only if i'm ahead",
        "no work after 10pm the night before climbing club",
        "20 min before gym and 40 min after",
        "push when necessary so nothing is late",
        "I prefer all sessions of exam prep tasks to be done as close to the exam as possible",
        "prep for the math quiz closer to the math quiz (with 1 day of buffer)",
        "readings as late as possible, leaving 12 hours",
    ],
)
def test_the_sentence_friday_writes_for_a_rule_reads_back_as_that_rule(text: str) -> None:
    """The Rules list shows each rule in Friday's words: typed back (or edited a little), it must be the same rule."""
    reading, _ = read(text)
    assert reading is not None
    assert read(sentence(reading))[0] == reading


@pytest.mark.parametrize(
    ("text", "subject", "events", "buffer"),
    [
        (
            "I prefer all sessions of exam prep tasks to be done as close to the exam as possible",
            "exam prep",
            None,
            None,
        ),
        ("interview prep as close to the interview as possible", "exam prep", ("interview",), None),
        ("prep for my interview as close to it as possible", "exam prep", ("interview",), None),
        ("prep for the math quiz closer to the math quiz (with 1 day of buffer)", "exam prep", ("math quiz",), 1440),
        ("quiz prep as close to the quiz as possible but finish a day early", "exam prep", ("quiz",), 1440),
        ("study for exams as late as possible", "exam prep", None, None),
        ("exam prep as close to the exam as possible, leaving 12 hours", "exam prep", None, 720),
        ("readings as late as possible", "readings", None, None),
    ],
)
def test_work_as_close_to_its_due_as_possible(
    text: str, subject: str, events: tuple | None, buffer: int | None
) -> None:
    assert read(text)[0] == Reading("close", subject, events=events, before_min=buffer)


def test_close_to_the_exam_becomes_a_price_on_that_prep() -> None:
    reading, strength = read("prep for the math quiz closer to the math quiz (with 1 day of buffer)")
    assert reading is not None
    made = spec(reading, strength, "you:quiz", [], ["Exam prep", "Reading"])
    assert made["type"] == "close_to_due" and made["params"] == {"buffer_min": 1440, "inside": 10.0}
    assert made["scope"]["preset"] == "Exam prep"
    (words,) = made["scope"]["title_regex"]
    assert re.search(words, "Prep: Math 1920 Quiz 3") and not re.search(words, "Prep: Math 1920 Prelim 2")
    always = spec(reading, "Always", "you:quiz", [], ["Exam prep"])
    assert always["params"]["inside"] == "forbid"


@pytest.mark.parametrize(
    ("text", "kind", "meals"),
    [
        ("Never skip lunch or dinner", "meals_kept", ("lunch", "dinner")),
        ("Lunch and dinner are never skipped", "meals_kept", ("lunch", "dinner")),
        ("Dinner is non-negotiable", "meals_kept", ("dinner",)),
        ("never miss supper", "meals_kept", ("dinner",)),
        ("Always keep my meals", "meals_kept", ("breakfast", "lunch", "dinner")),
        ("Let Friday decide breakfast", "meals_learned", ("breakfast",)),
        ("Let Friday decide whether I have breakfast", "meals_learned", ("breakfast",)),
        ("Learn whether I have breakfast", "meals_learned", ("breakfast",)),
        ("Plan breakfast only if I usually have it", "meals_learned", ("breakfast",)),
        ("Friday decides all my meals", "meals_learned", ("breakfast", "lunch", "dinner")),
    ],
)
def test_meals_kept_from_work_or_left_to_friday(text: str, kind: str, meals: tuple) -> None:
    assert read(text)[0] == Reading(kind, "meals", events=meals)


def test_kept_meals_hold_in_the_deadlines_stage_and_learned_ones_are_the_jobs() -> None:
    reading, strength = read("Never skip lunch or dinner")
    assert reading is not None and sentence(reading) == "Lunch and dinner are never skipped for work"
    kept = spec(reading, strength, "you:meals", [], [])
    assert (kept["type"], kept["stage"], kept["scope"]["preset"]) == ("elastic_shortfall", "deadlines", "Routine")
    (words,) = kept["scope"]["title_regex"]
    assert all(re.search(words, t) for t in ("Lunch", "Dinner", "Supper")) and not re.search(words, "Breakfast")
    reading, strength = read("Let Friday decide breakfast")
    assert reading is not None and sentence(reading) == "Let Friday decide breakfast from your habits"
    learned = spec(reading, strength, "you:breakfast", [], [])
    assert (learned["type"], learned["params"]) == ("meal_learned", {"meals": ["breakfast"]})
    claude = Reading("meals_kept", "meals", events=["Supper"])  # Claude's overrides: a list, in its own words
    assert sentence(claude) == "Dinner is never skipped for work"


def test_skipping_a_meal_when_busy_is_not_keeping_it() -> None:
    reading, _ = read("skip lunch if there's too much work")
    assert reading is not None and reading.kind != "meals_kept"


@pytest.mark.parametrize(
    "text",
    [
        "have shorter events go with smaller time slots and longer events go in larger time slots",
        "Short tasks in short gaps, long tasks in long stretches",
        "fit tasks to the gaps",
        "use small gaps for small tasks",
        "save big blocks of time for long work",
        "Put quick things in the small breaks between classes",
    ],
)
def test_tasks_fitted_to_the_gaps_they_go_in(text: str) -> None:
    reading, strength = read(text)
    assert reading == Reading("fit_gaps", "work")
    made = spec(reading, "Strongly", "you:gaps", [], [])
    assert (made["type"], made["weight"], made["params"]) == ("fit_gaps", 3.0, {"price": 2.0})


@pytest.mark.parametrize(
    "text", ["small tasks in the morning", "take short breaks between long sessions", "no short breaks"]
)
def test_other_sentences_about_size_are_not_gap_fitting(text: str) -> None:
    reading, _ = read(text)
    assert reading is None or reading.kind != "fit_gaps"


# From a corpus of 522 student-written rules (26 Oct): each was read as something else before. Each now reads as it
# means, or goes to Claude (None) rather than become a rule that says another thing.
@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("no work after 10", "No work after 10pm"),
        ("no work after 11:30", "No work after 11:30pm"),
        ("no work after 9 on fridays", "No work after 9pm on Fri"),
        ("no work after 10 p.m.", "No work after 10pm"),
        ("dinner before 7", "Dinner before 7pm"),
        ("Must have dinner by 8", "Dinner before 8pm"),
        ("nothing before 8", "No work before 8am"),
        ("I don't want to work before 9", "No work before 9am"),
        ("I don't want to start work before 10 am on weekends", "No work before 10am on weekends"),
        ("avoid working after 10pm", "No work after 10pm"),
        ("no wrok after 10pm", "No work after 10pm"),
        ("dont work on weekends", "No work on weekends"),
        ("absolutely no work on sundays", "No work on Sun"),
        ("never ever work past 1am", "No work after 1am"),
        ("under no circumstances work on sunday", "No work on Sun"),
        ("preferably no work before 9", "No work before 9am"),
        ("Done by 9pm every day", "No work after 9pm"),
        ("finish work by 6pm on fridays", "No work after 6pm on Fri"),
        ("nothing on sunday mornings", "Keep Sun 8am–12pm free"),
        ("I'd rather not work on friday nights", "Keep Fri 10pm–2am free"),
        ("no work after 10pm except on fridays", "No work after 10pm on Mon, Tue, Wed, Thu, Sat, Sun"),
        ("Stop working by 10:30pm on school nights", "No work after 10:30pm on Mon, Tue, Wed, Thu, Sun"),
        ("only work between 9am and 6pm", "Work between 9am and 6pm"),
        ("weekend work only in the afternoon", "Work between 12pm and 5pm on weekends"),
        (
            "I'll go to the party only if I'm done with my work",
            "Party only when you’re ahead: work takes its time first",
        ),
        ("leave 45 minutes after soccer to shower", "45 min after Soccer"),
        ("readings can be late", None),
        ("I don't eat breakfast", None),
        ("Eat lunch around noon", None),
        ("no eating after 9pm", None),
        ("bed by 11", "No work after 11pm"),
        ("sleep before 1am", "No work after 1am"),
        ("sleep in on saturdays", None),
        ("no work after 10pm and no work on sundays", None),
        ("only work on sundays if I'm behind", None),
        ("if a reading is late, skip it", None),
        ("short break after each lecture", None),
        ("lunch after my 11am class", None),
        ("a 30 minute break after every 2 hours of work", None),
        ("I need time to decompress after labs", None),
        ("take an hour off in the afternoon", None),
        ("late dinner on fridays is fine", None),
        ("easy week after midterms", None),
        ("no work during movie night on thursdays", None),
        ("no work after dinner on fridays", None),
        # 27 Oct: read as a rule that dropped part of what it said.
        ("never work on sunday mornings", "Keep Sun 8am–12pm free"),
        ("don't work on tues and thurs evenings", "Keep Tue, Thu 5pm–10pm free"),
        ("max 4h a day on weekends", "At most 4 h a day on weekends"),
        ("no more than 3 hours on saturdays", "At most 3 h a day on Sat"),
        ("Debate club is optional during midterms", None),
        ("gym is optional when I have a prelim that week", None),
        ("no work after 10pm except before exams", None),
        ("work after class until dinner", None),
        ("lunch before 1 and dinner before 7", None),
        ("no work before 9 or after 10", None),
        ("gym is optional but climbing club is mandatory", None),
        ("at most 6 hours a day and 4 on weekends", None),
        ("cap mondays at 4 hours", "At most 4 h a day on Mon"),
        ("only light work on weekends", None),  # on weekends nothing else: not light work only then
        ("only reading on sundays", None),
        ("15 minutes before and after events", None),  # a kind's buffer (event_kinds), not a title
        ("1h buffer before exams", None),
        ("an hour before any exam", None),
    ],
)
def test_sentences_once_misread_read_as_they_mean_or_go_to_claude(text: str, said: str | None) -> None:
    reading, _ = read(text)
    assert (sentence(reading) if reading else None) == said


def test_kind_words_scope_to_the_kind() -> None:
    reading, strength = read("no homework after 10pm")
    assert reading is not None
    assert spec(reading, strength, "x", [], ["Assignment", "Reading"])["scope"] == {"preset": "Assignment"}


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("no more than 90 minutes of reading a day", "At most 1.5 h of reading a day"),
        ("under 6 hours of work daily", "At most 6 h a day"),
        ("less than 5 hours a day", "At most 5 h a day"),
        ("6h/day max", "At most 6 h a day"),
        ("at most 3 hours of studying a night", "At most 3 h a day"),
        ("Don't work more than 4 hours on weekends", "At most 4 h a day on weekends"),
        ("at most 2 hours", None),  # a sitting's length, not a day's
    ],
)
def test_a_day_s_limit_said_other_ways(text: str, said: str | None) -> None:
    reading, _ = read(text)
    assert (sentence(reading) if reading else None) == said


def test_a_limit_on_some_days_holds_only_on_them() -> None:
    reading, strength = read("max 4h a day on weekends")
    assert reading is not None
    assert spec(reading, strength, "x", [], [])["params"] == {"threshold": "4h", "days": ["sat", "sun"]}


@pytest.mark.parametrize("text", ["shallow work after 8pm", "light work in the evening", "easy tasks after 9pm"])
def test_light_work_is_work_marked_light(text: str) -> None:
    reading, strength = read(text)
    assert reading is not None and reading.subject == "light work"
    assert spec(reading, strength, "x", [], [])["scope"] == {"energy": "light"}
