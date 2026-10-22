"""The small model sorting calendar events (M13): each new event's kind and title, one question per repeating event,
the rules standing in without a key, budget or answer, and a calendar's own kind winning."""

import json
from pathlib import Path
from typing import Any

import pytest

from friday.commands.fetching import sync
from friday.ingest import llm
from friday.sim.fakes import FakeGoogle, answered, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


class Sorter:
    """Answers each event asked about with the kind and title its title maps to."""

    def __init__(self, answers: dict[str, tuple[str, str]]):
        self.answers, self.asked = answers, []  # type: list[list[dict[str, Any]]]

    @property
    def messages(self) -> "Sorter":
        return self

    def create(self, **request: Any) -> Any:
        events = json.loads(request["messages"][0]["content"][0]["text"])
        self.asked.append(events)
        items = [
            {"id": e["id"], "kind": k, "title": t}
            for e in events
            if (k_t := self.answers.get(e["title"]))
            for k, t in [k_t]
        ]
        return answered({"items": items})


def all_day(eid: str, summary: str, day: str) -> dict:
    return {"id": eid, "summary": summary, "start": {"date": day}, "end": {"date": day[:8] + str(int(day[8:]) + 1)}}


def read(app: App, calendars: dict[str, list[dict]], client: Any = None, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": list(calendars)})
    google = FakeGoogle({f"{n}@group": e for n, e in calendars.items()}, names={f"{n}@group": n for n in calendars})
    sync(app.conn, app.now_utc + minutes_later, google=google, client=client)


def inbox(app: App) -> dict[str, dict]:
    return {s["input"]["title"]: s["input"] for s in app.do("inbox")["suggestions"]}


HOMEWORK = [
    all_day("prop", "PHYS Project Proposal (TWR)", "2026-10-23"),
    all_day("tba", "CS Assignment (TBA)", "2026-10-22"),
    event("hours", "CS 1110 office hours", "2026-10-21T15:00", "2026-10-21T16:00"),
    event("prelim", "CHEM Prelim 2", "2026-10-22T19:30", "2026-10-22T21:00"),
]
SORTED = {
    "PHYS Project Proposal (TWR)": ("Assignment", "PHYS project proposal"),
    "CS Assignment (TBA)": ("Assignment", "CS assignment"),
    "CS 1110 office hours": ("Meeting", "CS 1110 office hours"),
    "CHEM Prelim 2": ("Exam", "CHEM Prelim 2"),
}


def test_the_small_model_picks_each_events_kind_and_title(app: App) -> None:
    sorter = Sorter(SORTED)
    read(app, {"5. Homework": HOMEWORK}, sorter)
    found = inbox(app)
    assert found["PHYS project proposal"] == {
        "title": "PHYS project proposal",
        "preset": "Assignment",
        "due": "2026-10-23T23:59",
    }
    assert found["CS assignment"]["preset"] == "Assignment"
    assert found["CS 1110 office hours"]["preset"] == "Meeting" and found["CS 1110 office hours"]["start"]
    assert found["CHEM Prelim 2"]["preset"] == "Exam" and found["Prep: CHEM Prelim 2"]["due"] == "2026-10-22T19:30"
    assert [e["calendar"] for e in sorter.asked[0]] == ["5. Homework"] * 4 and len(sorter.asked) == 1
    assert app.do("inbox")["llm"]["calls"] == 1


def test_a_repeating_event_is_asked_about_once_and_unchanged_ones_not_again(app: App) -> None:
    lectures = [
        event(f"l{n}", "CHEM 2090, Lecture", f"2026-10-2{n}T12:20", f"2026-10-2{n}T13:10", recurringEventId="chem")
        for n in (0, 2, 4)
    ]
    sorter = Sorter({"CHEM 2090, Lecture": ("Class", "CHEM 2090 lecture")})
    read(app, {"4. School": lectures}, sorter)
    read(app, {"4. School": lectures}, sorter, minutes_later=60)
    assert len(sorter.asked) == 1 and len(sorter.asked[0]) == 1 and sorter.asked[0][0]["repeats"]
    assert {r["title"] for r in app.do("calendar_repeats")} == {"CHEM 2090 lecture"}


def test_without_a_key_or_answer_the_rules_sort_and_a_failure_shows_on_the_calendar(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "client", lambda: None)
    read(app, {"5. Homework": HOMEWORK})
    assert inbox(app)["CHEM Prelim 2"]["preset"] == "Exam" and "PHYS Project Proposal (TWR)" not in inbox(app)

    class Down(Sorter):
        def create(self, **request: Any) -> Any:
            raise ConnectionError("unreachable")

    read(app, {"6. Events": [event("expo", "Startup Expo", "2026-10-21T15:00", "2026-10-21T19:00")]}, Down({}), 60)
    assert inbox(app)["Startup Expo"]["preset"] == "Event"
    assert "fixed rules" in next(s for s in app.table("sources") if s["name"] == "6. Events")["last_error"]


def test_a_calendar_that_names_its_kind_isnt_asked_about(app: App) -> None:
    sorter = Sorter(SORTED)
    read(app, {"5. Homework": []}, sorter)
    app.do("calendar_set", id="5. Homework@group", kind="Assignment")
    read(app, {"5. Homework": HOMEWORK[:1]}, sorter, minutes_later=60)
    assert sorter.asked == [] and inbox(app)["PHYS Project Proposal (TWR)"]["preset"] == "Assignment"


def test_nothing_is_asked_once_todays_budget_is_spent(app: App) -> None:
    app.do("settings_set", key="llm", value={"daily_calls": 0})
    sorter = Sorter(SORTED)
    read(app, {"5. Homework": HOMEWORK}, sorter)
    assert sorter.asked == [] and inbox(app)["CHEM Prelim 2"]["preset"] == "Exam"


class Noted(Sorter):
    """Answers as the notes would have it: the lab write-up needs nothing, the proposal takes 3 hours."""

    def create(self, **request: Any) -> Any:
        self.system = request["system"]
        events = json.loads(request["messages"][0]["content"][0]["text"])
        said = {"Lab writeup": {"skip": True}, "PHYS Project Proposal (TWR)": {"minutes": 180}}
        items = [
            {"id": e["id"], "kind": "Assignment", "title": e["title"], "skip": False, "minutes": None}
            | said.get(e["title"], {})
            for e in events
        ]
        return answered({"items": items})


def test_what_you_told_friday_skips_entries_and_sets_lengths(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "api_key", lambda: "test-key")
    notes = ["PHYS lab write-ups are done in the lab session", "Project proposals take me about 3 hours"]
    app.do("settings_set", key="notes", value=notes)
    noted = Noted({})
    read(app, {"5. Homework": [all_day("lab", "Lab writeup", "2026-10-22"), HOMEWORK[0]]}, client=noted)
    assert all(n in noted.system for n in notes)
    assert inbox(app) == {"PHYS Project Proposal (TWR)": inbox(app)["PHYS Project Proposal (TWR)"]}
    assert inbox(app)["PHYS Project Proposal (TWR)"]["duration_min"] == 180
