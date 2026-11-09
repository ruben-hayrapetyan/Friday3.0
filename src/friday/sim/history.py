"""A Cornell student three weeks into using Friday (`fridayd demo --case NAME --ready`): they started on a Sunday
evening and lived each day since through the same commands as the app, on a clock that moves through the days.

Each morning Friday plans. The student works the plan's blocks: most as planned, some cut short or skipped, about
half of the work timed. Work takes its own time (problem sets longer than Friday thinks, readings shorter): it is
done when it is really done, and time the plan didn't give is logged afterwards. Most evenings they review the day
and answer a few comparisons, but not yesterday's, which waits in Review; each Sunday they say how the week felt.
Overdue work is handed in half done or dropped (one small thing is dropped early on); each Friday a habit is
skipped. A project made from a template runs through it. The weekend before today this week's work arrives
(Canvas, mail): most of it accepted, the rest (unread mail, a moved appointment, something typed in already) left
in the Inbox.
"""

import json
import random
import sqlite3
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from friday.commands.fetching import sync
from friday.commands.refit import prepare_questions
from friday.commands.registry import run
from friday.core.db import connect
from friday.core.time import format_local, parse_local, to_local, to_utc
from friday.sim.cornell import ZONE, Student, monday_of, term, typed_date
from friday.sim.first_evening import accept_inbox, add_routines, connect_google, shifted, type_lines
from friday.sim.sample import Sample

# How long work really takes against what Friday plans, by kind (before a little noise each time).
PACE = {"Assignment": 1.3, "Exam prep": 1.1, "Reading": 0.8, "Errand": 0.75, "Project": 1.2}
FEELS = ("Heavy", "Fine", "Good", "Fine", "Rough", "Good")
# Past days are planned on a small budget: they are history by the time anyone looks, and there are twenty of them.
HISTORY_ENGINE = {"chains": 2, "step_budgets": [{"max_items": 1000, "cold": 100_000, "warm": 50_000}]}
TASTE = {"late_night": 3.0, "weekday_evenings": 2.0}  # the student's weights where they differ from 1
UNIT = 15


class Life:
    """The student's database and clock: commands run at the moment the clock says."""

    def __init__(self, conn: sqlite3.Connection, student: Student, today: date, weeks: int) -> None:
        self.conn, self.student, self.today = conn, student, today
        self.monday = monday_of(today)
        self.first = self.monday - timedelta(weeks=weeks)
        self.rng = random.Random(zlib.crc32(student.key.encode()))
        self.now = 0
        self.real_minutes: dict[int, int] = {}  # each started item's true length
        self.worked: dict[int, int] = {}

    def at(self, day: date, clock: str) -> None:
        """`clock` on planning day `day`; a time before 04:00 is that night, after midnight."""
        moment = datetime.combine(day, datetime.strptime(clock, "%H:%M").time())
        self.now = to_utc(moment + timedelta(days=1) if clock < "04:00" else moment, ZONE.key)

    def do(self, command: str, /, **payload: Any) -> Any:
        return run(self.conn, command, payload, now_utc=self.now, actor="you", provisional=False).result

    def read(self, sample: Sample) -> None:
        self.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
        sync(self.conn, self.now, google=sample.google, mail=sample.gmail, client=sample.ai)

    def wake(self, day: date) -> str:
        return shifted(self.student.sleep[1], 60) if day.weekday() >= 5 else self.student.sleep[1]


def open_lived_in(db_path: Path, student: Student, now_utc: int, weeks: int = 3) -> sqlite3.Connection:
    """A fresh database with `weeks` lived before `now_utc` and the plan made at `now_utc`."""
    today = (to_local(now_utc, ZONE.key) - timedelta(hours=4)).date()  # the planning day: it starts at 04:00
    life = Life(connect(db_path), student, today, weeks)
    life.at(life.first - timedelta(days=1), "20:00")
    life.do("settings_set", key="time", value={"timezone": ZONE.key, "horizon_days": 14})
    life.do("settings_set", key="engine", value=HISTORY_ENGINE)
    start(life)
    day = life.first
    while day < today:
        live_day(life, day)
        day += timedelta(days=1)
    life.now = now_utc
    life.do("settings_set", key="engine", value={})  # the defaults again
    life.do("replan")
    return life.conn


