"""Simulated students for duration learning (RQ11-RQ13).

True length (log minutes) = kind base + course difficulty + course x kind effect + a per-course drift over the term
+ item noise. The student's preliminary estimate sees the item's expected length and part of its own noise, shifted by
a personal bias (the planning fallacy: most people underestimate), a kind-specific bias, and estimate noise. Recorded
actuals are the truth with a little recording noise, rounded to 5 minutes, and sometimes not recorded at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# kind -> (engine preset, typical minutes); titles are what the app would show
KINDS = {
    "pset": ("assignment", 240), "reading": ("reading", 80), "essay": ("assignment", 300), "lab": ("assignment", 180),
    "exam_prep": ("exam_prep", 360), "project": ("project", 600),
}
COURSES = ("CS 2110", "MATH 2940", "PHYS 2213", "ENGL 1170")
# which kinds each course assigns, and how many per week (fractions = some weeks)
SYLLABUS = {
    "CS 2110": {"pset": 1.0, "reading": 0.5},
    "MATH 2940": {"pset": 1.0, "reading": 1.0},
    "PHYS 2213": {"pset": 1.0, "lab": 0.5, "reading": 0.5},
    "ENGL 1170": {"reading": 1.5, "essay": 0.5},
}
PRELIM_WEEKS = (4, 8)
PROJECT = ("CS 2110", 5, 9)  # course, release week, due week


@dataclass(frozen=True)
class StudentType:
    name: str
    bias: float = -0.35  # log(estimate / actual) on average; -0.35 = estimates are 70% of the truth
    kind_bias: dict = field(default_factory=dict)  # extra bias by kind
    est_sigma: float = 0.25  # estimate noise (log)
    insight: float = 0.4  # share of the item's own noise the estimate sees
    bias_trend: float = 0.0  # change of bias per week (drifting habits)
    p_estimate: float = 1.0  # chance an item gets a preliminary estimate
    p_record: float = 0.8  # chance the actual length gets recorded


STUDENT_TYPES = {
    "calibrated": StudentType("calibrated", bias=0.0, est_sigma=0.2, insight=0.5),
    "optimist": StudentType("optimist", bias=-0.45),
    "noisy": StudentType("noisy", bias=-0.2, est_sigma=0.5, insight=0.1),
    "kind_biased": StudentType("kind_biased", bias=-0.05, kind_bias={"pset": -0.5, "essay": -0.6, "lab": -0.3}),
    "drifting": StudentType("drifting", bias=-0.1, bias_trend=-0.06),
    "sparse": StudentType("sparse", bias=-0.35, p_estimate=0.3, p_record=0.5),
}


@dataclass
class Item:
    id: int
    title: str
    course: str
    kind: str
    week: int
    release: int  # minutes (engine time)
    due: int
    true_min: float
    estimate_min: float | None  # preliminary estimate, if given
    _est_if_asked: float  # what the student would answer if asked
    recorded_min: float | None = None  # filled when finished and recorded
    _record_noise: float = 0.0
    _records: bool = True

    @property
    def preset(self) -> str:
        return KINDS[self.kind][0]

    def answer_estimate(self) -> float:
        return self._est_if_asked

    def record(self) -> float | None:
        if not self._records:
            return None
        return float(max(5.0, round(self.true_min * np.exp(self._record_noise) / 5) * 5))

    def answer_actual(self) -> float:
        """Asked later how long it took: a rougher recollection than a timer."""
        return float(max(5.0, round(self.true_min * np.exp(self._record_noise * 2) / 15) * 15))


@dataclass
class Student:
    kind: StudentType
    seed: int
    base: dict  # kind -> log minutes
    course_eff: dict
    ck_eff: dict
    drift_sd: float
    rng: np.random.Generator

    @staticmethod
    def make(kind: str | StudentType, seed: int, item_sigma: float = 0.3, drift_sd: float = 0.05,
             load: float = 1.0, pop_sd: float = 0.2) -> "Student":
        """`load` scales every true length (and so the estimates): 1.5 = a heavier term. `pop_sd`: how far this
        student's typical lengths sit from the population defaults (log sd; E020 round 3 uses 0.5)."""
        k = STUDENT_TYPES[kind] if isinstance(kind, str) else kind
        rng = np.random.default_rng(seed)
        base = {kd: float(np.log(m * load) + rng.normal(0, pop_sd)) for kd, (_, m) in KINDS.items()}
        course = {c: float(rng.normal(0, 0.3)) for c in COURSES}
        ck = {(c, kd): float(rng.normal(0, 0.15)) for c in COURSES for kd in KINDS}
        s = Student(k, seed, base, course, ck, drift_sd, rng)
        s.item_sigma = item_sigma
        s._drift = {c: 0.0 for c in COURSES}
        return s

    def expected_log(self, course: str, kind: str) -> float:
        return self.base[kind] + self.course_eff[course] + self.ck_eff[(course, kind)] + self._drift[course]

    def new_item(self, iid: int, title: str, course: str, kind: str, week: int, release: int, due: int) -> Item:
        r = self.rng
        k = self.kind
        noise = float(r.normal(0, self.item_sigma))
        mu = self.expected_log(course, kind)
        true = float(np.exp(mu + noise))
        bias = k.bias + k.kind_bias.get(kind, 0.0) + k.bias_trend * week
        est = float(np.exp(mu + k.insight * noise + bias + r.normal(0, k.est_sigma)))
        est = max(10.0, round(est / 15) * 15)  # people answer in quarter hours
        given = est if r.random() < k.p_estimate else None
        return Item(iid, title, course, kind, week, release, due, true, given, est,
                    _record_noise=float(r.normal(0, 0.08)), _records=bool(r.random() < k.p_record))

    def end_week(self) -> None:
        for c in COURSES:
            self._drift[c] += float(self.rng.normal(0.02, self.drift_sd))


