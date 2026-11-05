"""Black box: the forty-three people of the hosted Friday's test profiles (HOSTED.md H73–H76), each set up on their
first evening as the app would be (calendars, mail, quick-add, routines, rules) and planned on the default budget.
Whatever they do for a living, what came in lands once as itself and the plan never puts work in their meetings,
shifts, classes or the children's activities.

Monday 2026-10-19 09:00 in New York, as tests/scenarios/test_cornell.py.
"""

import sqlite3
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from friday.sim.cornell import ZONE, Student
from friday.sim.first_evening import hours_by_title, open_student
from friday.sim.people import PEOPLE

MONDAY = date(2026, 10, 19)
NOW = to_utc(parse_local(f"{MONDAY}T09:00"), ZONE.key)


class Planned:
    def __init__(self, person: Student, conn: sqlite3.Connection) -> None:
        self.person, self.conn = person, conn

    def ask(self, query: str, **payload: Any) -> Any:
        return run(self.conn, query, payload, now_utc=NOW, actor="you", provisional=False).result


@pytest.fixture(scope="module")
def planned(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Planned]]:
    out = {}
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        for key, person in PEOPLE.items():
            conn = open_student(tmp_path_factory.mktemp(key) / "friday.db", person, NOW)
            replan(conn, NOW)
            out[key] = Planned(person, conn)
        yield out
    for p in out.values():
        p.conn.close()


@pytest.mark.parametrize("key", PEOPLE)
def test_everything_is_answered_but_unread_mail_and_each_meeting_is_one_repeat_with_its_tag(
    planned: dict[str, Planned], key: str
) -> None:
    p = planned[key]
    waiting = {s["input"].get("title") for s in p.ask("inbox")["suggestions"]}
    unread = {w.title for letter in p.person.letters if letter.unread for w in letter.finds}
    assert waiting <= unread, f"left in the Inbox: {waiting - unread}"
    assert p.ask("calendar_repeats") == []
    series = {s["title"]: s for s in p.ask("series_list")}
    for m in p.person.meetings:
        title = m.plain or m.title
        assert title in series and series[title]["external"], f"{title} isn't a repeat: {sorted(series)}"
        assert series[title]["area"] == m.tag, title


@pytest.mark.parametrize("key", PEOPLE)
def test_each_piece_of_work_due_from_today_arrives_once_with_its_real_length(
    planned: dict[str, Planned], key: str
) -> None:
    p = planned[key]
    items = p.ask("items")
    titles = [i["title"] for i in items]
    now = datetime.combine(MONDAY, time(9))
    unread = {w.title for letter in p.person.letters if letter.unread for w in letter.finds}
    dues = {w.title: w for w in (*p.person.work, *(f for letter in p.person.letters for f in letter.finds))}
    for title, hours in hours_by_title(p.person).items():
        w = dues.get(title)
        if (
            title in unread
            or w is None
            or datetime.combine(MONDAY + timedelta(days=w.day), time.fromisoformat(w.at)) < now
        ):
            continue
        assert titles.count(title) == 1, f"{title} arrived {titles.count(title)} times"
        (item,) = [i for i in items if i["title"] == title]
        assert item["duration_min"] == round(hours * 60), title
        assert item["due"] == f"{MONDAY + timedelta(days=w.day)}T{w.at}", title


@pytest.mark.parametrize("key", PEOPLE)
def test_no_work_is_planned_in_a_meeting_shift_class_or_activity(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    plan = p.ask("plan", start=f"{MONDAY}T00:00", end=f"{MONDAY + timedelta(days=7)}T00:00")
    mine = {m.plain or m.title for m in p.person.meetings}
    busy = [(f["start"], f["end"], f["title"]) for f in plan["fixed"] if f["title"] in mine and "T" in f["start"]]
    assert busy, "their meetings aren't on the plan"
    for b in plan["blocks"]:
        for start, end, title in busy:
            assert not (b["start"] < end and start < b["end"]), f"{b['title']} {b['start']}–{b['end']} is in {title}"


@pytest.mark.parametrize("key", PEOPLE)
def test_their_own_rules_and_routines_are_kept_as_given(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    series = {s["title"] for s in p.ask("series_list")}
    assert {r.title for r in p.person.routines} <= series
    yours = [r for r in p.ask("rules") if r["source"] == "you"]
    assert 1 <= len(yours) <= len(p.person.rules), [r["sentence"] for r in yours]  # one may take another's days


def test_everyone_with_work_ahead_gets_a_plan_with_it(planned: dict[str, Planned]) -> None:
    empty = [k for k, p in planned.items() if p.ask("items") and not p.ask("plan")["blocks"]]
    assert not empty, f"no plan for {empty}"
