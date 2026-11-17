"""0.5.0's Projects page replaced the old one (16 Nov: "i don't want other users' previous projects to get deleted if
they had some on the old layout"). Whole system, over synthetic people: what someone made before it (projects, one
finished, an exam with prep, a weekly goal made as a plain repeat) is all on the new page, and listing it changes
nothing the planner does. The same was checked once across versions: the fifty profiles built by 0.4.x opened here."""

import sqlite3
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from friday.sim.cornell import ZONE
from friday.sim.first_evening import open_student
from friday.sim.people import PEOPLE

MONDAY = date(2026, 10, 19)
NOW = to_utc(parse_local(f"{MONDAY}T09:00"), ZONE.key)
WHO = ("ava", "jonah", "uma", "kai")  # a student, an office worker, a parent, a shift worker


def ask(conn: sqlite3.Connection, verb: str, **payload: Any) -> Any:
    return run(conn, verb, payload, now_utc=NOW, actor="you", provisional=False).result


def before_050(conn: sqlite3.Connection) -> dict[str, int]:
    """What the old page made: a project from a template, one finished, an exam with prep, and a weekly goal."""
    essay = ask(conn, "template_apply", template="Essay", title="History essay", hours=6)["item"]["id"]
    talk = ask(conn, "template_apply", template="Presentation", title="Club talk", hours=3)["item"]["id"]
    for step in [c["id"] for p in ask(conn, "projects") if p["item"]["id"] == talk for c in p["children"]]:
        ask(conn, "done", id=step)
    ask(conn, "done", id=talk)
    exam = ask(conn, "add", title="Stats midterm", preset="Exam", start="2026-10-29T10:00", end="2026-10-29T11:30")
    ask(conn, "add", title="Practice midterm", preset="Exam prep", duration_min=120, due="2026-10-29T10:00",
        before=[exam["item"]["id"]])  # fmt: skip
    goal = ask(conn, "series_add", title="Read for fun", preset="Goal", amount="target", target_min=180, every="week")
    return {"essay": essay, "talk": talk, "exam": exam["item"]["id"], "goal": goal["id"]}


@pytest.fixture(scope="module")
def people(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, tuple[sqlite3.Connection, dict[str, int]]]]:
    out = {}
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        for key in WHO:
            conn = open_student(tmp_path_factory.mktemp(key) / "friday.db", PEOPLE[key], NOW)
            made = before_050(conn)
            replan(conn, NOW)
            out[key] = (conn, made)
        yield out
    for conn, _ in out.values():
        conn.close()


@pytest.mark.parametrize("who", WHO)
def test_everything_made_before_is_on_the_new_page(people: dict, who: str) -> None:
    conn, made = people[who]
    assert made["essay"] in {p["item"]["id"] for p in ask(conn, "projects")}
    assert made["talk"] in {f["id"] for f in ask(conn, "projects_finished")}
    assert made["exam"] in {e["item"]["id"] for e in ask(conn, "exams")}
    [goal] = [o for o in ask(conn, "ongoing_projects") if o["id"] == made["goal"]]
    assert goal["as_before"] and goal["hours_per_week"] == 3


@pytest.mark.parametrize("who", WHO)
def test_listing_it_writes_nothing(people: dict, who: str) -> None:
    """The page only reads: every table as it was, so the planner has nothing new to go on. (Comparing two plans
    instead was flaky: a heavy week's deadline fallback is timed, the one budget in seconds.)"""
    conn, _ = people[who]
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]

    def everything() -> dict[str, list[tuple]]:
        return {t: sorted(map(tuple, conn.execute(f"SELECT * FROM {t}")), key=repr) for t in tables}

    before = everything()
    for query in ("projects", "projects_finished", "exams", "ongoing_projects", "project_options"):
        ask(conn, query)
    assert everything() == before
