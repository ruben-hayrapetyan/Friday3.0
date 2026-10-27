"""Scheduling changes said in words (27 Oct: "this is a scheduling change that friday couldn't parse. there will be this
kind of scheduling changes so make sure to add them to the test set"). Friday leaves these to Claude, which proposes
Friday's own commands. No test calls Claude, so each case is the sentence with what Claude should propose for it: the
proposal must be taken as it is (no command refuses it), from Ask Claude and from the Rules page, and applied, it must
make the calendar the sentence means. The first is the one Friday couldn't do: a place for one event, and a new
weekly event with a week off and a week somewhere else."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from friday.commands.claude import SYSTEM
from tests.commands.helpers import App, new_app
from tests.commands.test_ask_claude import asking

# Monday 19 Oct 2026, 9am (the helpers' now): "Friday" is the 23rd, "this Saturday" the 24th.
Ids = dict[str, int]


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def calendar(app: App) -> Ids:
    """A week like yours: Salsa on Friday, Chem lectures Monday, Wednesday and Friday, yoga on Wednesdays, a CS 2112
    discussion on Thursdays. Each event's id by title and date ("Yoga 2026-10-21")."""
    app.do("add", title="Salsa", when="fixed", start="2026-10-23T18:15", end="2026-10-23T19:15")
    chem = {"start": "2026-10-19T12:20", "end": "2026-10-19T13:10", "every": "mon,wed,fri"}
    app.do("add", title="Chem 2090 Lecture", when="fixed", location="Baker 100", **chem)
    app.do("add", title="Yoga", when="fixed", start="2026-10-21T19:00", end="2026-10-21T20:00", every="wed")
    app.do(
        "add", title="CS 2112 Discussion", when="fixed", start="2026-10-22T12:20", end="2026-10-22T13:10", every="thu"
    )
    return {f"{e['title']} {e['start'][:10]}": e["id"] for e in events(app)}


def events(app: App) -> list[dict[str, Any]]:
    """Every event to come, as the app shows it."""
    found = [app.do("item", id=r["id"])["item"] for r in app.table("items") if r["when_kind"] == "fixed"]
    return [e for e in found if e["status"] == "todo"]


def on(app: App, title: str, day: str) -> dict[str, Any] | None:
    return next((e for e in events(app) if e["title"] == title and e["start"][:10] == day), None)


@dataclass
class Case:
    text: str
    actions: Callable[[Ids], list[dict[str, Any]]]  # what Claude should propose
    # (title, day, "HH:MM–HH:MM" or None for gone that day, place)
    expect: list[tuple[str, str, str | None, str | None]]


def act(command: str, **given: Any) -> dict[str, Any]:
    return {"sentence": command, "command": command, "input": given}


