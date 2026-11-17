"""The whole system, on many synthetic people (students, workers, parents, shift workers, freelancers; very light to
overloaded): an ongoing project with a rhythm planned beside everything else they have. Its week never takes more than a
piece a day, never sits in their classes, meetings or shifts, and a project with no rhythm plans as a Goal did. A short
week, missed whole, carries half into the next, which then asks for more.

Monday 2026-10-19 09:00 in New York, as tests/scenarios/test_people.py.
"""

import sqlite3
from collections import Counter
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.time import parse_local, parse_utc, to_local, to_utc
from friday.planner.service import replan
from friday.sim.cornell import ZONE
from friday.sim.first_evening import open_student
from friday.sim.people import PEOPLE

MONDAY = date(2026, 10, 19)
NOW = to_utc(parse_local(f"{MONDAY}T09:00"), ZONE.key)
# One of each: light and heavy students, office workers, parents, shift workers and a freelancer.
WHO = ("ava", "grace", "jonah", "kira", "uma", "gus", "kai", "nia")


def ask(conn: sqlite3.Connection, verb: str, now: int = NOW, **payload: Any) -> Any:
    return run(conn, verb, payload, now_utc=now, actor="you", provisional=False).result


@pytest.fixture(scope="module")
def planned(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, tuple[sqlite3.Connection, int]]]:
    out = {}
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        for key in WHO:
            conn = open_student(tmp_path_factory.mktemp(key) / "friday.db", PEOPLE[key], NOW)
            series = ask(conn, "ongoing_add", title="Guitar practice", hours_per_week=3)["id"]
            ask(conn, "ongoing_set", id=series, rhythm_days=3)
            replan(conn, NOW)
            out[key] = (conn, series)
        yield out
    for conn, _ in out.values():
        conn.close()


def this_week(conn: sqlite3.Connection, series: int) -> int:
    return ask(conn, "ongoing_projects")[0]["week"]["item_id"]


def blocks_of(conn: sqlite3.Connection, item_id: int) -> list[tuple[int, int]]:
    plan = conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()[0]
    found = conn.execute("SELECT start_utc, end_utc FROM blocks WHERE plan_id = ? AND item_id = ?", [plan, item_id])
    return [(parse_utc(a), parse_utc(b)) for a, b in found]


@pytest.mark.parametrize("key", WHO)
def test_a_rhythms_week_takes_at_most_a_piece_a_day(planned: dict, key: str) -> None:
    conn, series = planned[key]
    by_day: Counter[date] = Counter()
    for start, end in blocks_of(conn, this_week(conn, series)):
        by_day[to_local(start, ZONE.key).date()] += end - start
    assert all(minutes <= 60 for minutes in by_day.values()), f"{key}: {dict(by_day)}"  # 3 h in 3: an hour a day


@pytest.mark.parametrize("key", WHO)
def test_it_never_sits_in_their_fixed_time(planned: dict, key: str) -> None:
    conn, series = planned[key]
    fixed = [
        (parse_utc(a), parse_utc(b))
        for a, b in conn.execute(
            "SELECT start_utc, end_utc FROM items WHERE \"when\" = 'fixed' AND blocks_time = 1 AND status = 'todo' "
            "AND start_utc IS NOT NULL"
        )
    ]
    for start, end in blocks_of(conn, this_week(conn, series)):
        assert not any(a < end and start < b for a, b in fixed), f"{key}: a piece at {to_local(start, ZONE.key)}"


def test_most_people_get_some_of_it_planned(planned: dict) -> None:
    # Before first_chunk_units kept to the rhythm, a week with a most-a-day under two hours was planned for no one.
    got = [key for key, (conn, series) in planned.items() if blocks_of(conn, this_week(conn, series))]
    assert len(got) >= len(WHO) // 2, got


def test_a_missed_week_carries_half_into_the_next(planned: dict) -> None:
    conn, series = planned["jonah"]
    next_monday = to_utc(parse_local("2026-10-26T09:00"), ZONE.key)
    [shown] = ask(conn, "ongoing_projects", now=next_monday)
    done = shown["past"][-1]["done_min"]
    assert shown["week"]["carried_min"] == round(0.5 * (180 - done))
    assert shown["week"]["target_min"] == 180 + shown["week"]["carried_min"]
