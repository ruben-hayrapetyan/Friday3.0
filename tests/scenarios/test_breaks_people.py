"""Breaks for everybody (18 Nov: "strenuously test on various settings, various schedules"): each of the hosted Friday's
test people (students, workers, parents; very light to overloaded), set up on their first evening, takes four kinds of
break, and what a break promises holds for every one:

- Light, your defaults: every repeat on its days paused, one-off events kept; no day over about N things.
- Off: no work on its days; work due inside is planned before it, or said to be late.
- Light at one a day, pausing one calendar's repeats only, a tag's tasks waiting, meals and sleep kept.
- Light at six a day, from the middle of today.

And for each: no meal on a break day unless it plans meals; no task of a paused tag; every day's list is open tasks with
work that day; ticking every thing off and back on leaves them as they were; deleting the break brings it all back.
Monday 2026-10-19 9am in New York, as tests/scenarios/test_people.py.
"""

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.items import FieldError
from friday.core.rows import item_from_row
from friday.core.settings import Pause
from friday.core.time import parse_local, parse_utc, planning_date, to_utc
from friday.core.vacations import is_meal, pauses
from friday.planner.service import replan
from friday.planner.snapshot import break_calendars
from friday.sim.cornell import ZONE
from friday.sim.first_evening import open_student
from friday.sim.people import PEOPLE

MONDAY = date(2026, 10, 19)
NOW = to_utc(parse_local(f"{MONDAY}T09:00"), ZONE.key)
TZ, DAY_START = ZONE.key, 240
WED, FRI = date(2026, 10, 21), date(2026, 10, 23)


