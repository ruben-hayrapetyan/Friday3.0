"""Rule sentences generated from templates (subjects × relations × times × days × strength words × negations ×
hedges): whatever the sentence, reading it doesn't crash, a reading becomes a rule the settings and the planner
accept, its times are clock times, strength words map one way, and the sentence Friday writes back reads as the same
rule."""

import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.core.presets import DEFAULT_PRESETS
from friday.core.rule_text import Reading, read, sentence, spec
from friday.core.settings import validate_value
from friday.engine.rules import RULE_TYPES, build_rules

MANY = settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
CLOCK = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
SHORT = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FULL = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SUBJECTS = ["work", "deep work", "reading", "gym", "homework", "essays", "chores", "studying", "math", "psych",
            "anything", "lunch", "exam prep"]  # fmt: skip
EVENTS = ["gym", "climbing club", "soccer practice", "band", "choir", "book club", "dance", "the gym"]
PARTS = ["mornings", "afternoons", "evenings", "nights"]
ALWAYS_WORDS = ["always", "must", "absolutely", "strictly"]
STRONG_WORDS = ["really", "strongly", "definitely"]
HEDGES = ["please", "ideally", "i'd prefer", "i'd like to", "preferably", "i really want to"]


@st.composite
def clock_said(draw: st.DrawFn) -> str:
    """A time as people write it: `22:00`, `9:30pm`, `10pm`, `noon`, `midnight`."""
    hour, minute = draw(st.integers(0, 23)), draw(st.sampled_from([0, 0, 15, 30, 45, 5, 59]))
    style = draw(st.integers(0, 3))
    if style == 0:
        return f"{hour:02d}:{minute:02d}"
    if style == 1 and (hour, minute) in ((12, 0), (0, 0)):
        return "noon" if hour == 12 else "midnight"
    twelve = hour % 12 or 12
    return f"{twelve}{f':{minute:02d}' if minute else ''}{'am' if hour < 12 else 'pm'}"


@st.composite
def days_said(draw: st.DrawFn) -> str:
    """`on weekends`, `on mondays, wednesdays and fridays`, `on tue & thu`, or nothing."""
    picked = draw(st.lists(st.integers(0, 6), max_size=7, unique=True))
    if not picked:
        return draw(st.sampled_from(["", "on weekdays", "on weekends"]))
    names = [draw(st.sampled_from([SHORT[d], FULL[d], FULL[d] + "s"])) for d in picked]
    if len(names) == 1:
        return f"on {names[0]}"
    return "on " + ", ".join(names[:-1]) + draw(st.sampled_from([" and ", ", ", " & "])) + names[-1]


@st.composite
def rule_sentences(draw: st.DrawFn) -> str:
    s, e, e2 = draw(st.sampled_from(SUBJECTS)), draw(st.sampled_from(EVENTS)), draw(st.sampled_from(EVENTS))
    t1, t2, d, part = draw(clock_said()), draw(clock_said()), draw(days_said()), draw(st.sampled_from(PARTS))
    whole = draw(st.sampled_from([5, 10, 15, 20, 25, 30, 40, 45, 50, 60, 75, 90, 120, 150, 180, 240, 360]))
    minutes = draw(st.sampled_from([5, 10, 15, 20, 30, 45, 60, 120]))
    hours = draw(st.sampled_from(["1", "2", "3", "4", "6", "8", "1.5", "2.5", "0.5", "10"]))
    n = draw(st.sampled_from(["a", "one", "two", "three", "1", "2", "3", "5"]))
    spare = draw(st.sampled_from(["1 day", "2 days", "12 hours", "3 hours", "90 minutes", "half a day", "30 minutes"]))
    plain = d.removeprefix("on ")
    templates = [
        f"no {s} after {t1} {d}", f"{s} before {t1} {d}", f"{s} after {t1} {d}", f"no {s} before {t1} {d}",
        f"{s} between {t1} and {t2} {d}", f"no {s} between {t1} and {t2} {d}", f"{s} in the {part[:-1]} {d}",
        f"no {s} in the {part[:-1]} {d}", f"keep {plain} {part} free",
        f"keep {plain or 'saturday'} from {t1} to {t2} free", f"keep {plain or 'friday'} {part} lighter",
        f"at most {hours} hours of {s} a day", f"at most {hours} hours a day",
        f"no more than {hours}h a day", f"finish {s} {n} days early", f"{s} right after {e}",
        f"{whole} minutes before and after {e}", f"{whole} minutes before {e} and {minutes} after",
        f"{whole} minutes after {e}", f"{whole} min around {e}", f"{e} and {e2} are optional", f"{e} is optional",
        f"skip {e} if there's too much work", f"{e} only if i'm ahead", f"i usually skip {e}",
        f"no work after {t1} the night before {e}", f"{s} only {d or 'on weekends'}", f"no {s} {d or 'on sundays'}",
        f"never {s} {d or 'on sundays'}", f"exam prep as close to the exam as possible, leaving {spare}",
        f"{s} as late as possible", f"prep for the {e} close to the {e} with {spare} of buffer",
        f"go easier on {plain or 'saturdays'}", "go easier on saturday and go harder on sunday",
        "never skip lunch or dinner", "let friday decide breakfast", "always keep my meals", "fit tasks to the gaps",
        "don't let work be late", f"rest on {plain or 'sundays'}", f"stop working by {t1} {d}",
    ]  # fmt: skip
    said = " ".join(draw(st.sampled_from(templates)).split())
    lead = draw(st.sampled_from(["", "", "", *ALWAYS_WORDS, *STRONG_WORDS, *HEDGES]))
    return f"{lead} {said}".strip()