CASES = [
    Case(
        "add a location to salsa on friday which is Willard Straight Hall, room 215. add another salsa event on "
        "saturday from 1:35 - 2:40pm in Helen Newman Hall's dance studio except for the one on saturday on 11/14 and "
        "on this saturday, its in Willard Straight Hall, room 601",
        lambda ids: [
            act("edit", id=ids["Salsa 2026-10-23"], location="Willard Straight Hall, room 215"),
            act(
                "add",
                title="Salsa",
                when="fixed",
                start="2026-10-24T13:35",
                end="2026-10-24T14:40",
                location="Helen Newman Hall, dance studio",
                every="sat",
                exceptions=[
                    {"date": "2026-11-14", "skip": True},
                    {"date": "2026-10-24", "location": "Willard Straight Hall, room 601"},
                ],
            ),  # fmt: skip
        ],
        [
            ("Salsa", "2026-10-23", "18:15–19:15", "Willard Straight Hall, room 215"),
            ("Salsa", "2026-10-24", "13:35–14:40", "Willard Straight Hall, room 601"),
            ("Salsa", "2026-10-31", "13:35–14:40", "Helen Newman Hall, dance studio"),
            ("Salsa", "2026-11-07", "13:35–14:40", "Helen Newman Hall, dance studio"),
            ("Salsa", "2026-11-14", None, None),
            ("Salsa", "2026-11-21", "13:35–14:40", "Helen Newman Hall, dance studio"),
        ],
    ),
    Case(
        "no yoga this week, and next week it's in the small gym",
        lambda ids: [
            act("skip", id=ids["Yoga 2026-10-21"]),
            act("edit", id=ids["Yoga 2026-10-28"], location="small gym"),
        ],
        [
            ("Yoga", "2026-10-21", None, None),
            ("Yoga", "2026-10-28", "19:00–20:00", "small gym"),
            ("Yoga", "2026-11-04", "19:00–20:00", None),
        ],  # fmt: skip
    ),
    Case(
        "from now on chem lecture is in Baker 200",
        lambda ids: [act("edit", id=ids["Chem 2090 Lecture 2026-10-21"], location="Baker 200", from_date="2026-10-21")],
        [
            ("Chem 2090 Lecture", "2026-10-19", "12:20–13:10", "Baker 100"),
            ("Chem 2090 Lecture", "2026-10-21", "12:20–13:10", "Baker 200"),
            ("Chem 2090 Lecture", "2026-11-06", "12:20–13:10", "Baker 200"),
        ],  # fmt: skip
    ),
    Case(
        "move this thursday's CS 2112 discussion to 5pm in Gates 114",
        lambda ids: [
            act(
                "edit",
                id=ids["CS 2112 Discussion 2026-10-22"],
                start="2026-10-22T17:00",
                end="2026-10-22T17:50",
                location="Gates 114",
            ),
        ],  # fmt: skip
        [
            ("CS 2112 Discussion", "2026-10-22", "17:00–17:50", "Gates 114"),
            ("CS 2112 Discussion", "2026-10-29", "12:20–13:10", None),
        ],  # fmt: skip
    ),
    Case(
        "add office hours every tuesday and thursday 4-5pm in Rhodes 412 until december, except thanksgiving week",
        lambda ids: [
            act(
                "add",
                title="Office hours",
                when="fixed",
                start="2026-10-20T16:00",
                end="2026-10-20T17:00",
                location="Rhodes 412",
                every="rrule:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261130T235900",
                exceptions=[{"date": "2026-11-24", "skip": True}, {"date": "2026-11-26", "skip": True}],
            ),
        ],  # fmt: skip
        [
            ("Office hours", "2026-10-20", "16:00–17:00", "Rhodes 412"),
            ("Office hours", "2026-10-22", "16:00–17:00", "Rhodes 412"),
            ("Office hours", "2026-11-19", "16:00–17:00", "Rhodes 412"),
            ("Office hours", "2026-11-24", None, None),
            ("Office hours", "2026-11-26", None, None),
            ("Office hours", "2026-12-01", None, None),
        ],  # fmt: skip
    ),
    Case(
        "add a dentist appointment on nov 3 at 10:30 for an hour at 123 College Ave",
        lambda ids: [
            act(
                "add",
                title="Dentist appointment",
                when="fixed",
                start="2026-11-03T10:30",
                end="2026-11-03T11:30",
                location="123 College Ave",
            ),
        ],  # fmt: skip
        [("Dentist appointment", "2026-11-03", "10:30–11:30", "123 College Ave")],
    ),
    Case(
        "friday's salsa got moved to 9pm and it's at Barton Hall now",
        lambda ids: [
            act(
                "edit",
                id=ids["Salsa 2026-10-23"],
                start="2026-10-23T21:00",
                end="2026-10-23T22:00",
                location="Barton Hall",
            ),
        ],  # fmt: skip
        [("Salsa", "2026-10-23", "21:00–22:00", "Barton Hall")],
    ),
    Case(
        "the wednesday chem lecture on 11/4 is cancelled",
        lambda ids: [act("skip", id=ids["Chem 2090 Lecture 2026-11-04"])],
        [
            ("Chem 2090 Lecture", "2026-11-04", None, None),
            ("Chem 2090 Lecture", "2026-11-06", "12:20–13:10", "Baker 100"),
        ],
    ),
]