class Person:
    def __init__(self, conn: sqlite3.Connection, now: int = NOW) -> None:
        self.conn, self.now = conn, now

    def do(self, command: str, /, **payload: Any) -> Any:
        return run(self.conn, command, payload, now_utc=self.now, actor="you", provisional=False).result

    def full(self, command: str, /, **payload: Any) -> Any:
        return run(self.conn, command, payload, now_utc=self.now, actor="you", provisional=False)

    def items(self) -> dict[int, dict[str, Any]]:
        return {r["id"]: dict(r) for r in self.conn.execute("SELECT * FROM items WHERE user_id = 1")}

    def blocks(self) -> list[tuple[int, int, int]]:
        plan = self.conn.execute("SELECT id FROM plans ORDER BY id DESC LIMIT 1").fetchone()
        found = self.conn.execute("SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ?", [plan["id"]])
        return [(r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"])) for r in found]


def day_of(minutes: int) -> date:
    return planning_date(minutes, TZ, DAY_START)


@pytest.fixture(scope="module")
def first_evenings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Where each person's first evening is built, once, for every break tried on them."""
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        yield tmp_path_factory.mktemp("people")


def person_with(folder: Path, key: str, tmp: Path, now: int = NOW) -> Person:
    """A copy of the person's first evening (built once), planned."""
    base = folder / f"{key}.db"
    if not base.exists():
        conn = open_student(base, PEOPLE[key], NOW)
        replan(conn, NOW)
        conn.close()
    conn = sqlite3.connect(tmp / "friday.db")
    sqlite3.connect(base).backup(conn)
    conn.close()
    from friday.core.db import connect

    return Person(connect(tmp / "friday.db"), now)


def variants(p: Person) -> dict[str, dict[str, Any]]:
    """The four breaks, the third pausing the person's busiest calendar and their first tag."""
    choices = p.do("break_choices")
    busiest = max(choices["calendars"], key=lambda c: c["repeats"])["name"] if choices["calendars"] else "Friday"
    tags = choices["tags"][:1]
    return {
        "light": {"start": WED.isoformat(), "end": FRI.isoformat()},
        "off": {"start": WED.isoformat(), "end": FRI.isoformat(), "mode": "off"},
        "picky": {"start": WED.isoformat(), "end": FRI.isoformat(), "work_min": 45, "plan_meals": True,
                  "keep_sleep": True, "pause": {"repeating": "only", "calendars": [busiest], "tags": tags}},
        "busy today": {"start": MONDAY.isoformat(), "end": "2026-10-20", "work_min": 270},
    }  # fmt: skip


def check_break(p: Person, made: dict[str, Any]) -> list[str]:
    """What a break promises, each broken promise said."""
    out: list[str] = []
    first, last = date.fromisoformat(made["start"]), date.fromisoformat(made["end"])
    on = lambda d: first <= d <= last  # noqa: E731
    items = p.items()
    pause = Pause.model_validate(made["pause"])
    calendars = break_calendars(p.conn, 1)
    plan = p.do("plan", start=f"{first}T04:00", end=f"{last + timedelta(days=1)}T04:00")
    paused = set(plan["paused"])
    for f in plan["fixed"]:
        if not f.get("start"):
            continue
        d = day_of(to_utc(parse_local(f["start"][:16]), TZ))
        should = on(d) and pauses(pause, series_id=f.get("series_id"), calendar=calendars.get(f["id"]))
        if should != (f["id"] in paused):
            out.append(f"{f['title']} on {d}: paused {f['id'] in paused}, should be {should}")
    per_day: dict[date, int] = {}
    for item_id, start, end in p.blocks():
        d = day_of(start)
        if not on(d) or start < p.now:
            continue
        row = items[item_id]
        item = item_from_row(row)
        if is_meal(item):
            if not made["plan_meals"]:
                out.append(f"{item.title}, a meal, planned on {d}")
            continue
        if made["mode"] == "off":
            out.append(f"{item.title} planned on {d}, an Off day")
        area = p.conn.execute("SELECT name FROM areas WHERE id = ?", [row["area_id"]]).fetchone()
        if area and area["name"] in pause.tags:
            out.append(f"{item.title} ({area['name']}, paused) planned on {d}")
        if row["preset"] not in ("Routine", "Habit"):
            per_day[d] = per_day.get(d, 0) + end - start
    for d, minutes in per_day.items():
        most = made["work_min"]
        if minutes > most + 15:  # a quarter hour's rounding
            out.append(f"{minutes} min of work on {d}, more than the break's about {most} min a day")
    for n in range((last - first).days + 1):
        d = first + timedelta(days=n)
        day = p.do("vacation_day", date=d.isoformat())
        if day["vacation"] is None:
            out.append(f"{d}: not on the break")
        for t in day["items"]:
            item = item_from_row(items[t["item_id"]])
            if is_meal(item) and not made["plan_meals"]:
                out.append(f"{d}: the meal {item.title} on the list")
            if items[t["item_id"]]["status"] != "todo":
                out.append(f"{d}: {item.title} on the list, {items[t['item_id']]['status']}")
    return out


@pytest.mark.parametrize("key", sorted(PEOPLE))
def test_breaks_keep_their_promises(first_evenings: Path, tmp_path: Path, key: str) -> None:
    """Each kind of break on a copy of the person's first evening; then ticking, deleting, and Off's due work."""
    broken: list[str] = []
    for n, kind in enumerate(["light", "off", "picky", "busy today"]):
        folder = tmp_path / f"v{n}"
        folder.mkdir()
        p = person_with(first_evenings, key, folder, NOW + (300 if kind == "busy today" else 0))  # 2pm: mid-day
        made = p.do("vacation_add", name=f"{kind} break", **variants(p)[kind])["vacation"]
        replan(p.conn, p.now)
        broken += [f"{kind}: {b}" for b in check_break(p, made)]
        for query in ("status", "break_choices", "vacations", "inbox"):
            p.do(query)
        p.do("calendar", start=MONDAY.isoformat(), days=7)
        if kind == "off":
            broken += [f"off: {b}" for b in due_inside_off(p)]
        if kind == "light":
            broken += [f"ticking: {b}" for b in tick_and_delete(p, made)]
        p.conn.close()
    assert not broken, "\n".join(broken)


def tick_and_delete(p: Person, made: dict[str, Any]) -> list[str]:
    """Every thing on Wednesday's list ticked off and back on leaves them as they were; deleting the break brings it
    all back."""
    out: list[str] = []
    p.now = to_utc(parse_local(f"{WED}T10:00"), TZ)
    replan(p.conn, p.now)
    before = {i: (r["status"], r["duration_units"]) for i, r in p.items().items()}
    progress = p.conn.execute("SELECT count(*) FROM progress").fetchone()[0]
    things = p.do("vacation_day", date=WED.isoformat())["items"]
    for t in things:
        p.do("vacation_tick", date=WED.isoformat(), item_id=t["item_id"], ticked=True)
    after = p.do("vacation_day", date=WED.isoformat())
    ids = {x["item_id"] for x in things}
    if not all(t["ticked"] for t in after["items"] if t["item_id"] in ids) or (after["vacation"]["ticked"] or 0) < len(
        ids
    ):
        out.append(f"ticked {len(ids)}, the list says {after['vacation']['ticked']}")
    replan(p.conn, p.now)
    for t in things:
        p.do("vacation_tick", date=WED.isoformat(), item_id=t["item_id"], ticked=False)
    now = {i: (r["status"], r["duration_units"]) for i, r in p.items().items()}
    out += [f"item {i} was {before[i]}, now {now.get(i)}" for i in before if now.get(i) != before[i]]
    if p.conn.execute("SELECT count(*) FROM progress").fetchone()[0] != progress:
        out.append("unticking left progress behind")
    p.do("vacation_delete", id=made["id"])
    replan(p.conn, p.now)
    if p.do("plan", start=f"{WED}T04:00", end=f"{FRI}T23:59")["paused"]:
        out.append("events still paused after the break was deleted")
    if any(d["vacation"] for d in p.do("calendar", start=WED.isoformat(), days=3)["days"]):
        out.append("days still on a deleted break")
    return out


def due_inside_off(p: Person) -> list[str]:
    """Work due during an Off break is planned before it, or said to be late (late, or slipping: planned past its due).
    A due with no firmness (a chore's) is a wish, never said late, here as on any day."""
    out: list[str] = []
    status = p.do("status")
    late = {i["item_id"] for i in [*status["late_items"], *status["slipping"]]}
    start = to_utc(parse_local(f"{WED}T04:00"), TZ)
    blocks = p.blocks()
    for item_id, row in p.items().items():
        if row["status"] != "todo" or row["when_kind"] == "fixed" or not row["due_utc"] or row["firmness"] == "none":
            continue
        due = day_of(parse_utc(row["due_utc"]))
        if not WED <= due <= FRI or is_meal(item_from_row(row)) or row["preset"] in ("Routine", "Habit"):
            continue
        if [b for b in blocks if b[0] == item_id and b[1] >= start] and item_id not in late:
            out.append(f"{row['title']}, due {due}, planned on the break and not said late")
    return out


def test_a_break_refuses_what_it_should(first_evenings: Path, tmp_path: Path) -> None:
    p = person_with(first_evenings, "ben", tmp_path)
    p.do("vacation_add", name="One", start=WED.isoformat(), end=FRI.isoformat())
    for bad in ({"start": "2026-10-22", "end": "2026-10-25"}, {"start": FRI.isoformat(), "end": WED.isoformat()}):
        with pytest.raises(FieldError):
            p.do("vacation_add", name="Two", **bad)
