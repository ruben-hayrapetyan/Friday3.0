"""`python -m friday.sim.agenda NAME [--at 2026-10-19T09:00] [--days 7] [--folder DIR]`: set a Cornell student up
in a scratch database (sim/students.py), plan with your engine settings, and print the plan as a student would
read it: each day's classes and work, then each piece of work's sittings against its due, the meals, then what
the plan cost. `all` runs every student. To click through the same student instead: `fridayd demo --case NAME --ready`.
"""

import argparse
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from friday.commands.registry import run
from friday.core.time import parse_local, to_local, to_utc
from friday.planner.service import replan
from friday.sim.cornell import ZONE, Student, monday_of
from friday.sim.first_evening import open_student
from friday.sim.judge import judge
from friday.sim.students import STUDENTS

Rows = list[dict[str, Any]]


def ask(conn: sqlite3.Connection, now_utc: int, query: str, **payload: Any) -> Any:
    return run(conn, query, payload, now_utc=now_utc, actor="you", provisional=False).result


def hm(minutes: float) -> str:
    return f"{int(minutes // 60)}h{int(minutes % 60):02}" if minutes % 60 else f"{int(minutes // 60)}h"


def joined(blocks: Rows) -> list[tuple[datetime, datetime, str, int]]:
    """Back-to-back blocks of one item as one sitting: (start, end, title, item id)."""
    out: list[tuple[datetime, datetime, str, int]] = []
    for b in sorted(blocks, key=lambda b: b["start"]):
        start, end = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
        if out and out[-1][3] == b["item_id"] and out[-1][1] == start:
            out[-1] = (out[-1][0], end, b["title"], b["item_id"])
        else:
            out.append((start, end, b["title"], b["item_id"]))
    return out


def days(plan: dict[str, Any], first: datetime, count: int) -> list[str]:
    """Each day: its fixed events (·) and work (▶) in order, with the hours of work."""
    by_day: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
    work: dict[str, float] = defaultdict(float)
    for f in plan["fixed"]:
        if f.get("start") and f.get("end"):
            start, end = datetime.fromisoformat(f["start"]), datetime.fromisoformat(f["end"])
            mark = "☐" if start.time() == end.time() == datetime.min.time() else "·"
            by_day[start.date().isoformat()].append((start, end, f"{mark} {f['title']}"))
    for start, end, title, _ in joined(plan["blocks"]):
        by_day[start.date().isoformat()].append((start, end, f"▶ {title} ({hm((end - start).seconds / 60)})"))
        work[start.date().isoformat()] += (end - start).seconds / 60
    lines = []
    for n in range(count):
        day = (first + timedelta(days=n)).date()
        lines.append(f"\n{day:%a %b %d}   work {hm(work[day.isoformat()])}")
        for start, end, text in sorted(by_day[day.isoformat()]):
            span = "  all day   " if text.startswith("☐") else f"  {start:%H:%M}–{end:%H:%M}"
            lines.append(f"{span}  {text}")
    return lines


def work_table(plan: dict[str, Any], items: Rows) -> list[str]:
    """Each flexible item: its length, how it is cut, and how early (or late) its last sitting ends."""
    sittings: dict[int, list[tuple[datetime, datetime, str, int]]] = defaultdict(list)
    for s in joined(plan["blocks"]):
        sittings[s[3]].append(s)
    lines = [f"\n{'work':44} {'due':12} {'length':>7} {'planned':>8}  sittings  ends before due"]
    flexible = [i for i in items if i["when"] != "fixed" and i["status"] == "todo"]
    for item in sorted(flexible, key=lambda i: i["due"] or "9999"):
        found = sittings[item["id"]]
        planned = sum((b - a).seconds / 60 for a, b, *_ in found)
        cut = " ".join(hm((b - a).seconds / 60) for a, b, *_ in found)
        margin = ""
        if item["due"] and found:
            early = datetime.fromisoformat(item["due"]) - max(b for _, b, *_ in found)
            margin = "LATE" if early < timedelta(0) else f"{early.days}d {early.seconds // 3600}h"
        due = datetime.fromisoformat(item["due"]).strftime("%a %d %H:%M") if item["due"] else "-"
        length = hm(item["remaining_min"]) if item["remaining_min"] is not None else "open"
        lines.append(f"{item['title'][:44]:44} {due:12} {length:>7} {hm(planned):>8}  {cut:20} {margin}")
    return lines


def meal_lines(plan: dict[str, Any], items: Rows, until: datetime) -> list[str]:
    """Each day's meals: when, how long, and whether inside the window the student gave it."""
    by_day: dict[str, list[str]] = defaultdict(list)
    for m in judge(plan, items, until).meals:
        said = f"{m.title} {m.start} {m.minutes}m" + ("" if m.inside else " OUTSIDE") if m.minutes else f"{m.title} —"
        by_day[m.day].append(said)
    return ["\nMeals (— is none planned)"] + [f"  {day}  " + " · ".join(found) for day, found in sorted(by_day.items())]


def report(conn: sqlite3.Connection, student: Student, now_utc: int, show_days: int) -> str:
    plan = ask(conn, now_utc, "plan")
    items = ask(conn, now_utc, "items")
    status = ask(conn, now_utc, "status")
    local = to_local(now_utc, ZONE.key)
    start = datetime(local.year, local.month, local.day)
    lines = [f"===== {student.name} ({student.load}): {student.about}", *[f"Expect: {n}" for n in student.notes]]
    lines.append(f"Inbox left: {status['suggestions']}; repeats left: {len(ask(conn, now_utc, 'calendar_repeats'))}")
    lines += days(plan, start, show_days)
    lines += work_table(plan, items)
    lines += meal_lines(plan, items, start + timedelta(days=show_days))
    lines.append(f"\nNotices: {status['notices'] or 'none'}")
    totals = {k: v for k, v in ask(conn, now_utc, "rule_totals").items() if v}
    lines.append(f"Rule costs: {totals}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", choices=[*STUDENTS, "all"])
    parser.add_argument("--at", help="local time to plan from (default: this Monday 09:00)")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--folder", type=Path, help="keep the database here to open with fridayd afterwards")
    args = parser.parse_args()
    at = args.at or f"{monday_of(datetime.now().date())}T09:00"
    now_utc = to_utc(parse_local(at), ZONE.key)
    for key in STUDENTS if args.name == "all" else [args.name]:
        with tempfile.TemporaryDirectory() as scratch:
            folder = args.folder / key if args.folder else Path(scratch)
            folder.mkdir(parents=True, exist_ok=True)
            conn = open_student(folder / "friday.db", STUDENTS[key], now_utc)
            replan(conn, now_utc)
            print(report(conn, STUDENTS[key], now_utc, args.days))
            conn.close()


if __name__ == "__main__":
    main()
