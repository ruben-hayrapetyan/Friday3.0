"""A simulated semester (DESIGN §24.4): what a student tells Friday over a term, and when they tell it.

Each `Event` is a registry command with the local time the student runs it, so the loop exercises the same paths
as the app. Names are generic ("C1 PS3"); nothing personal is shipped.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np

CLASS_DAYS = ("mon,wed", "tue,thu", "mon,wed,fri", "tue,thu")
DUE_WEEKDAY = (1, 3, 4, 2)  # each course's problem set is due on its own weekday (Mon = 0)


@dataclass(frozen=True)
class TermConfig:
    start: date = date(2026, 8, 31)  # a Monday
    weeks: int = 15
    courses: int = 4
    social_per_week: tuple[int, int] = (2, 4)
    sick_rate: float = 0.02  # chance that a day is a sick day


@dataclass(frozen=True)
class Event:
    at: str  # local time the student runs the command
    command: str
    payload: dict[str, Any]


@dataclass
class Term:
    config: TermConfig
    events: list[Event]
    sick_days: set[date] = field(default_factory=set)
    areas: list[str] = field(default_factory=list)


def local(day: date, hhmm: str) -> str:
    return f"{day.isoformat()}T{hhmm}"


def minutes(rng: np.random.Generator, median_h: float, sigma: float = 0.4, most_h: float = 8) -> int:
    """A log-normal length, in whole quarter hours."""
    hours = min(most_h, float(rng.lognormal(np.log(median_h), sigma)))
    return max(15, round(hours * 4) * 15)


def generate_term(config: TermConfig, seed: int) -> Term:
    rng = np.random.default_rng(seed)
    start, end = config.start, config.start + timedelta(weeks=config.weeks)
    areas = [f"C{c + 1}" for c in range(config.courses)]
    setup = local(start, "08:00")
    events = [Event(setup, "area_add", {"name": a}) for a in areas]
    for c, area in enumerate(areas):
        events += course(rng, config, c, area, setup)
    events += life(rng, config, setup)
    events.append(
        Event(
            setup,
            "template_apply",
            {
                "template": "Essay",
                "title": "Term project",
                "hours": 20,
                "area": areas[0],
                "due": local(start + timedelta(weeks=config.weeks - 2, days=4), "17:00"),
            },
        )
    )
    events += social(rng, config)
    sick = {start + timedelta(days=d) for d in range((end - start).days) if rng.random() < config.sick_rate}
    # Nothing is told before the term starts (a short term puts exam prep "two weeks before" earlier).
    events = [e if e.at >= setup else Event(setup, e.command, e.payload) for e in events]
    return Term(config, sorted(events, key=lambda e: e.at), sick, areas)


def course(rng: np.random.Generator, config: TermConfig, c: int, area: str, setup: str) -> list[Event]:
    """Class meetings, a problem set and a reading every week, and two exams with their prep."""
    start, days = config.start, CLASS_DAYS[c % len(CLASS_DAYS)]
    first = start + timedelta(days=0 if days.startswith("mon") else 1)
    hour = 9 + 2 * c
    until = start + timedelta(weeks=config.weeks, days=-3)
    events = [
        Event(
            setup,
            "series_add",
            {
                "title": f"{area} lecture",
                "preset": "Class",
                "area": area,
                "start": local(first, f"{hour:02d}:00"),
                "end": local(first, f"{hour + 1:02d}:15"),
                "every": f"{days} until {until.month}-{until.day}",
            },
        )
    ]
    for week in range(1, config.weeks):
        due = start + timedelta(weeks=week, days=DUE_WEEKDAY[c % len(DUE_WEEKDAY)])
        told = max(start, due - timedelta(days=7))
        events.append(
            Event(
                local(told, "10:00"),
                "add",
                {
                    "title": f"{area} PS{week}",
                    "preset": "Assignment",
                    "area": area,
                    "due": local(due, "23:59"),
                    "duration_min": minutes(rng, 3),
                },
            )
        )
        monday = start + timedelta(weeks=week - 1)
        events.append(
            Event(
                local(monday, "09:00"),
                "add",
                {
                    "title": f"{area} reading {week}",
                    "preset": "Reading",
                    "area": area,
                    "due": local(monday + timedelta(days=6), "23:59"),
                    "duration_min": minutes(rng, 1, 0.3, 3),
                },
            )
        )
    for name, week in (("midterm", config.weeks // 2), ("final", config.weeks - 1)):
        exam = start + timedelta(weeks=week, days=2 + c % 3)
        events.append(
            Event(
                setup,
                "add",
                {
                    "title": f"{area} {name}",
                    "preset": "Event",
                    "area": area,
                    "start": local(exam, "14:00"),
                    "end": local(exam, "16:00"),
                },
            )
        )
        events.append(
            Event(
                local(exam - timedelta(days=14), "10:00"),
                "add",
                {
                    "title": f"{area} {name} prep",
                    "preset": "Exam prep",
                    "area": area,
                    "due": local(exam, "14:00"),
                    "duration_min": minutes(rng, 6, 0.3, 12),
                },
            )
        )
    return events


def life(rng: np.random.Generator, config: TermConfig, setup: str) -> list[Event]:
    """Meals, chores, two habits and a weekly goal, all repeating from the first day."""
    first = config.start.isoformat()

    def series(**payload: Any) -> Event:
        return Event(setup, "series_add", {"start_date": first} | payload)

    meal = {"preset": "Routine", "every": "day", "min_min": 20, "ideal_min": 30, "max_min": 45}
    return [
        series(title="lunch", release_offset_min=450, due_offset_min=630, **meal),  # 11:30–14:30
        series(title="dinner", release_offset_min=840, due_offset_min=990, **meal),  # 18:00–20:30
        series(title="laundry", preset="Chore", every="week", duration_min=60),
        series(title="groceries", preset="Errand", every="week", duration_min=45),
        series(title="gym", preset="Habit", every="week", per_window=3, duration_min=60),
        series(title="meditate", preset="Habit", every="day", duration_min=15),
        series(title="guitar", preset="Goal", every="week", target_min=180),
    ]


def social(rng: np.random.Generator, config: TermConfig) -> list[Event]:
    """Two to four evenings out a week, told that morning."""
    low, high = config.social_per_week
    events = []
    for week in range(config.weeks):
        for d in rng.choice(7, size=int(rng.integers(low, high + 1)), replace=False):
            day = config.start + timedelta(weeks=week, days=int(d))
            events.append(
                Event(
                    local(day, "10:00"),
                    "add",
                    {
                        "title": "evening out",
                        "preset": "Event",
                        "start": local(day, "19:00"),
                        "end": local(day, "22:00"),
                    },
                )
            )
    return events
