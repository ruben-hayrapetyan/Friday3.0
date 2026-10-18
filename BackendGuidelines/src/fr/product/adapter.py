"""Friday-app data -> engine `Scenario` (Q0).

Tasks arrive as Todo List writes them in todos.json (id, title, horizon, bucket, isDone, dueDate as ISO 8601, progress
in quarters); events as the app reads them from EventKit (title, start, end, isAllDay). Todo List has no course or
length fields, so the course comes from a course code in the title ("CS 2110 A4") and the length from the duration
model (estimate / recorded history), passed in as `minutes`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from ..core.builder import ItemSpec, spec
from ..core.generate import Scenario
from ..core.settings import Settings
from . import clock

COURSE = re.compile(r"\b([A-Z]{2,5})\s?(\d{4})\b")
KIND_WORDS = [  # first match wins
    ("exam_prep", re.compile(r"\b(prelim|midterm|exam|final exam|quiz)\b", re.I)),
    ("project", re.compile(r"\bproject\b", re.I)),
    ("essay", re.compile(r"\b(essay|paper|draft|write[- ]?up)\b", re.I)),
    ("lab", re.compile(r"\blab\b", re.I)),
    ("reading", re.compile(r"\b(read|reading|chapter|ch\.)", re.I)),
]
# What a task is, finer than the engine's presets, for constraints that name it ("split problem sets first"). Read from
# the title alone, so a task in the Assignments list that never says so ("make study guide") is not a problem set.
PROBLEM_SET = re.compile(r"\b(prob\w*\s*sets?|p-?sets?|hw\s*\d*|homework|ps\s*\d+|worksheets?|exercises?)\b", re.I)
TYPES = ("problem_set", "essay", "lab", "reading", "exam_prep", "project", "email", "other")
PRESET = {"pset": "assignment", "essay": "assignment", "lab": "assignment", "reading": "reading",
          "exam_prep": "exam_prep", "project": "project", "email": "errand", "other": "assignment"}
HARD_KINDS = {"pset", "essay", "lab", "exam_prep", "project"}


def local(ts: str) -> datetime:
    """ISO 8601 from the app (UTC 'Z' or with an offset) -> naive local wall time."""
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def course_of(title: str) -> str | None:
    m = COURSE.search(title)
    return f"{m.group(1)} {m.group(2)}" if m else None


def kind_of(task: dict) -> str:
    bucket = task.get("bucket")
    if bucket == "emails":
        return "email"
    for kind, rx in KIND_WORDS:
        if rx.search(task["title"]):
            return kind
    if bucket == "readings":
        return "reading"
    if bucket == "assignments":
        return "pset"
    return "other"


def type_of(task: dict) -> str:
    """One of TYPES. Unlike kind_of, which feeds the duration model, a problem set needs the title to say so."""
    if task.get("bucket") != "emails" and PROBLEM_SET.search(task.get("title", "")):
        return "problem_set"
    kind = kind_of(task)
    return kind if kind in TYPES else "other"


@dataclass
class Task:
    """One open task as the engine sees it."""
    id: str  # the app's UUID
    title: str
    course: str | None
    kind: str
    due: int | None  # engine minutes
    progress: float  # 0..1 from the quarters slider
    raw: dict

    @property
    def type(self) -> str:
        return type_of(self.raw)

    @property
    def hard(self) -> bool:
        return self.kind in HARD_KINDS and self.due is not None


def tasks_from(todos: list[dict]) -> list[Task]:
    out = []
    for t in todos:
        if t.get("isDone"):
            continue
        due = clock.to_minutes(local(t["dueDate"])) if t.get("dueDate") else None
        out.append(Task(str(t["id"]), t.get("title", ""), t.get("course") or course_of(t.get("title", "")), kind_of(t),
                        due, min(max(int(t.get("progress", 0)), 0), 3) / 4, t))
    return out


def scenario(now: datetime, tasks: list[Task], minutes: dict[str, float], events: list[dict],
             settings: Settings | None = None) -> tuple[Scenario, dict[int, str]]:
    """The engine instance for this moment. `minutes[task id]` = remaining minutes to plan for (from the duration
    model). Returns the scenario and the map engine item id -> app task id."""
    t0 = clock.to_minutes(now)
    specs: list[ItemSpec] = []
    ids: dict[int, str] = {}
    n = 0
    for ev in events:
        if ev.get("isAllDay"):
            continue
        s, e = clock.to_minutes(local(ev["start"])), clock.to_minutes(local(ev["end"]))
        if e <= t0:
            continue
        n += 1
        kind = "class" if re.search(r"\b(lecture|class|section|discussion|recitation|seminar)\b", ev.get("title", ""), re.I) \
            or COURSE.search(ev.get("title", "")) else "other"
        specs.append(spec("commitment", n, ev.get("title", "event"), start=s, end=e, event_kind=kind,
                          area=course_of(ev.get("title", ""))))
    for t in tasks:
        left = minutes.get(t.id)
        if left is None or left <= 0:
            continue
        n += 1
        ids[n] = t.id
        dur = int(max(15, math.ceil(left / 15) * 15))
        preset = PRESET[t.kind]
        over = dict(area=t.course, duration_min=dur, due=t.due, release=t0, tags=(f"type:{t.type}",),
                    firmness="hard" if t.hard else ("soft" if t.due is not None else "none"))
        if preset in ("assignment", "reading", "exam_prep", "project"):
            over["min_chunk_min"] = min(60 if preset == "project" else 30, dur)
        specs.append(spec(preset, n, t.title, **over))
    return Scenario("friday", specs, [], t0, settings or Settings()), ids


def blocks(c, owner, ids: dict[int, str]) -> list[dict]:
    """Owner array -> [{task_id, start, end}] with contiguous slots merged, ISO local times."""
    g = c.problem.grid
    out = []
    cur = None
    for s in range(g.S):
        o = int(owner[s])
        key = c.keys[o] if o >= 0 else None
        tid = ids.get(int(key.split(":")[1])) if key else None
        if cur is not None and (tid != cur["task_id"] or g.start[s] != cur["_end"]):
            out.append(cur)
            cur = None
        if tid is None:
            continue
        if cur is None:
            cur = dict(task_id=tid, _start=int(g.start[s]), _end=int(g.end[s]))
        else:
            cur["_end"] = int(g.end[s])
    if cur is not None:
        out.append(cur)
    return [dict(task_id=b["task_id"], start=clock.iso(b["_start"]), end=clock.iso(b["_end"])) for b in out]
