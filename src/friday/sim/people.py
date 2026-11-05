"""Forty-three made-up people to try the hosted Friday on (HOSTED.md, before S1), beside the seven Cornell students:
students at a made-up university, people with jobs, parents and carers, and shift workers and freelancers, each from
very light to overloaded. A person is made from their key alone, so they are the same every time, and is a
`Student` (sim/cornell.py) so everything that sets a student up, lives their weeks or serves them works on them:
their calendars carry their own names (Work, Kids, Shifts…) and their mail comes from managers, schools and clients.
"""

import random
import zlib
from typing import Literal

from friday.sim.cornell import (
    Event,
    Letter,
    Meeting,
    Prelim,
    Project,
    Routine,
    Student,
    Work,
    course,
    each_week,
    meals,
)
from friday.sim.people_pools import (
    ALL_DAY,
    APPOINTMENTS,
    CARE,
    CLIENTS,
    COURSES,
    FIRST,
    FREELANCE,
    JOB_TASKS,
    JOBS,
    KID_ACTIVITIES,
    KIDS,
    LAST,
    MWF_SLOTS,
    PARENT_TASKS,
    RULES,
    SECTION_SLOTS,
    SHIFT_JOBS,
    TR_SLOTS,
    TYPED,
    WEEKLY_WORK,
)

Kind = Literal["student", "worker", "parent", "shift"]
Load = Literal["very light", "light", "moderate", "heavy", "very heavy", "overloaded"]
LOADS: tuple[Load, ...] = ("very light", "light", "moderate", "moderate", "heavy", "very heavy", "overloaded")
SCALE = {"very light": 0.5, "light": 0.75, "moderate": 1.0, "heavy": 1.35, "very heavy": 1.7, "overloaded": 2.4}
HOW_MANY: dict[Kind, int] = {"student": 8, "worker": 12, "parent": 12, "shift": 11}
TAKEN = {"maya", "alex", "jordan", "elena", "priya", "daniel", "riley"}  # the Cornell students' keys
# Every calendar named for the person's life, each name once: (classes, canvas, homework, personal, clubs, work).
CALENDAR_NAMES = {
    kind: dict(zip(("classes", "canvas", "homework", "personal", "clubs", "work"), names, strict=True))
    for kind, names in {
        "student": ("Classes", "Coursework", "Homework", "Personal", "Clubs", "Job"),
        "worker": ("Work", "Asana", "Deadlines", "Personal", "Friends", "Side gig"),
        "parent": ("Work", "Family to-dos", "School", "Family", "Kids", "Bookshop"),
        "shift": ("Appointments", "To-dos", "Deadlines", "Personal", "Friends", "Shifts"),
        "freelance": ("Clients", "Trello", "Deadlines", "Personal", "Friends", "Studio"),
    }.items()
}
NEWSLETTERS = (
    Letter("City Library <news@citylibrary.org>", "This month at the library", "Events and new books.", bulk=True),
    Letter("Grocer Plus <deals@grocerplus.com>", "Your weekly deals are here", "Save on fruit this week.", bulk=True),
    Letter("Streamly <hello@streamly.tv>", "New this week", "Shows we think you'll like.", bulk=True),
)  # fmt: skip


def clock(minutes: int) -> str:
    return f"{minutes // 60 % 24:02}:{minutes % 60:02}"


def minutes(at: str) -> int:
    h, m = map(int, at.split(":"))
    return h * 60 + m


def later(at: str, by: int) -> str:
    return clock(minutes(at) + by)


def hours(rng: random.Random, base: float, load: Load) -> float:
    """A length near `base`, more for a heavier load, in quarter hours."""
    return max(0.25, round(base * SCALE[load] * rng.uniform(0.8, 1.25) * 4) / 4)


def count(rng: random.Random, load: Load, few: int, many: int) -> int:
    return max(1, round((few + (many - few) * (SCALE[load] - 0.5) / 1.9) + rng.uniform(-0.5, 0.5)))


def appointments(rng: random.Random, n: int) -> tuple[Event, ...]:
    """One-off appointments over the next weeks (one moved from where it was) and a birthday or two."""
    out = []
    for i, (title, kind, length) in enumerate(rng.sample(APPOINTMENTS, n)):
        day, start = rng.randint(-9, 18), clock(rng.choice(range(9 * 60, 19 * 60, 30)))
        moved = (later(start, -120), later(start, -120 + length)) if i == 0 else None
        out.append(Event(title, day, start, later(start, length), kind=kind, was=moved))
    out += [Event(t, rng.randint(1, 20)) for t in rng.sample(ALL_DAY, rng.randint(1, 2))]
    return tuple(out)