def start(life: Life) -> None:
    """The first evening: Google as it was then, the inbox accepted, routines, the undated quick-add lines, rules."""
    early = term(life.student, life.today, early=True)
    connect_google(life.do, life.student, lambda: life.read(early))
    accept_inbox(life.do, life.student)
    add_routines(life.do, life.student)
    type_lines(life.do, life.student, life.monday, dated_only=False)
    for sentence in life.student.rules:
        life.do("rule_add", text=sentence)


def live_day(life: Life, day: date) -> None:
    if day > life.first:
        life.at(day, "04:00")
        life.do("close_day", date=(day - timedelta(days=1)).isoformat())  # the nightly job: unreviewed days
    life.at(day, life.wake(day))
    morning(life, day)
    life.do("replan")
    outcomes = work_the_plan(life, day)
    life.at(day, "03:45")  # late that night, still the same planning day
    if day < life.today - timedelta(days=1) and life.rng.random() < 0.85:
        review(life, day, outcomes)
        if day < life.first + timedelta(days=7):  # the first week: enough to learn from, not enough to stop asking
            answer_questions(life)
    if day == life.today - timedelta(days=1):
        prepare_questions(life.conn, life.now)  # last night's questions about today, not answered yet
    if day.weekday() == 6:
        life.do("week_note", week=(day - timedelta(days=6)).isoformat(), feel=life.rng.choice(FEELS))
    hand_in_or_drop(life)


def morning(life: Life, day: date) -> None:
    """What comes up on certain mornings: something typed in from a syllabus, this week's work arriving, the
    project made, a habit skipped."""
    student, offset = life.student, (day - life.monday).days
    if day == life.first + timedelta(days=3):
        drop_smallest(life)
    if offset == -2:
        typed_early(life)
        life.read(term(student, life.today))
        accept_inbox(life.do, student)
        type_lines(life.do, student, life.monday, dated_only=True)
        if student.project and student.project.waits_on:
            step, on = student.project.waits_on
            ids = {i["title"]: i["id"] for i in life.do("items")}
            life.do("depend", item_id=ids[step], depends_on_id=ids[on])
    project = student.project
    if project and day == max(life.monday + timedelta(days=project.made), life.first):
        due = f"{life.monday + timedelta(days=project.due)}T23:59"
        life.do("template_apply", template=project.template, title=project.title, hours=project.hours, due=due,
                area=project.area)  # fmt: skip
    if day.weekday() == 4:  # Friday: the next habit is skipped
        habits = [i for i in life.do("items") if i["preset"] == "Habit" and i["series_id"]]
        if habits:
            life.do("skip", id=min(habits, key=lambda i: i["due"] or "")["id"])


def drop_smallest(life: Life) -> None:
    """Not worth it: the smallest piece of work due before this week, still to do, is dropped."""
    past = [i for i in life.do("items") if i["due"] and i["due"] < f"{life.monday}" and i["amount"] == "fixed"]
    past = [i for i in past if not i["series_id"] and i["preset"] != "Exam prep"]
    if past:
        life.do("drop", id=min(past, key=lambda i: (i["duration_min"] or 0, i["due"]))["id"])


def typed_early(life: Life) -> None:
    """Next week's first Canvas assignment, typed in from the syllabus just before Canvas has it: a likely
    duplicate."""
    found = sorted((w for w in life.student.work if w.via == "canvas" and w.day >= 7), key=lambda w: w.day)
    if found:
        w = found[0]
        life.do("add", text=f"{w.title} due {typed_date(life.monday + timedelta(days=w.day))} ~{w.hours:g}h")


def work_the_plan(life: Life, day: date) -> dict[str, tuple[str, float]]:
    """Each of the day's blocks as the student lives it; returns how each went, by block key, for the review."""
    lo = f"{day}T04:00"
    hi = f"{day + timedelta(days=1)}T04:00"
    outcomes: dict[str, tuple[str, float]] = {}
    for block in sorted(life.do("plan", start=lo, end=hi)["blocks"], key=lambda b: b["start"]):
        item = life.do("item", id=block["item_id"])["item"]
        key = block["key"]
        if item["status"] != "todo":
            outcomes[key] = ("not_done", 0.0)
            continue
        roll = life.rng.random()
        if roll < 0.1:
            outcomes[key] = ("not_done", 0.0)
            continue
        share = 0.5 if roll < 0.22 and item["amount"] == "fixed" else 1.0
        outcomes[key] = live_block(life, block, item, share)
    return outcomes