# Several kinds at once (27 Oct: "you should be able to parse many different combinations of requests at once"): each
# its own command, in the order said, a rule among them.
CASES += [
    Case(
        "cancel yoga this wednesday, move thursday's discussion to 2pm, and from next monday chem is in Baker 200",
        lambda ids: [
            act("skip", id=ids["Yoga 2026-10-21"]),
            act("edit", id=ids["CS 2112 Discussion 2026-10-22"], start="2026-10-22T14:00", end="2026-10-22T14:50"),
            act("edit", id=ids["Chem 2090 Lecture 2026-10-26"], location="Baker 200", from_date="2026-10-26"),
        ],
        [
            ("Yoga", "2026-10-21", None, None),
            ("CS 2112 Discussion", "2026-10-22", "14:00–14:50", None),
            ("Chem 2090 Lecture", "2026-10-23", "12:20–13:10", "Baker 100"),
            ("Chem 2090 Lecture", "2026-10-26", "12:20–13:10", "Baker 200"),
        ],  # fmt: skip
    ),
    Case(
        "add a study group every sunday 3-5pm at Mann Library starting this sunday but not on 11/8, put salsa on "
        "friday in Willard Straight 215, and add a dentist appointment nov 3 at 10:30 for 45 min",
        lambda ids: [
            act(
                "add",
                title="Study group",
                when="fixed",
                start="2026-10-25T15:00",
                end="2026-10-25T17:00",
                location="Mann Library",
                every="sun",
                exceptions=[{"date": "2026-11-08", "skip": True}],
            ),
            act("edit", id=ids["Salsa 2026-10-23"], location="Willard Straight Hall, room 215"),
            act("add", title="Dentist appointment", when="fixed", start="2026-11-03T10:30", end="2026-11-03T11:15"),
        ],  # fmt: skip
        [
            ("Study group", "2026-10-25", "15:00–17:00", "Mann Library"),
            ("Study group", "2026-11-08", None, None),
            ("Study group", "2026-11-15", "15:00–17:00", "Mann Library"),
            ("Salsa", "2026-10-23", "18:15–19:15", "Willard Straight Hall, room 215"),
            ("Dentist appointment", "2026-11-03", "10:30–11:15", None),
        ],  # fmt: skip
    ),
    Case(
        "no work after 11pm on weeknights, and salsa on saturdays at 1:35-2:40 in Helen Newman starting the 31st, "
        "except halloween it's at Barton Hall at 3",
        lambda ids: [
            act("rule_add", text="no work after 11pm on weeknights", strength="Prefer"),
            act(
                "add",
                title="Salsa",
                when="fixed",
                start="2026-10-31T13:35",
                end="2026-10-31T14:40",
                location="Helen Newman Hall",
                every="sat",
                exceptions=[
                    {
                        "date": "2026-10-31",
                        "location": "Barton Hall",
                        "start": "2026-10-31T15:00",
                        "end": "2026-10-31T16:05",
                    }
                ],
            ),
        ],  # fmt: skip
        [
            ("Salsa", "2026-10-31", "15:00–16:05", "Barton Hall"),
            ("Salsa", "2026-11-07", "13:35–14:40", "Helen Newman Hall"),
        ],
    ),
]


@pytest.mark.parametrize("purpose", ["anything", "rule"])
@pytest.mark.parametrize("case", CASES, ids=[c.text[:60] for c in CASES])
def test_a_scheduling_change_is_proposed_and_makes_the_calendar_it_says(
    app: App, monkeypatch: pytest.MonkeyPatch, case: Case, purpose: str
) -> None:
    ids = calendar(app)
    proposed = case.actions(ids)
    asking(monkeypatch, {"reply": "", "actions": proposed})
    out = app.do("ask_claude", text=case.text, purpose=purpose)
    assert [a["error"] for a in out["actions"]] == [None] * len(proposed)  # taken as proposed, typed anywhere
    for a in out["actions"]:  # applied in order, as Ask Claude and the Rules page apply them
        app.do(a["command"], **a["input"])
    for title, day, times, place in case.expect:
        found = on(app, title, day)
        if times is None:
            assert found is None, f"{title} on {day} should be gone: {found}"
            continue
        assert found is not None, f"no {title} on {day}"
        assert f"{found['start'][11:]}–{found['end'][11:]}" == times, (title, day, found["start"], found["end"])
        assert found["location"] == place, (title, day, found["location"])


def test_claude_is_told_what_these_need() -> None:
    """Places, a repeat's times that differ, one time skipped, and from a date on: what the cases above use."""
    for needed in ("location", "exceptions", "skip: true", "from_date", "skip: {id}", "Willard Straight Hall",
                   "several different things at once"):  # fmt: skip
        assert needed in SYSTEM, needed


def test_a_change_typed_as_a_rule_is_asked_as_a_change(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    claude = asking(monkeypatch, {"reply": "", "actions": []})
    app.do("ask_claude", text=CASES[0].text, purpose="rule")
    assert "change to the calendar itself" in claude.asked[0]["system"]


def test_an_exception_on_a_day_it_doesnt_repeat_is_said_and_a_lone_event_has_none(app: App) -> None:
    out = app.do(
        "add", title="Salsa", when="fixed", start="2026-10-24T13:35", end="2026-10-24T14:40", every="sat",
        exceptions=[{"date": "2026-11-13", "skip": True}],
    )  # fmt: skip
    assert out["warnings"] == ["It doesn't happen on 2026-11-13, so nothing changed that day"]
    with pytest.raises(Exception, match="only a repeat"):
        app.do("add", title="Dentist", when="fixed", start="2026-11-03T10:30", end="2026-11-03T11:30",
               exceptions=[{"date": "2026-11-03", "skip": True}])  # fmt: skip
