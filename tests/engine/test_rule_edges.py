"""Edges of the rules you write, found in an audit: a night past midnight, an exam among several, events named by
words, an evening kept free until midnight, and the parts of a set due on your day rather than UTC's."""

from datetime import date

from friday.core.rule_text import read, spec
from friday.core.settings import validate_value
from friday.core.time import to_local
from friday.engine.rules import BuildContext
from tests.bench.generator import Maker, Scenario, bench_settings

TZ = "America/New_York"
MON = date(2026, 10, 19)


def rule(text: str, name: str = "r") -> dict:
    reading, strength = read(text)
    assert reading is not None, text
    return spec(reading, strength, name, [], [])


def test_no_work_after_midnight_the_night_before_leaves_that_day_open() -> None:
    make = Maker(TZ, MON)
    club = make.fixed("commitment", "Climbing club", make.at(2, "18:00"), 120)  # Wednesday
    essay = make.item("assignment", "Essay", duration_units=8, due_utc=make.at(4, "12:00"))
    late = rule("never work after midnight the night before climbing club")
    settings = bench_settings(TZ, horizon_days=3, fine_days=3, rules=[late])
    p = Scenario("t", [club, essay], make.at(0, "05:00"), settings).build()
    allowed = p.items[f"item:{essay.id}"].allowed_set
    tuesday = [s for s in range(p.grid.S) if p.grid.slots[s].date == date(2026, 10, 20)]
    day = [s for s in tuesday if p.grid.slots[s].day_minute < 24 * 60 and not (p.blocked[s] or p.core[s])]
    night = [s for s in tuesday if p.grid.slots[s].day_minute >= 24 * 60]
    assert day and all(s in allowed for s in day)  # Tuesday itself is open
    assert not any(s in allowed for s in night)  # from midnight on, that night, it isn't


def test_exam_prep_is_due_at_the_coming_exam_nearest_its_due() -> None:
    make = Maker(TZ, MON)
    quiz = make.fixed("commitment", "CHEM 2090 Quiz 3", make.at(0, "10:00"), 50)  # Monday, over by 3pm
    midterm = make.fixed("commitment", "CHEM 2090 Midterm", make.at(2, "10:00"), 90)  # Wednesday
    prep = make.item("exam_prep", "CHEM 2090 midterm review", duration_units=12, due_utc=make.at(2, "10:00"))
    p = Scenario(
        "t", [quiz, midterm, prep], make.at(0, "15:00"), bench_settings(TZ, horizon_days=4, fine_days=4)
    ).build()
    item = p.items[f"item:{prep.id}"]
    assert item.due_utc == make.at(2, "10:00") and item.allowed  # Wednesday's midterm, with time to prepare


def test_optional_events_are_named_by_whole_words() -> None:
    make = Maker(TZ, MON)
    events = [
        make.fixed("commitment", "Open office hours", make.at(0, "13:00"), 120),  # "pe" inside a word
        make.fixed("commitment", "Speech class", make.at(0, "16:00"), 60),
        make.fixed("commitment", "PE 1162 Salsa", make.at(0, "19:00"), 60),
    ]
    settings = bench_settings(TZ, horizon_days=2, fine_days=2, rules=[rule("skip PE if I have too much work")])
    p = Scenario("t", events, make.at(0, "09:00"), settings).build()
    assert {f.title: f.skippable for f in p.fixed} == {
        "Open office hours": False,
        "Speech class": False,
        "PE 1162 Salsa": True,
    }


def test_an_evening_kept_free_until_midnight_keeps_the_night_after_it_too() -> None:
    ends = {}
    for text in ("keep from 6pm to midnight free", "keep from 6pm to 11:30pm free"):
        make = Maker(TZ, MON)
        work = make.item("assignment", "Essay", duration_units=8, due_utc=make.at(3, "12:00"))
        settings = bench_settings(TZ, horizon_days=2, fine_days=2, rules=[rule(text, "res")])
        night = {"bedtime": "03:00", "wake": "09:00", "margin_min": 0}
        settings["sleep"] = validate_value(
            "sleep", dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), night)
        )
        p = Scenario("t", [work], make.at(0, "09:00"), settings).build()
        reserve = next(r for r in p.rules if r.name == "res")
        slots = sorted(v[2] for v in next(iter(reserve.measures(BuildContext(p)))).expr.terms)
        ends[text] = to_local(int(p.grid.end[slots[-1]]), TZ).strftime("%a %H:%M")
    assert ends["keep from 6pm to midnight free"] == ends["keep from 6pm to 11:30pm free"] == "Tue 03:00"
