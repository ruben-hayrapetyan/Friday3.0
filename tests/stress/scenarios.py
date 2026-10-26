"""Sample schedules: the simulator's seven Cornell students (very light to overloaded), synthetic terms of every size,
and a catalog of edge cases, each built through the same commands as the app. `week()` then lives through the changes
a week brings (a quiet tick, a new task, an urgent one, a finished one, the timer, a missed afternoon, a moved
event, a new rule, a syllabus's worth of tasks, the next morning, an impossible load), replanning after each."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from friday.core.time import format_local, parse_local, to_local, to_utc
from tests.stress.harness import World

ZONE = "America/New_York"
MONDAY = date(2026, 11, 2)  # the week after the clocks change, a plain one
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
RULES = (
    "No work after 11pm",
    "No work before 9am",
    "Deep work in the morning",
    "Keep Saturday mornings free",
    "At most 7 hours a day",
    "Finish things a day early",
    "Go easier on Saturdays",
    "Gym is optional",
    "No work after 10pm the night before Climbing Club",
    "Climbing club only if I'm ahead",
    "Reading only on weekends",
    "No work between 7 and 10am",
    "Keep Fri, Sat 8pm–11:59pm lighter",
)


def at(day: int, hhmm: str, monday: date = MONDAY) -> str:
    return f"{(monday + timedelta(days=day)).isoformat()}T{hhmm}"


def hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


# Synthetic terms


def synthetic(folder: Path, name: str, size: int, seed: int, policy: str = "done") -> World:
    """A term's week with about `size` open tasks: courses with lectures and sections, meals, problem sets,
    readings, labs, a long project, exams with prep, some waiting on others, some pinned, and a few rules."""
    rng = np.random.default_rng(seed)
    world = World.fresh(folder, name, at(0, "08:00"), ZONE, planner=planner(policy))
    courses = max(3, min(7, size // 12 + 2))
    world.do("add", text="Lunch every day 11:30am-2pm 30m")
    world.do("add", text="Dinner every day 5:30pm-8pm 45m")
    for c in range(courses):
        code = f"C{c + 1} {1100 + 10 * c}"
        days = [(0, 2, 4), (1, 3), (0, 2), (1, 3), (0, 4)][c % 5]
        start = int(rng.choice([8 * 60 + 40, 10 * 60 + 10, 11 * 60 + 40, 13 * 60 + 25, 14 * 60 + 55]))
        length = 50 if len(days) == 3 else 75
        world.do("add", title=f"{code} Lecture", when="fixed", start=at(days[0], hhmm(start)),
                 end=at(days[0], hhmm(start + length)), every="rrule:FREQ=WEEKLY;BYDAY=" + byday(days),
                 event_kind="class")  # fmt: skip
        if c % 2 == 0:
            world.do("add", title=f"{code} Section", when="fixed", start=at(c % 5, "16:45"), end=at(c % 5, "17:35"),
                     every="rrule:FREQ=WEEKLY", event_kind="class")  # fmt: skip
    world.do(
        "add", title="Climbing Club", when="fixed", start=at(2, "19:00"), end=at(2, "21:00"), every="rrule:FREQ=WEEKLY"
    )
    world.do(
        "add",
        title="Gym",
        when="fixed",
        start=at(1, "07:30"),
        end=at(1, "09:00"),
        every="rrule:FREQ=WEEKLY;BYDAY=TU,TH",
    )
    ids: list[int] = []
    kinds = ("Assignment", "Reading", "Assignment", "Project", "Chore")
    for n in range(size):
        c = n % courses
        due_day = int(rng.integers(0, 14))
        minutes = max(15, int(round(float(rng.lognormal(np.log(90), 0.6)) / 15)) * 15)
        fields: dict[str, Any] = {
            "title": f"C{c + 1} {kinds[n % len(kinds)]} {n + 1}",
            "preset": kinds[n % len(kinds)],
            "due": at(due_day, str(rng.choice(["09:00", "13:00", "17:00", "23:59"]))),
            "duration_min": min(minutes, 8 * 60),
        }
        if n % 9 == 0:
            fields["shape"] = "one_sitting"
            fields["duration_min"] = min(fields["duration_min"], 180)
        if n % 7 == 0:
            fields["energy"] = "deep"
        ids.append(world.do("add", **fields)["item"]["id"])
    for c in range(0, courses, 2):
        exam = world.do("add", title=f"C{c + 1} Prelim", when="fixed", start=at(9 + c % 4, "19:30"),
                        end=at(9 + c % 4, "21:00"), event_kind="exam")["item"]["id"]  # fmt: skip
        world.do("add", title=f"C{c + 1} prelim study guide", preset="Exam prep", duration_min=240,
                 due=at(9 + c % 4, "19:30"), before=[exam])  # fmt: skip
    world.do("add", title="Research project", duration_min=40 * 60, due=at(27, "17:00"), long_term=True)
    for a, b in zip(ids[::11], ids[5::11], strict=False):  # some work waits on other work
        world.try_do("depend", item_id=b, depends_on_id=a)
    for item_id in ids[3::17]:  # some pinned where you said
        day = int(rng.integers(1, 6))
        world.try_do("pin", id=item_id, start=at(day, "15:00"), end=at(day, "16:00"), kind="preferred")
    for text in rng.choice(RULES, size=4, replace=False):
        world.try_do("rule_add", text=str(text), strength="Prefer")
    return world


def byday(days: tuple[int, ...]) -> str:
    return ",".join(BYDAY[d] for d in days)


def planner(policy: str) -> dict[str, Any]:
    from friday.core.settings import DEFAULTS

    return DEFAULTS["planner"].model_dump() | {"assume_unreviewed": policy}


# A week of changes


def week(world: World, steps: set[str] | None = None, cold: bool = True) -> None:
    """The changes a week brings, a replan after each (timed and checked); `cold`: the first plan too."""

    def want(step: str) -> bool:
        return steps is None or step in steps

    if cold:
        world.replan("cold", warm=False)
    if want("tick"):
        world.replan("tick (nothing changed)", stability=True)
    if want("add"):
        world.do("add", title="New problem set", duration_min=150, due=world.local(world.now + 3 * 1440), quick=True)
        world.replan("add a task")
    if want("urgent"):
        world.do("add", title="Urgent form", duration_min=45, due=world.local(world.now + 4 * 60), quick=True)
        world.replan("add one due in 4 hours")
    if want("done"):
        found = [b for b in world.do("plan")["blocks"] if not b.get("fixed")]
        if found:
            world.do("done", id=found[0]["item_id"], quick=True)
            world.replan("mark one done")
    if want("timer"):
        found = [b for b in world.do("plan")["blocks"] if not b.get("fixed")]
        if found:
            world.do("start", id=found[0]["item_id"], quick=True)
            world.replan("start the timer")
            world.later(50)
            world.do("stop", quick=True)
            world.replan("stop the timer 50 min later")
    if want("missed"):
        world.later(180)
        world.replan("3 hours pass (blocks missed or counted)")
    if want("move_event"):
        events = [f for f in world.do("plan")["fixed"] if f.get("start") and f["start"] > world.local(world.now)]
        if events:
            e = events[0]
            moved = lambda t: format_local(to_local(to_utc(parse_local(t), world.tz) + 60, world.tz))  # noqa: E731
            world.do("edit", id=e["id"], start=moved(e["start"]), end=moved(e["end"]), quick=True)
            world.replan("move an event an hour")
    if want("rule"):
        world.try_do("rule_add", text="never work after 9pm", strength="Always")
        world.replan("add an Always rule")
    if want("bulk"):
        for n in range(25):
            world.do("add", title=f"Syllabus reading {n + 1}", preset="Reading", duration_min=45,
                     due=world.local(world.now + (2 + n % 12) * 1440))  # fmt: skip
        world.replan("25 tasks at once")
    if want("next_day"):
        world.at(world.local(world.now + 1440)[:10] + "T08:00")
        world.try_do("close_day")
        world.replan("next morning (cold, as the nightly job)", warm=False)
    if want("overload"):
        world.do("add", title="Impossible thesis", duration_min=30 * 60, due=world.local(world.now + 1440))
        world.replan("30 h due tomorrow (overload)")


# Cornell students


def student(folder: Path, key: str) -> World:
    from friday.sim.cornell import ZONE as CORNELL
    from friday.sim.first_evening import open_student
    from friday.sim.students import STUDENTS

    now = to_utc(datetime(2026, 10, 19, 19, 0), CORNELL.key)  # a Monday evening, as the scenarios open them
    conn = open_student(folder / f"{key}.db", STUDENTS[key], now)
    return World(f"student {key} ({STUDENTS[key].load})", conn, now, CORNELL.key)


# The edge-case catalog: each builds its world and returns checks to run on the plans it gets.

Check = Callable[[World], list[str]]


@dataclass
class Edge:
    name: str
    build: Callable[[Path], World]
    check: Check | None = None
    steps: set[str] | None = None  # which of the week's changes to live through (None: all)


def blocks_of(world: World, title: str) -> list[dict[str, Any]]:
    return [
        b
        for b in world.do("plan", start=world.local(world.now - 2 * 1440), end=world.local(world.now + 30 * 1440))[
            "blocks"
        ]
        if b["title"] == title
    ]


def expect(cond: bool, message: str) -> list[str]:
    return [] if cond else [message]


def dst_fall_back(folder: Path) -> World:
    w = World.fresh(folder, "dst-fall-back", "2026-10-30T09:00", ZONE)
    w.do("add", title="Weekend essay", duration_min=8 * 60, due="2026-11-02T09:00")
    w.do("add", title="Sunday 1am meeting", when="fixed", start="2026-11-01T01:00", end="2026-11-01T02:30")
    w.do("add", text="Lunch every day 11:30am-2pm 30m")
    return w


def dst_spring_forward(folder: Path) -> World:
    w = World.fresh(folder, "dst-spring-forward", "2027-03-12T09:00", ZONE)
    w.do("add", title="Spring essay", duration_min=10 * 60, due="2027-03-15T09:00")
    w.do("add", title="Sunday 2:30am", when="fixed", start="2027-03-14T03:00", end="2027-03-14T04:00")
    return w


def half_hour_zone(folder: Path) -> World:
    w = World.fresh(folder, "kathmandu-0545", "2026-11-02T08:00", "Asia/Kathmandu")
    for n in range(12):
        w.do("add", title=f"Task {n}", duration_min=60 + 15 * (n % 4), due=at(n % 6 + 1, "17:00"))
    w.do("add", title="Class", when="fixed", start=at(1, "10:10"), end=at(1, "11:25"), every="rrule:FREQ=DAILY")
    return w


def southern_zone(folder: Path) -> World:
    w = World.fresh(folder, "auckland", "2027-04-02T08:00", "Pacific/Auckland")  # clocks go back 4 April 2027
    w.do("add", title="Report", duration_min=12 * 60, due="2027-04-06T17:00")
    return w


def late_sleeper(folder: Path) -> World:
    w = World.fresh(folder, "late-sleeper", at(0, "12:00"), ZONE, bedtime="03:00", wake="11:00")
    for n in range(10):
        w.do("add", title=f"Night owl task {n}", duration_min=90, due=at(n % 5 + 1, "23:59"))
    return w


def bedtime_after_day_start(folder: Path) -> World:
    w = World.fresh(folder, "bed-at-4.30am", at(0, "12:00"), ZONE, bedtime="04:30", wake="12:00")
    w.do("add", title="Essay", duration_min=4 * 60, due=at(2, "23:59"))
    return w


def check_bedtime_after_day_start(w: World) -> list[str]:
    return expect(bool(blocks_of(w, "Essay")) or w.replans[-1].late == 0, "a 4:30am bedtime leaves no day to work in")


def early_bird(folder: Path) -> World:
    w = World.fresh(folder, "early-bird", at(0, "06:00"), ZONE, bedtime="21:00", wake="05:00")
    for n in range(10):
        w.do("add", title=f"Dawn task {n}", duration_min=60, due=at(n % 5 + 1, "12:00"))
    return w


def overdue(folder: Path) -> World:
    w = World.fresh(folder, "already-overdue", at(0, "10:00"), ZONE)
    for n in range(8):
        w.do("add", title=f"Overdue {n}", duration_min=60, due=at(-1 - n % 3, "17:00"))
    return w


def check_overdue(w: World) -> list[str]:
    r = w.replans[0]
    return expect(r.late >= 1, "overdue work isn't said late") + expect(
        r.blocks > 0, "overdue work isn't planned at all"
    )


def due_in_ten(folder: Path) -> World:
    w = World.fresh(folder, "due-in-10-minutes", at(0, "10:00"), ZONE)
    w.do("add", title="Quiz form", duration_min=30, due=at(0, "10:10"))
    return w


def check_due_in_ten(w: World) -> list[str]:
    return expect(w.replans[0].late >= 1, "30 min due in 10 isn't said late")


def huge(folder: Path) -> World:
    w = World.fresh(folder, "40h-in-2-days", at(0, "08:00"), ZONE)
    w.do("add", title="Thesis", duration_min=40 * 60, due=at(2, "08:00"))
    return w


def check_huge(w: World) -> list[str]:
    return expect(w.replans[0].late >= 1, "40 h in 2 days isn't said late")


def tiny_many(folder: Path) -> World:
    w = World.fresh(folder, "300-tiny-tasks", at(0, "08:00"), ZONE)
    for n in range(300):
        w.do("add", title=f"Tiny {n}", duration_min=15, due=at(n % 14, "23:59"))
    return w


def packed(folder: Path) -> World:
    w = World.fresh(folder, "no-free-time", at(0, "08:00"), ZONE)
    w.do("add", title="All-day job", when="fixed", start=at(0, "07:30"), end=at(0, "23:30"), every="rrule:FREQ=DAILY")
    w.do("add", title="Essay", duration_min=3 * 60, due=at(3, "23:59"))
    return w


def check_packed(w: World) -> list[str]:
    # With no free time the only room is the hour past bedtime a deadline may use (23:30 to 00:30).
    outside = [b for b in blocks_of(w, "Essay") if not (b["start"][11:] >= "23:30" or b["end"][11:] <= "00:30")]
    return expect(not outside, f"work squeezed outside the past-bedtime hour: {outside[:2]}")


def all_day_and_overlaps(folder: Path) -> World:
    w = World.fresh(folder, "all-day-and-overlapping-events", at(0, "08:00"), ZONE)
    w.do("add", title="Fall break", when="fixed", start=at(1, "00:00"), end=at(3, "00:00"))
    w.do("add", title="Meeting A", when="fixed", start=at(0, "13:00"), end=at(0, "15:00"))
    w.do("add", title="Meeting B", when="fixed", start=at(0, "14:00"), end=at(0, "16:00"))
    w.do("add", title="Free coffee", when="fixed", start=at(0, "10:00"), end=at(0, "11:00"), free=True)
    for n in range(6):
        w.do("add", title=f"Work {n}", duration_min=120, due=at(4, "17:00"))
    return w


def lock_conflict(folder: Path) -> World:
    w = World.fresh(folder, "lock-over-an-event", at(0, "08:00"), ZONE)
    essay = w.do("add", title="Essay", duration_min=120, due=at(3, "23:59"))["item"]["id"]
    w.do("add", title="Seminar", when="fixed", start=at(1, "14:00"), end=at(1, "16:00"))
    w.try_do("pin", id=essay, start=at(1, "14:00"), end=at(1, "16:00"), kind="locked")
    return w


def pin_in_past(folder: Path) -> World:
    w = World.fresh(folder, "pin-in-the-past", at(0, "08:00"), ZONE)
    essay = w.do("add", title="Essay", duration_min=120, due=at(3, "23:59"))["item"]["id"]
    w.do("pin", id=essay, start=at(0, "09:00"), end=at(0, "11:00"), kind="locked")
    w.later(5 * 60)  # it's 1pm: the pin is over
    return w


def chain(folder: Path) -> World:
    w = World.fresh(folder, "chain-of-20", at(0, "08:00"), ZONE)
    previous = None
    for n in range(20):
        made = w.do(
            "add", title=f"Step {n + 1}", duration_min=45, due=at(6, "23:59"), after=[previous] if previous else []
        )
        previous = made["item"]["id"]
    return w


def circular(folder: Path) -> World:
    w = World.fresh(folder, "circular-dependency", at(0, "08:00"), ZONE)
    a = w.do("add", title="A", duration_min=60, due=at(3, "17:00"))["item"]["id"]
    b = w.do("add", title="B", duration_min=60, due=at(3, "17:00"), after=[a])["item"]["id"]
    refused = w.try_do("depend", item_id=a, depends_on_id=b)
    if not isinstance(refused, Exception):
        w.errors.append("a circular dependency was accepted")
    return w


def exams_two(folder: Path) -> World:
    w = World.fresh(folder, "two-exams-one-course", at(0, "15:00"), ZONE)
    w.do("add", title="CHEM 2090 Quiz 3", when="fixed", start=at(0, "10:00"), end=at(0, "10:50"), event_kind="exam")
    w.do("add", title="CHEM 2090 Midterm", when="fixed", start=at(2, "10:00"), end=at(2, "11:30"), event_kind="exam")
    w.do("add", title="CHEM 2090 midterm review", preset="Exam prep", duration_min=180, due=at(2, "10:00"))
    return w


def check_exams_two(w: World) -> list[str]:
    got = blocks_of(w, "CHEM 2090 midterm review")
    return expect(bool(got), "midterm prep never planned (due taken from the quiz that's over)")


def pointless_late(folder: Path) -> World:
    w = World.fresh(folder, "prep-after-its-quiz", at(0, "08:00"), ZONE)
    w.do("add", title="Math quiz", when="fixed", start=at(0, "09:00"), end=at(0, "09:50"), event_kind="exam")
    w.do("add", title="Math quiz prep", preset="Exam prep", duration_min=5 * 60, due=at(0, "09:00"))
    return w


def check_pointless_late(w: World) -> list[str]:
    late_after = [b for b in blocks_of(w, "Math quiz prep") if b["start"] >= at(0, "09:00")]
    return expect(not late_after, "prep planned after its quiz")


def always_no_time(folder: Path) -> World:
    w = World.fresh(folder, "always-rules-leave-no-time", at(0, "08:00"), ZONE)
    w.do("rule_add", text="No work before noon", strength="Always")
    w.do("rule_add", text="No work after noon", strength="Always")
    w.do("add", title="Report", duration_min=120, due=at(3, "17:00"))
    return w


def check_always_no_time(w: World) -> list[str]:
    return expect(not blocks_of(w, "Report") or w.replans[0].late >= 1, "work planned inside Always-forbidden time")


def optional_overload(folder: Path) -> World:
    w = World.fresh(folder, "optional-events-under-pressure", at(0, "08:00"), ZONE)
    w.do("add", title="Gym", when="fixed", start=at(0, "17:00"), end=at(0, "19:00"), every="rrule:FREQ=DAILY")
    w.do("add", title="Climbing Club", when="fixed", start=at(1, "19:00"), end=at(1, "21:00"))
    w.do("rule_add", text="gym is optional")
    w.do("rule_add", text="climbing club only if i'm ahead")
    w.do("add", title="Big project", duration_min=14 * 60, due=at(2, "08:00"))
    return w


def parts(folder: Path) -> World:
    w = World.fresh(folder, "problem-set-parts", at(0, "08:00"), ZONE)
    for part in ("odds", "evens", "bonus"):
        w.do("add", title=f"PS 7 {part}", preset="Assignment", duration_min=90, due=at(2, "23:59"))
    return w


def check_parts(w: World) -> list[str]:
    order = {p: min((b["start"] for b in blocks_of(w, f"PS 7 {p}")), default="") for p in ("bonus", "evens", "odds")}
    return expect(
        order["bonus"] <= order["evens"] <= order["odds"] or "" in order.values(), f"parts out of order {order}"
    )


def timer_long(folder: Path) -> World:
    w = World.fresh(folder, "timer-runs-long-past-midnight", at(0, "21:00"), ZONE)
    essay = w.do("add", title="Essay", duration_min=120, due=at(2, "23:59"))["item"]["id"]
    w.do("start", id=essay)
    w.later(5 * 60)  # 2am: still timing, three hours past its length
    return w


def missed_days(folder: Path) -> World:
    w = World.fresh(folder, "three-missed-days", at(0, "08:00"), ZONE, planner=planner("not_done"))
    for n in range(10):
        w.do("add", title=f"Work {n}", duration_min=120, due=at(5, "23:59"))
    w.replan("first plan", warm=False)
    w.at(at(3, "08:00"))  # nothing done for three days
    return w


def check_missed_days(w: World) -> list[str]:
    left = sum(i["remaining_min"] or 0 for i in w.do("items"))
    return expect(left == 10 * 120, f"missed work counted as done ({left} of 1200 left)")


def long_horizon(folder: Path) -> World:
    w = World.fresh(folder, "28-day-horizon", at(0, "08:00"), ZONE, horizon_days=28)
    for n in range(60):
        w.do("add", title=f"Long {n}", duration_min=120, due=at(n % 28, "23:59"))
    return w


def day_off(folder: Path) -> World:
    w = World.fresh(folder, "day-off-cap-0", at(0, "08:00"), ZONE)
    w.do("day_override", date=at(1, "")[:10], cap_hours=0)
    for n in range(6):
        w.do("add", title=f"Task {n}", duration_min=120, due=at(3, "23:59"))
    return w


def check_day_off(w: World) -> list[str]:
    day = at(1, "")[:10]
    on = [b for b in w.do("plan", start=day + "T04:00", end=day + "T23:59")["blocks"] if not b.get("fixed")]
    return expect(not on, f"{len(on)} blocks on a day capped at 0 h")


def elastic_open(folder: Path) -> World:
    w = World.fresh(folder, "elastic-open-target", at(0, "08:00"), ZONE)
    w.do("add", title="Practice cello", amount="target", target_min=300, every="week")
    w.do("add", title="Side project", amount="open")
    w.do("add", text="Lunch every day 11:30am-2pm 30m")
    w.do("add", title="Essay", duration_min=180, due=at(2, "23:59"))
    return w


def buffers(folder: Path) -> World:
    w = World.fresh(folder, "travel-buffers", at(0, "08:00"), ZONE)
    w.do("add", title="Downtown appointment", when="fixed", start=at(0, "13:00"), end=at(0, "14:00"),
         buffer_before_min=45, buffer_after_min=45)  # fmt: skip
    w.do("add", title="Essay", duration_min=8 * 60, due=at(0, "23:59"))
    return w


def check_buffers(w: World) -> list[str]:
    near = [b for b in blocks_of(w, "Essay") if b["start"] < at(0, "14:45") and b["end"] > at(0, "12:15")]
    return expect(not near, "work planned in an event's travel time")


def tentative(folder: Path) -> World:
    w = World.fresh(folder, "tentative-and-release", at(0, "08:00"), ZONE)
    w.do("add", title="Maybe talk", duration_min=60, due=at(2, "17:00"), certainty="tentative")
    w.do("add", title="Released later", duration_min=120, release=at(2, "09:00"), due=at(4, "17:00"))
    return w


def check_release(w: World) -> list[str]:
    early = [b for b in blocks_of(w, "Released later") if b["start"] < at(2, "09:00")]
    return expect(not early, "work planned before its release")


def empty(folder: Path) -> World:
    return World.fresh(folder, "empty", at(0, "08:00"), ZONE)


def series_heavy(folder: Path) -> World:
    w = World.fresh(folder, "15-repeating-classes", at(0, "08:00"), ZONE, horizon_days=21)
    for n in range(15):
        day = BYDAY[n % 5]
        w.do("add", title=f"Class {n}", when="fixed", start=at(n % 5, hhmm(8 * 60 + 60 * (n % 9))),
             end=at(n % 5, hhmm(8 * 60 + 60 * (n % 9) + 50)), every=f"rrule:FREQ=WEEKLY;BYDAY={day}")  # fmt: skip
    for n in range(30):
        w.do("add", title=f"Homework {n}", duration_min=60, due=at(n % 20, "23:59"))
    return w


def contradicting(folder: Path) -> World:
    w = World.fresh(folder, "contradicting-preferences", at(0, "08:00"), ZONE)
    w.do("rule_add", text="deep work in the morning", strength="Prefer")
    w.do("rule_add", text="no work before noon", strength="Prefer")
    w.do("add", title="Deep essay", duration_min=4 * 60, due=at(2, "23:59"), energy="deep")
    return w


def runs_by_itself(folder: Path) -> World:
    w = World.fresh(folder, "a-task-that-runs-by-itself", at(0, "08:00"), ZONE)
    w.do("add", title="Lab", when="fixed", start=at(0, "09:00"), end=at(0, "14:00"))
    w.do("add", title="Lab", when="fixed", start=at(0, "17:00"), end=at(0, "23:30"))
    w.do("add", title="Laundry", duration_min=120, due=at(0, "17:00"), background=True)
    w.do("add", title="Essay", duration_min=150, due=at(0, "17:00"))
    return w


def check_runs_by_itself(w: World) -> list[str]:
    (run,) = blocks_of(w, "Laundry") or [{}]
    essay = blocks_of(w, "Essay")
    held = sum(
        1
        for b in w.conn.execute(
            "SELECT b.* FROM blocks b JOIN items i ON i.id = b.item_id "
            "WHERE i.title = 'Laundry' AND b.plan_id = (SELECT max(id) FROM plans)"
        )
    )
    return (
        expect(bool(run.get("background")), "the laundry isn't drawn as running by itself")
        + expect(not w.replans[0].late and bool(essay), "late, though the essay fits beside the laundry")
        + expect(held == 1, f"the plan holds {held} blocks of the laundry, not its start")
    )  # fmt: skip


def prep_close_to_exam(folder: Path) -> World:
    w = World.fresh(folder, "exam-prep-close-to-the-exam", at(0, "08:00"), ZONE)
    exam = w.do("add", title="Chem 2090 Prelim", when="fixed", start=at(4, "19:30"), end=at(4, "21:00"),
                event_kind="exam")["item"]["id"]  # fmt: skip
    w.do("add", title="Prep: Chem 2090 Prelim", preset="Exam prep", duration_min=240, due=at(4, "19:30"), before=[exam])
    quiz = w.do("add", title="Math 1920 Quiz 3", when="fixed", start=at(3, "13:25"), end=at(3, "14:15"),
                event_kind="exam")["item"]["id"]  # fmt: skip
    w.do("add", title="Prep: Math 1920 Quiz 3", preset="Exam prep", duration_min=120, due=at(3, "13:25"), before=[quiz])
    w.do("rule_add", text="I prefer all sessions of exam prep tasks to be done as close to the exam as possible")
    w.do("rule_add", text="prep for the math quiz closer to the math quiz (with 1 day of buffer)")
    return w


def check_prep_close_to_exam(w: World) -> list[str]:
    chem = blocks_of(w, "Prep: Chem 2090 Prelim")
    quiz = blocks_of(w, "Prep: Math 1920 Quiz 3")
    return expect(
        bool(chem) and all(b["start"] >= at(3, "00:00")[:10] for b in chem), f"chem prep not close: {chem[:2]}"
    ) + expect(bool(quiz) and all(b["end"] <= at(2, "13:25") for b in quiz), f"quiz prep inside its buffer: {quiz}")


def skip_for_the_night(folder: Path) -> World:
    w = World.fresh(folder, "skip-the-club-for-the-night-before", at(0, "09:00"), ZONE)
    w.do("add", title="Climbing Club", when="fixed", start=at(2, "06:00"), end=at(2, "08:00"))
    w.do("rule_add", text="climbing club only if i'm ahead")
    w.do("rule_add", text="no work after 10pm the night before climbing club", strength="Always")
    w.do("add", title="Lab", when="fixed", start=at(0, "09:00"), end=at(1, "01:00"))
    w.do("add", title="Lab", when="fixed", start=at(1, "07:00"), end=at(1, "20:00"))
    w.do("add", title="Essay", duration_min=3 * 60, due=at(2, "06:00"))  # due as the club starts: only the night helps
    return w


def check_skip_for_the_night(w: World) -> list[str]:
    essay = blocks_of(w, "Essay")
    notices = w.do("status")["notices"]
    return (
        expect(not w.replans[0].late, "late: skipping the club should free the night before")
        + expect(
            any(b["end"] > at(1, "22:00") and b["start"] < at(2, "04:00") for b in essay),
            "no work past 10pm the night before a skipped club",
        )  # fmt: skip
        + expect(any(n.startswith("Skip Climbing Club") for n in notices), "the plan doesn't say skip")
    )


def done_for_tonight(folder: Path) -> World:
    w = World.fresh(folder, "done-with-work-tonight", at(0, "20:00"), ZONE)
    w.do("settings_set", key="sleep_tracking", value={"on": True})
    w.do("add", title="Reading", duration_min=120, due=at(4, "17:00"))
    w.do("add", title="Quiz corrections", duration_min=45, due=at(0, "23:00"))
    w.do("sleep_mark", kind="done")
    return w


def check_done_for_tonight(w: World) -> list[str]:
    tonight = [b for b in blocks_of(w, "Reading") if b["start"] < at(1, "04:00")]
    corrections = blocks_of(w, "Quiz corrections")
    return expect(not tonight, f"work planned tonight after done with work: {tonight}") + expect(
        bool(corrections) and corrections[0]["start"] < at(0, "23:00"), "work due tonight wasn't kept tonight"
    )


def eating_now(folder: Path) -> World:
    w = World.fresh(folder, "eating-lunch-now", at(0, "12:00"), ZONE)
    w.do("settings_set", key="meal_tracking", value={"on": True})
    w.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
         min_min=15, ideal_min=45, max_min=45)  # fmt: skip
    w.do("add", title="Essay", duration_min=180, due=at(0, "18:00"))
    w.do("meal_start", kind="lunch")
    return w


def check_eating_now(w: World) -> list[str]:
    essay = blocks_of(w, "Essay")
    return expect(not any(b["start"] < at(0, "12:45") for b in essay), f"work planned while you eat: {essay[:2]}")


def repeats_of_every_kind(folder: Path) -> World:
    w = World.fresh(folder, "monthly-and-every-other-week-errands", at(0, "08:00"), ZONE)
    for text in (
        "pay rent every month ~15m",
        "laundry every other week ~1h",
        "groceries every week due sunday ~1h",
        "water plants every 3 days ~10m",
        "haircut every 4 weeks ~1h",
        "problem set every week due fri 5pm ~3h",
    ):
        w.do("add", text=text)
    return w


def check_repeats_of_every_kind(w: World) -> list[str]:
    weekly = blocks_of(w, "groceries")
    rents = w.conn.execute("SELECT count(*) FROM items WHERE title = 'pay rent'").fetchone()[0]
    return expect(len({b["start"][:10] for b in weekly}) >= 1, "weekly groceries never planned") + expect(
        rents >= 2,
        f"{rents} months of rent made",  # due a month out: planned in its last weeks, not yet
    )


EDGES = (
    Edge("DST fall back (1 Nov 2026)", dst_fall_back),
    Edge("DST spring forward (14 Mar 2027)", dst_spring_forward),
    Edge("UTC+5:45 (Kathmandu)", half_hour_zone),
    Edge("Southern clocks back (Auckland)", southern_zone),
    Edge("Late sleeper (3am to 11am)", late_sleeper),
    Edge("Bedtime after the 4am day start", bedtime_after_day_start, check_bedtime_after_day_start),
    Edge("Early bird (9pm to 5am)", early_bird),
    Edge("Everything already overdue", overdue, check_overdue),
    Edge("Due in 10 minutes", due_in_ten, check_due_in_ten),
    Edge("40 h due in 2 days", huge, check_huge),
    Edge("300 tiny tasks", tiny_many),
    Edge("No free time all week", packed, check_packed),
    Edge("All-day, overlapping and free events", all_day_and_overlaps),
    Edge("Locked pin over an event", lock_conflict),
    Edge("Locked pin already past", pin_in_past),
    Edge("Chain of 20 dependencies", chain),
    Edge("Circular dependency refused", circular),
    Edge("Two exams, one course", exams_two, check_exams_two),
    Edge("Prep after its quiz", pointless_late, check_pointless_late),
    Edge("Always rules that leave no time", always_no_time, check_always_no_time),
    Edge("Optional events under pressure", optional_overload),
    Edge("Problem set parts", parts, check_parts),
    Edge("Timer running past midnight", timer_long),
    Edge("Three missed days (plan again)", missed_days, check_missed_days),
    Edge("28-day horizon, 60 tasks", long_horizon),
    Edge("A day off (cap 0)", day_off, check_day_off),
    Edge("Elastic, open and target work", elastic_open),
    Edge("Travel time around an event", buffers, check_buffers),
    Edge("Tentative and released-later work", tentative, check_release),
    Edge("Nothing at all", empty),
    Edge("15 repeating classes, 21 days", series_heavy),
    Edge("Contradicting preferences", contradicting),
    Edge("A task that runs by itself", runs_by_itself, check_runs_by_itself, {"tick"}),
    Edge("Exam prep close to the exam, quiz prep a day early", prep_close_to_exam, check_prep_close_to_exam, {"tick"}),
    Edge("Skip the club for the night before", skip_for_the_night, check_skip_for_the_night, {"tick"}),
    Edge("Done with work tonight", done_for_tonight, check_done_for_tonight, {"tick"}),
    Edge("Eating lunch now", eating_now, check_eating_now, {"tick"}),
    Edge("Monthly, fortnightly and weekly errands", repeats_of_every_kind, check_repeats_of_every_kind),
)