def live_block(life: Life, block: dict[str, Any], item: dict[str, Any], share: float) -> tuple[str, float]:
    """Work a block (or half of it); finish the item when its true length is reached, saying how long it took.
    Timed half the time."""
    begin, end = parse_local(block["start"]), parse_local(block["end"])
    minutes = int((end - begin).total_seconds() // 60 * share) // UNIT * UNIT or UNIT
    item_id = item["id"]
    if item["amount"] == "fixed" and item_id not in life.real_minutes:
        pace = PACE.get(item["preset"] or "", 1.0) * life.rng.lognormvariate(0, 0.15)
        life.real_minutes[item_id] = max(UNIT, round((item["duration_min"] or 0) * pace / UNIT) * UNIT)
    left = life.real_minutes.get(item_id, 10**6) - life.worked.get(item_id, 0)
    minutes = min(minutes, max(UNIT, left))
    life.worked[item_id] = life.worked.get(item_id, 0) + minutes
    whole = int((end - begin).total_seconds() // 60)
    timed = item["amount"] == "fixed" and life.rng.random() < 0.5
    life.now = to_utc(begin, ZONE.key)
    if timed:
        life.do("start", id=item_id)
    life.now += minutes
    if timed:
        life.do("stop")
    if minutes >= left:
        life.do("done", id=item_id, actual_min=life.worked[item_id])
    return ("done", 1.0) if minutes >= whole else ("partial", minutes / whole)


def review(life: Life, day: date, outcomes: dict[str, tuple[str, float]]) -> None:
    """The evening review as it went. What Friday thinks is finished but took longer gets the rest that evening
    (logged), then is done with the time it really took."""
    sheet = life.do("review", date=day.isoformat())
    entries = []
    for block in sheet["blocks"]:
        status, share = outcomes.get(block["key"], ("not_done", 0.0))
        entries.append({"block_key": block["key"], "status": status, "share": share})
    life.do("review_submit", date=day.isoformat(), entries=entries)
    ends = {b["item_id"]: b["end"] for b in sheet["blocks"]}
    for item in life.do("review", date=day.isoformat())["finished"]:
        short = life.real_minutes.get(item["id"], 0) - life.worked.get(item["id"], 0)
        if short > 0:  # straight after its last block that day
            life.worked[item["id"]] += short
            # straight after its last block, ending by the review at the latest: work is logged once it's done
            begin = min(parse_local(ends.get(item["id"], f"{day}T19:00")),
                        to_local(life.now, ZONE.key) - timedelta(minutes=short))  # fmt: skip
            life.do("log", id=item["id"], start=f"{begin:%Y-%m-%dT%H:%M}",
                    end=f"{begin + timedelta(minutes=short):%Y-%m-%dT%H:%M}")  # fmt: skip
        life.do("done", id=item["id"], actual_min=life.worked.get(item["id"]))


def answer_questions(life: Life) -> None:
    """Tomorrow's comparison questions, answered by a steady taste: late nights and evenings cost more to this
    student than to Friday's defaults (each version's rule costs, as Friday stored them with the question)."""
    prepare_questions(life.conn, life.now)
    for q in life.do("questions")["comparisons"]:
        row = life.conn.execute("SELECT features_a, features_b FROM comparisons WHERE id = ?", [q["id"]]).fetchone()
        a, b = (sum(TASTE.get(r, 1.0) * v for r, v in json.loads(f)["rules"].items()) for f in row)
        life.do("compare_answer", id=q["id"], answer="a" if a <= b else "b")


def hand_in_or_drop(life: Life) -> None:
    """Work more than a day overdue is handed in as it is (done) when half of it was done, else dropped."""
    cutoff = format_local(to_local(life.now - 24 * 60, ZONE.key))
    for item in life.do("items"):
        overdue = item["status"] == "todo" and item["due"] and item["due"] < cutoff and item["firmness"] == "hard"
        if not overdue or item["when"] == "fixed" or item["amount"] != "fixed":
            continue
        worked = life.worked.get(item["id"], 0)
        if worked * 2 >= (item["duration_min"] or 0):
            life.do("done", id=item["id"], actual_min=worked)
        else:
            life.do("drop", id=item["id"])