MONDAY0 = 7  # engine date of week 0's Monday (same epoch convention as core.generate)


def at(date: int, hhmm: str) -> int:
    h, m = hhmm.split(":")
    return date * 1440 + int(h) * 60 + int(m)


def term(student: Student, weeks: int = 10) -> list[Item]:
    """The term's items in release order. Psets due Thu/Fri night, readings before the next class, essays and labs the
    following week, prelim prep before each prelim, one project."""
    r = student.rng
    out: list[Item] = []
    n = 0
    for w in range(weeks):
        mon = MONDAY0 + 7 * w
        for course, kinds in SYLLABUS.items():
            for kind, rate in kinds.items():
                k = int(rate) + (1 if r.random() < rate - int(rate) else 0)
                for j in range(k):
                    n += 1
                    if kind == "pset":
                        rel, due = at(mon, "08:00"), at(mon + int(r.choice([3, 4])), "23:59")
                    elif kind == "reading":
                        d = int(r.integers(0, 5))
                        rel, due = at(mon + d, "08:00"), at(mon + d + 2, "09:00")
                    else:  # essay, lab: a week and a bit
                        rel, due = at(mon, "08:00"), at(mon + 7 + int(r.integers(0, 3)), "23:59")
                    idx = sum(1 for it in out if it.course == course and it.kind == kind) + 1
                    out.append(student.new_item(n, f"{course} {kind} {idx}", course, kind, w, rel, due))
        if w in PRELIM_WEEKS:
            c = COURSES[(w // 4) % 3 + 1 if w // 4 else 1]
            n += 1
            exam = at(mon + 3, "19:30")
            out.append(student.new_item(n, f"{c} prelim {PRELIM_WEEKS.index(w) + 1} prep", c, "exam_prep", w,
                                        at(mon - 5, "08:00"), exam))
        if w == PROJECT[1]:
            n += 1
            out.append(student.new_item(n, f"{PROJECT[0]} final project", PROJECT[0], "project", w, at(mon, "08:00"),
                                        at(MONDAY0 + 7 * PROJECT[2] + 4, "23:59")))
        student.end_week()
    out.sort(key=lambda it: (it.release, it.id))
    return out
