"""Two Cornell students three weeks into using Friday, as `fridayd demo --case NAME --ready` serves them
(sim/history.py): every page has something on it. Insights and the weekly review show the work done and how long it
really took, yesterday's review waits, some of the inbox is left, a project from a template is under way, their own
rules are there in their words, and Friday has learned from a few answered comparisons.

Monday 2026-10-19 09:00 in New York, as in test_cornell.py.
"""

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.time import parse_local, to_utc
from friday.sim.cornell import ZONE
from friday.sim.history import open_lived_in
from friday.sim.students import STUDENTS

NOW = to_utc(parse_local("2026-10-19T09:00"), ZONE.key)
LIVED = ("jordan", "daniel")  # a moderate week and a heavy one, each with a project waiting on other work


@pytest.fixture(scope="module")
def lived(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, sqlite3.Connection]]:
    """Each student's three weeks, lived once (about half a minute each)."""
    out = {}
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        for key in LIVED:
            out[key] = open_lived_in(tmp_path_factory.mktemp(key) / "friday.db", STUDENTS[key], NOW)
        yield out
    for conn in out.values():
        conn.close()


def ask(conn: sqlite3.Connection, query: str, **payload: Any) -> Any:
    return run(conn, query, payload, now_utc=NOW, actor="you", provisional=False).result


@pytest.mark.parametrize("key", LIVED)
def test_insights_show_three_weeks_of_work_and_that_assignments_take_longer_than_planned(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    found = ask(lived[key], "insights")
    # Work only: meals and habits aren't counted, so three weeks is a dozen-odd things, not fifty.
    assert found["done"] >= 10 and found["hours"] >= 20 and found["best_hours"]
    kinds = {k["kind"]: k for k in found["by_kind"]}
    assert kinds["Assignment"]["n"] >= 3 and kinds["Assignment"]["median"] > 1.1
    assert "Exam prep" in kinds  # last term's first prelim
    assert sum(map(sum, found["heat"])) > 0


@pytest.mark.parametrize("key", LIVED)
def test_last_weeks_review_has_planned_against_done_what_finished_and_how_it_felt(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    week = ask(lived[key], "week_review", date="2026-10-12")
    assert any(a["actual_h"] > 0 for a in week["areas"]) and any(a["planned_h"] > 0 for a in week["areas"])
    assert week["finished"] and week["deadlines"] and week["note"]["feel"]


@pytest.mark.parametrize("key", LIVED)
def test_yesterday_waits_in_review_after_days_that_were_reviewed_timed_and_skipped(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    conn = lived[key]
    yesterday = ask(conn, "review", date="2026-10-18")
    assert not yesterday["reviewed"] and yesterday["blocks"]
    days = [ask(conn, "review", date=f"2026-10-{d:02}") for d in range(1, 18)]
    assert sum(d["reviewed"] for d in days) >= 10
    sources = {s["source"] for d in days for s in d["sessions"]}
    assert {"timer", "review", "retro"} <= sources
    assert ask(conn, "items", status="skipped") and ask(conn, "items", status="dropped")


@pytest.mark.parametrize("key", LIVED)
def test_the_inbox_keeps_unread_mail_a_moved_event_and_sets_aside_a_duplicate(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    inbox = ask(lived[key], "inbox")
    waiting = inbox["suggestions"]
    unread = {w.title for letter in STUDENTS[key].letters if letter.unread for w in letter.finds}
    moved = {e.title for e in STUDENTS[key].events if e.was}
    assert unread <= {s["input"].get("title") for s in waiting}
    assert moved <= {s["input"].get("title") for s in waiting if s["command"] == "edit"}
    # 27 Oct: what you have already isn't asked; the inbox lists it set aside, to add anyway.
    assert inbox["set_aside"]


@pytest.mark.parametrize("key", LIVED)
def test_a_project_from_a_template_is_under_way_and_a_step_waits_on_other_work(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    conn, project = lived[key], STUDENTS[key].project
    assert project and project.waits_on
    found = next(p for p in ask(conn, "projects") if p["item"]["title"] == project.title)
    steps = {c["title"]: c for c in found["children"]}
    assert len(steps) == 3 and sum(c["done_min"] for c in steps.values()) > 0
    step, on = project.waits_on
    waits = {d["depends_on_id"] for d in ask(conn, "item", id=steps[step]["id"])["depends_on"]}
    others = {i["id"] for i in ask(conn, "items", status="all") if i["title"] == on}
    assert waits & others


@pytest.mark.parametrize("key", LIVED)
def test_their_own_rules_are_there_in_their_words_and_friday_learned_from_answers(
    lived: dict[str, sqlite3.Connection], key: str
) -> None:
    conn = lived[key]
    own = [r for r in ask(conn, "rules") if r["source"] != "default"]
    assert 2 <= len(own) == len(STUDENTS[key].rules) <= 5
    learned = ask(conn, "learning")
    assert learned["comparisons"] >= 5 and learned["suggested"]