def well_made(reading: Reading, strength: str) -> None:
    """The planner rule a reading becomes: valid settings, and (for the planner's own types) an engine rule."""
    made = spec(reading, strength, "you:rule", ["Psych"], list(DEFAULT_PRESETS))  # type: ignore[arg-type]
    validate_value("rules", [made])
    if made["type"] in RULE_TYPES:
        build_rules([made])
    for time in (reading.at, reading.until):
        assert time is None or CLOCK.fullmatch(time), time


@MANY
@given(rule_sentences())
def test_a_generated_sentence_reads_as_a_rule_that_reads_back_the_same(text: str) -> None:
    reading, strength = read(text)
    if reading is None:
        return  # left to Claude
    well_made(reading, strength)
    said = sentence(reading)
    assert read(said)[0] == reading, said


@MANY
@given(rule_sentences())
def test_strength_words_map_one_way(text: str) -> None:
    _, strength = read(text)
    if re.search(r"\b(always|never|must|absolutely|strictly)\b", text):
        assert strength == "Always"
    elif re.search(r"\b(really|strongly|definitely)\b", text):
        assert strength == "Strongly"
    else:
        assert strength == "Prefer"


@st.composite
def time_rules(draw: st.DrawFn) -> tuple[str, str, str]:
    """A subject, a time with am or pm (a bare `10:00` after "after" is the evening, on purpose), and days: for the
    sentences that must mean the same."""
    time = draw(clock_said().filter(lambda t: not t[0].isdigit() or t.endswith(("am", "pm"))))
    return draw(st.sampled_from(SUBJECTS[:-2])), time, draw(days_said())


@MANY
@given(time_rules())
def test_no_work_after_a_time_is_work_before_it(said: tuple[str, str, str]) -> None:
    subject, time, days = said
    assert read(f"no {subject} after {time} {days}")[0] == read(f"{subject} before {time} {days}")[0]
    assert read(f"no {subject} before {time} {days}")[0] == read(f"{subject} after {time} {days}")[0]


@MANY
@given(time_rules(), st.sampled_from(HEDGES + STRONG_WORDS), st.sampled_from(["", ".", " if possible", "!"]))
def test_hedges_and_strength_words_never_change_what_a_rule_says(
    said: tuple[str, str, str], lead: str, tail: str
) -> None:
    subject, time, days = said
    for base in (f"no {subject} after {time} {days}", f"{subject} in the morning {days}", f"no {subject} {days}"):
        plain = " ".join(base.split())
        assert read(f"{lead} {plain}{tail}")[0] == read(plain)[0]
        assert read(plain.upper())[0] == read(plain)[0]


@MANY
@given(st.permutations(SHORT), st.integers(1, 7), time_rules())
def test_the_order_days_are_named_in_does_not_matter(order: list[str], k: int, said: tuple[str, str, str]) -> None:
    subject, time, _ = said
    days = order[:k]
    one = read(f"no {subject} after {time} on {', '.join(days)}")[0]
    other = read(f"no {subject} after {time} on {', '.join(reversed(days))}")[0]
    assert one == other
    assert one is None or one.days is None or set(one.days) == set(days) or len(days) == 7


WORDS = ("no never don't not avoid always really must please i'd prefer work deep reading gym lunch dinner breakfast "
         "meals after before by until between and to from in the morning evening night afternoon on weekdays weekends "
         "sundays mon wed fri except school nights keep free lighter at most hours of a day finish days early right "
         "after class minutes min around before and after optional skip if there's too much only i'm ahead night "
         "climbing club go easier harder push as close exam possible late let friday decide fit tasks gaps small short "
         "long 10pm 10 7am noon midnight 12am 0 00:00 24:00 99 99:99 13pm 1.5 30 , ; . - – 9:75 25 0.0 hour h m days "
         "day bed sleep rest off leave buffer 1000 999 prep for quiz with leaving").split()  # fmt: skip


@settings(max_examples=500, deadline=None)
@given(st.lists(st.sampled_from(WORDS), min_size=1, max_size=12))
def test_any_jumble_of_rule_words_reads_safely(words: list[str]) -> None:
    reading, strength = read(" ".join(words))
    if reading is not None:
        well_made(reading, strength)
        read(sentence(reading))


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=60))
def test_any_text_reads_without_a_crash(text: str) -> None:
    reading, strength = read(text)
    if reading is not None:
        well_made(reading, strength)


# Bugs these properties found (27 Oct), each minimal, fixed the same day.


@pytest.mark.parametrize("text", ["90 minutes before and after gym", "75 minutes after gym", "2.5 hours before gym"])
def test_time_around_an_event_that_is_not_whole_hours_reads_back(text: str) -> None:
    reading, _ = read(text)
    assert reading is not None and read(sentence(reading))[0] == reading


@pytest.mark.parametrize("text", ["please bed by 11", "really sleep before 1am", "ideally in bed by 11pm"])
def test_a_hedged_bedtime_still_ends_work(text: str) -> None:
    reading, _ = read(text)
    assert reading is not None and reading.subject == "work"


@pytest.mark.parametrize("text", ["piano lesson saturdays", "no lesson saturdays"])
def test_a_word_ending_in_on_is_not_on_a_day(text: str) -> None:
    reading, _ = read(text)
    assert reading is None or reading.subject.split()[-1] != "less"
