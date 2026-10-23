"""A Cornell student's first evening with Friday (sim/cornell.py, M15): sleep times, Google and Gmail on, the
calendars switched on and their repeats imported, the inbox answered with the hours things really take, their
routines, quick-add lines and rules, through the same commands as the app.
"""

import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from friday.commands.all import REGISTRY  # noqa: F401  (registers every command)
from friday.commands.fetching import sync
from friday.commands.registry import run
from friday.core.db import connect
from friday.core.time import to_local
from friday.sim.cornell import ZONE, Student, dated, term, typed_date

# Each calendar as the student switches it on: its kind ("auto" lets each event be sorted).
KINDS = {"classes": "auto", "canvas": "auto", "homework": "Assignment", "personal": "auto", "clubs": "auto",
         "work": "Event"}  # fmt: skip
DAY_START_MIN = 4 * 60  # time.day_start: a series' window is counted from it


def hours_by_title(student: Student) -> dict[str, float]:
    """What each suggestion really takes, by the title it arrives with (prep by its exam's)."""
    hours = {w.title: w.hours for w in (*student.work, *(f for letter in student.letters for f in letter.finds))}
    return hours | {f"Prep: {p.title}": p.prep_hours for p in student.prelims}


def tags_by_title(student: Student) -> dict[str, str]:
    return {w.title: w.tag for w in (*student.work, *(f for letter in student.letters for f in letter.finds)) if w.tag}


Do = Callable[..., Any]  # runs a command: do("add", title=…), as tests' App.do


def set_up(do: Do, student: Student, monday: date, read: Callable[[], None]) -> None:
    """The student's first evening with Friday: Google and Gmail on, each suggestion accepted with the hours it
    really takes (but unread mail's), their routines, the typed lines and the rules. `read` runs a sync against the
    student's Google and Gmail."""
    connect_google(do, student, read)
    accept_inbox(do, student)
    add_routines(do, student)
    type_lines(do, student, monday)
    for sentence in student.rules:
        do("rule_add", text=sentence)


def connect_google(do: Do, student: Student, read: Callable[[], None]) -> None:
    """Sleep times, Google and Gmail on, every calendar switched on as its kind, the repeating ones imported with
    their tags."""
    bed, wake = student.sleep
    later = {"bedtime": shifted(bed, 60), "wake": shifted(wake, 60), "margin_min": 60}
    weekday = {"bedtime": bed, "wake": wake, "margin_min": 60}
    sleep = {d: weekday for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": later, "sun": later}
    do("settings_set", key="sleep", value=sleep)
    do("settings_set", key="gcal", value={"read": ["primary"], "include_all_day": True})
    do("settings_set", key="gmail", value={"enabled": True})
    read()
    for key, kind in KINDS.items():
        do("calendar_set", id=f"{key}@g", on=True, kind=kind)
    read()
    import_repeats(do, student)


def add_routines(do: Do, student: Student) -> None:
    """Each routine as the To-do page's repeat would make it: a window counted from the day's start (04:00)."""
    for r in student.routines:
        fields: dict[str, Any] = {"title": r.title, "preset": r.preset, "every": r.every}
        if isinstance(r.minutes, int):
            fields["duration_min"] = r.minutes
        else:
            fields |= dict(zip(("min_min", "ideal_min", "max_min"), r.minutes, strict=True))
        if r.window:
            fields["release_offset_min"] = minutes_of(r.window[0]) - DAY_START_MIN
            fields["due_offset_min"] = minutes_of(r.window[1]) - DAY_START_MIN
        do("series_add", **fields)


def type_lines(do: Do, student: Student, monday: date, dated_only: bool | None = None) -> None:
    """The quick-add lines; with `dated_only`, only those naming a date (True) or none (False)."""
    for line in student.typed:
        if dated_only is None or ("{d" in line) == dated_only:
            do("add", text=dated(line, monday, typed_date))


def minutes_of(clock: str) -> int:
    h, m = map(int, clock.split(":"))
    return h * 60 + m


def shifted(clock: str, minutes: int) -> str:
    total = (minutes_of(clock) + minutes) % (24 * 60)
    return f"{total // 60:02}:{total % 60:02}"


def import_repeats(do: Do, student: Student) -> None:
    tags = {t: m.tag for m in student.meetings if m.tag for t in (m.title, m.plain)}
    waiting = do("calendar_repeats")
    if waiting:
        do("repeats_import", repeats=[{"batch": r["batch"], "area": tags.get(r["title"])} for r in waiting])


def accept_inbox(do: Do, student: Student) -> None:
    """Events first, so each prep is linked to its exam; work with its real hours and tag. What unread mail found,
    a moved event and a likely duplicate stay for the student to answer."""
    hours, tags = hours_by_title(student), tags_by_title(student)
    unread = {w.title for letter in student.letters if letter.unread for w in letter.finds}
    waiting = do("inbox")["suggestions"]
    waiting.sort(key=lambda s: s["input"].get("start") is None)
    for s in waiting:
        title = s["input"].get("title", "")
        if title in unread or s["command"] == "edit" or s["duplicate_of"]:
            continue
        edits: dict[str, Any] = {}
        if title in hours:
            edits["duration_min"] = round(hours[title] * 60)
        if title in tags:
            edits["area"] = tags[title]
        do("suggestion_accept", id=s["id"], edits=edits)


def open_student(db_path: Path, student: Student, now_utc: int, horizon_days: int = 14) -> sqlite3.Connection:
    """A fresh database with the student set up as of `now_utc`, the plan not yet made."""
    conn = connect(db_path)

    def do(command: str, /, **payload: Any) -> Any:
        return run(conn, command, payload, now_utc=now_utc, actor="you", provisional=False).result

    def read() -> None:
        conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
        sync(conn, now_utc, google=sample.google, mail=sample.gmail, client=sample.ai)

    do("settings_set", key="time", value={"timezone": ZONE.key, "horizon_days": horizon_days})
    sample = term(student, to_local(now_utc, ZONE.key).date())
    set_up(do, student, sample.monday, read)
    return conn