def typed(rng: random.Random, kind: Kind, n: int) -> tuple[str, ...]:
    return tuple(rng.sample(TYPED["any"], n) + rng.sample(TYPED[kind], 1))


def rules(rng: random.Random, kind: Kind) -> tuple[str, ...]:
    return tuple(rng.sample(RULES["any"], rng.randint(1, 2)) + rng.sample(RULES[kind], 1))


def a_student(rng: random.Random, load: Load, n_: int) -> dict:
    n = min(len(MWF_SLOTS), count(rng, load, 3, 6))
    mwf, tr, sections = rng.sample(MWF_SLOTS, 3), rng.sample(TR_SLOTS, 3), rng.sample(SECTION_SLOTS, 5)
    meetings, work, prelims, letters = [], [], [], []
    taking = rng.sample(COURSES, n)
    for i, (code, _what) in enumerate(taking):
        days, (start, end) = ("MWF", mwf[i // 2]) if i % 2 == 0 else ("TR", tr[i // 2])
        parts = [("LEC 001", days, start, end)]
        if rng.random() < 0.5:
            parts.append(("DIS 201", *sections[i]))
        meetings += course(code, *parts)
        task, kind, base = rng.choice(WEEKLY_WORK)
        due = (i * 2 + 1) % 5
        work += each_week(f"{code} {task} {{n}}", due, hours(rng, base, load), first=7, kind=kind, tag=code)
        if rng.random() < 0.45:
            prelims.append(Prelim(f"{code} Midterm", rng.randint(-6, 12), prep_hours=hours(rng, 4, load)))
        if rng.random() < 0.35:
            essay = Work(f"{code} short essay", rng.randint(3, 16), hours(rng, 3, load), via="mail", tag=code)
            letters.append(Letter(f"Prof. {rng.choice(LAST)} <prof@example.edu>", f"{code}: short essay",
                                  f"The short essay is due {{d{essay.day}}} at 11:59pm.", finds=(essay,),
                                  unread=rng.random() < 0.3))  # fmt: skip
    code = meetings[0].tag or ""
    project = Project("Essay", f"{code} term paper", hours(rng, 9, load), due=rng.randint(15, 26), made=-10, area=code)
    return {"meetings": meetings, "work": work, "prelims": prelims, "letters": letters, "area": "school",
            "project": project if rng.random() < 0.5 else None, "sleep": rng.choice((("00:30", "08:30"),
            ("23:45", "07:45"), ("01:00", "09:30"))), "meals": meals(("11:30", "14:00"), ("17:30", "20:30")),
            "calendars": CALENDAR_NAMES["student"],
            "about": "student: " + ", ".join(what for _, what in taking)}  # fmt: skip


def job_tasks(rng: random.Random, load: Load, tag: str, sender: str, n: int) -> tuple[list[Work], list[Letter]]:
    """Deadlines from a work tracker, and one or two asked for by mail."""
    work, letters = [], []
    for i, (title, base) in enumerate(rng.sample(JOB_TASKS, n)):
        w = Work(title, rng.randint(-12, 16), hours(rng, base, load), at=rng.choice(("17:00", "12:00", "23:59")),
                 via="mail" if i < 2 else "canvas", kind="Assignment", tag=tag)  # fmt: skip
        work.append(w)
        if w.via == "mail" and w.day >= 0:
            letters.append(Letter(sender, f"Can you take on: {title}?", f"Could you get this to me by {{d{w.day}}}?",
                                  finds=(w,), unread=i == 1))  # fmt: skip
    return [w for w in work if w.via == "canvas"], letters


def a_worker(rng: random.Random, load: Load, n: int) -> dict:
    job, company = JOBS[n % len(JOBS)]
    boss = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    standup = rng.choice(("09:15", "09:30", "10:00"))
    meetings = [Meeting("Standup", "MTWRF", standup, later(standup, 15), kind="Meeting", tag="Job"),
                Meeting(f"1:1 with {boss.split()[0]}", rng.choice("MTWRF"), "14:00", "14:30", kind="Meeting",
                        tag="Job"),
                Meeting("Team meeting", rng.choice("MTWR"), "11:00", "12:00", kind="Meeting", tag="Job")]  # fmt: skip
    if rng.random() < 0.4:
        meetings.append(Meeting("Evening class: Spanish", rng.choice("TR"), "18:30", "20:00", calendar="personal",
                                kind="Class", tag="Spanish"))  # fmt: skip
    work, letters = job_tasks(rng, load, "Job", f"{boss} <{boss.split()[0].lower()}@example.com>",
                              count(rng, load, 3, 9))  # fmt: skip
    project = Project("Presentation", f"{company} all-hands talk", hours(rng, 6, load), due=rng.randint(10, 24),
                      made=-6, area="Job")  # fmt: skip
    return {"meetings": meetings, "work": work, "letters": letters, "area": "Job",
            "project": project if rng.random() < 0.4 else None, "sleep": rng.choice((("23:00", "07:00"),
            ("23:30", "07:15"), ("00:00", "08:00"))), "meals": meals(("12:00", "14:00"), ("18:00", "21:00")),
            "calendars": CALENDAR_NAMES["worker"],
            "about": f"{job} at {company}"}  # fmt: skip


def without_clashes(meetings: list[Meeting]) -> tuple[Meeting, ...]:
    """The meetings in order, leaving out any that clash with one kept: one person can't be in two places (a parent
    takes every child)."""
    kept: list[Meeting] = []
    for m in meetings:
        if not any(set(m.days) & set(k.days) and minutes(m.start) < minutes(k.end) and minutes(k.start) < minutes(m.end)
                   for k in kept):  # fmt: skip
            kept.append(m)
    return tuple(kept)


def a_parent(rng: random.Random, load: Load, n: int) -> dict:
    kids = rng.sample(KIDS, rng.randint(1, 3))
    meetings = [
        Meeting("School drop-off", "MTWRF", "08:00", "08:30", calendar="clubs", kind="Event", tag="Kids"),
        Meeting("School pickup", "MTWRF", "15:00", "15:30", calendar="clubs", kind="Event", tag="Kids"),
    ]
    for kid, (activity, days, start, end) in zip(kids, rng.sample(KID_ACTIVITIES, len(kids)), strict=True):
        meetings.append(Meeting(f"{kid}'s {activity.lower()}", days, start, end, calendar="clubs", tag="Kids"))
    if rng.random() < 0.5:
        meetings.append(Meeting("Part-time at the bookshop", "TR", "09:00", "13:00", calendar="work", tag="Job"))
    if rng.random() < 0.4:
        title, days, start, end = rng.choice(CARE)
        meetings.append(Meeting(title, days, start, end, calendar="personal", kind="Appointment", tag="Family"))
    work, letters = [], []
    for title, base, kind in rng.sample(PARENT_TASKS, count(rng, load, 2, 7)):
        work.append(Work(title, rng.randint(-10, 14), hours(rng, base, load), kind=kind, tag="Family"))
    form = Work(f"{kids[0]}'s school trip forms", rng.randint(2, 9), 0.5, via="mail", kind="Errand", tag="Kids")
    letters.append(Letter("Riverside Elementary <office@riverside.example.org>", "Trip forms and payment",
                          f"Please return the forms by {{d{form.day}}}.", finds=(form,)))  # fmt: skip
    breakfast = ("06:45", "07:45")
    return {"meetings": meetings, "work": work, "letters": letters, "area": "Family", "project": None,
            "sleep": rng.choice((("22:30", "06:30"), ("23:00", "06:45"))),
            "meals": meals(("12:00", "14:30"), ("17:30", "19:30"), breakfast=breakfast),
            "calendars": CALENDAR_NAMES["parent"],
            "about": f"parent of {', '.join(kids)}"}  # fmt: skip


def a_shift_worker(rng: random.Random, load: Load, n: int) -> dict:
    job, place, (start, end) = SHIFT_JOBS[n // 2 % len(SHIFT_JOBS)]
    days = "".join(sorted(rng.sample("MTWRFSU", rng.randint(3, 5)), key="MTWRFSU".index))
    meetings = [Meeting(f"{job} shift", days, start, end, calendar="work", tag="Job")]
    late = minutes(end) > 20 * 60
    lunch = ("11:30", "13:30") if late else (later(end, 15), later(end, 135))
    dinner = (later(end, 15), later(end, 75)) if late else ("18:30", "21:00")
    sleep = ("00:30", "08:30") if late else (later(start, -510), later(start, -60))
    work = [Work("Training module", rng.randint(2, 14), hours(rng, 2, load), kind="Assignment", tag="Job")]
    return {"meetings": meetings, "work": work, "letters": [], "area": "Job", "project": None, "sleep": sleep,
            "meals": (Routine("Lunch", lunch), Routine("Dinner", dinner, (30, 45, 60))),
            "calendars": CALENDAR_NAMES["shift"],
            "about": f"{job} at {place}, shifts {days}"}  # fmt: skip


def a_freelancer(rng: random.Random, load: Load, n: int) -> dict:
    trade, *jobs = FREELANCE[n // 2 % len(FREELANCE)]
    clients = rng.sample(CLIENTS, 3)
    meetings = [Meeting(f"Call with {clients[0]}", rng.choice("MTWRF"), "10:00", "10:45", kind="Meeting",
                        tag="Clients")]  # fmt: skip
    work, letters = [], []
    for i, (title, base) in enumerate((*jobs, *jobs)[: count(rng, load, 2, 6)]):
        client = clients[i % 3]
        w = Work(f"{title} ({client})", rng.randint(-8, 18), hours(rng, base, load), via="mail", tag="Clients")
        work.append(w)
        letters.append(Letter(f"{client} <hi@{client.split()[0].lower()}.example.com>", f"{title}: timing for {client}",
                              f"Could we have it by {{d{w.day}}}?", finds=(w,), unread=i == 2))  # fmt: skip
    return {"meetings": meetings, "work": [], "letters": [x for x in letters if x.finds[0].day >= 0],
            "area": "Clients", "project": None, "sleep": rng.choice((("00:30", "08:30"), ("01:00", "09:00"))),
            "meals": meals(("12:30", "15:00"), ("18:30", "21:30")), "calendars": CALENDAR_NAMES["freelance"],
            "about": f"freelance {trade.lower()}"}  # fmt: skip


def person(key: str, name: str, kind: Kind, load: Load, freelance: bool = False, n: int = 0) -> Student:
    """The person `key` names, the same every time."""
    rng = random.Random(zlib.crc32(key.encode()))
    maker = {"student": a_student, "worker": a_worker, "parent": a_parent}.get(kind)
    life = maker(rng, load, n) if maker else (a_freelancer if freelance else a_shift_worker)(rng, load, n)
    first, last = name.split()
    return Student(
        key=key,
        name=first,
        about=f"{life['about'][0].upper()}{life['about'][1:]} ({load})",
        load=load,
        meetings=without_clashes(life["meetings"]),
        prelims=tuple(life.get("prelims", ())),
        work=tuple(life["work"]),
        events=appointments(rng, count(rng, load, 1, 4)),
        letters=(*life["letters"], *rng.sample(NEWSLETTERS, 2)),
        typed=typed(rng, kind, rng.randint(2, 4)),
        rules=rules(rng, kind),
        routines=life["meals"],
        project=life["project"],
        sleep=life["sleep"],
        email=f"{first.lower()}.{last.lower()}@example.com",
        calendars=life["calendars"],
        notes=(f"A {kind}'s {load} weeks: nothing planned in their meetings, shifts or sleep.",),
    )


def roster() -> tuple[tuple[str, str, Kind, Load, bool, int], ...]:
    """Each person's key, full name, kind, load, whether a shift worker freelances and their place among their
    kind, in a fixed order."""
    names = [n for n in FIRST if n.lower() not in TAKEN]
    out, n = [], 0
    for kind, many in HOW_MANY.items():
        for i in range(many):
            first, last = names[n], LAST[(n * 7) % len(LAST)]
            out.append(
                (first.lower(), f"{first} {last}", kind, LOADS[(i + n) % len(LOADS)], kind == "shift" and i % 2 == 1, i)
            )
            n += 1
    return tuple(out)


PEOPLE = {key: person(key, name, kind, load, freelance, i) for key, name, kind, load, freelance, i in roster()}
KINDS: dict[str, Kind] = {key: kind for key, _, kind, *_ in roster()}
