"""Cornell students to try Friday on (M15): each one's term as Google, Gmail and the AI would give it, from a light
senior fall to a prelim week nobody could finish, and the steps the student takes to set Friday up
(sim/first_evening.py). Used by tests/scenarios/test_cornell.py, `fridayd demo --case NAME` and
`python -m friday.sim.agenda NAME`.

A student is data (sim/students.py): weekly meetings in Cornell's day letters, prelims, work with the hours it
really takes and where it arrives from (Canvas, a homework calendar, mail or typed into quick-add), one-off events,
mail, routines (meals in their windows), rules in their own words and a project. Everything is made up and dated
from the Monday of the week given, so it is always current.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from friday.sim.fakes import FakeGmail, FakeGoogle, ScriptedClient, mail
from friday.sim.sample import ZONE, Sample, all_day, timed

LETTERS = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}
RRULE_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WEEKS = range(-4, 5)  # four weeks back (for the weeks lived before today, sim/history.py) to four ahead
CALENDARS = {
    "primary": "{netid}@cornell.edu",
    "classes": "Cornell Classes",
    "canvas": "Canvas",
    "homework": "Homework",
    "personal": "Personal",
    "clubs": "Clubs",
    "work": "Work",
}
Via = Literal["canvas", "homework", "mail", "typed"]


@dataclass(frozen=True)
class Meeting:
    """A weekly meeting on one of the student's calendars: a lecture, a lab, a shift, practice."""

    title: str  # as the calendar has it
    days: str  # Cornell's letters: "MWF", "TR"
    start: str
    end: str
    calendar: str = "classes"
    kind: str = "Class"  # how the small model sorts it
    plain: str | None = None  # the title it gives; the calendar's when None
    tag: str | None = None  # the tag the student gives it on import
    until: int | None = None  # the last day it meets, counted from this week's Monday


@dataclass(frozen=True)
class Prelim:
    """An evening prelim (or a final) on the class calendar; Friday adds its prep."""

    title: str
    day: int  # days after this week's Monday
    start: str = "19:30"
    end: str = "21:00"
    prep_hours: float = 4
    where: str = ""


@dataclass(frozen=True)
class Work:
    """Something due, with the hours it really takes."""

    title: str  # as Friday should show it
    day: int
    hours: float
    via: Via = "canvas"
    at: str = "23:59"
    kind: str = "Assignment"
    tag: str | None = None
    raw: str | None = None  # the calendar's own words, when they differ from the title


@dataclass(frozen=True)
class Event:
    """A one-off: an appointment, an info session, a birthday."""

    title: str
    day: int
    start: str | None = None  # None: all day
    end: str | None = None
    calendar: str = "personal"
    kind: str = "Event"
    was: tuple[str, str] | None = None  # its start and end before it moved: what Google said weeks ago


@dataclass(frozen=True)
class Routine:
    """Something repeating the student adds themselves: a meal in a window of the day with a length that gives,
    or a habit or chore of a set length (`every` as series_add takes it)."""

    title: str
    window: tuple[str, str] | None = None  # from, by (local); None: any time of its day or week
    minutes: tuple[int, int, int] | int = (30, 45, 45)  # least, ideal, most; one number for a set length
    preset: str = "Routine"
    every: str = "day"


def meals(
    lunch: tuple[str, str], dinner: tuple[str, str], breakfast: tuple[str, str] | None = None
) -> tuple[Routine, ...]:
    """Lunch and dinner (and breakfast) every day, each in its window: 30–45 minutes, dinner up to an hour."""
    out = (Routine("Lunch", lunch), Routine("Dinner", dinner, (30, 45, 60)))
    return out + ((Routine("Breakfast", breakfast, (15, 15, 30)),) if breakfast else ())


@dataclass(frozen=True)
class Project:
    """A project the student made from a template on day `made` (counted like `due`), and what one step waits on."""

    template: str
    title: str
    hours: float
    due: int
    made: int
    area: str | None = None
    waits_on: tuple[str, str] | None = None  # (step, the item it waits on)


@dataclass(frozen=True)
class Letter:
    """An email. `{dN}` in the body is the date N days after this week's Monday ("Thursday, Oct 22"); `finds` is
    what the AI reads in it, each due on its day, quoting that date."""

    sender: str
    subject: str
    body: str
    bulk: bool = False
    finds: tuple[Work, ...] = ()
    thread: str | None = None
    unread: bool = False  # in the inbox, not yet answered


@dataclass(frozen=True)
class Student:
    key: str
    name: str
    about: str  # one line: year, major, the shape of the term
    load: Literal["very light", "light", "moderate", "heavy", "very heavy", "overloaded"]
    meetings: tuple[Meeting, ...]
    prelims: tuple[Prelim, ...] = ()
    work: tuple[Work, ...] = ()
    events: tuple[Event, ...] = ()
    letters: tuple[Letter, ...] = ()
    typed: tuple[str, ...] = ()  # quick-add lines, `{dN}` as in Letter but as "oct 22"
    rules: tuple[str, ...] = ()  # sentences for the Rules page, in the student's words
    routines: tuple[Routine, ...] = ()
    project: Project | None = None
    sleep: tuple[str, str] = ("00:00", "08:00")  # weekday bedtime and wake; weekends an hour later
    netid: str = "abc123"
    notes: tuple[str, ...] = field(default_factory=tuple)  # what a plan for this student should look like
    email: str = ""  # their Google address; a Cornell student's is their netid's
    calendars: dict[str, str] = field(default_factory=dict)  # names in place of CALENDARS' (sim/people.py)


# Helpers for writing students (sim/students.py).


def each_week(
    title: str, day: int, hours: float, weeks: range = range(-3, 4), first: int = 1, raw: str | None = None, **kw: Any
) -> tuple[Work, ...]:
    """The same work each week: `{n}` in the title (and the calendar's words) is `first` this week, counting back
    for the three weeks before (done before today, sim/history.py)."""
    return tuple(
        Work(title.format(n=first + w), day + 7 * w, hours, raw=raw and raw.format(n=first + w), **kw) for w in weeks
    )


def lecture(code: str, section: str, days: str, start: str, end: str, plain: str = "Lecture") -> Meeting:
    """A meeting as Cornell's class calendar names it ("CS 2110 - LEC 001"), sorted to "CS 2110 Lecture"."""
    return Meeting(f"{code} - {section}", days, start, end, plain=f"{code} {plain}", tag=code)


SUBJECTS = {"LEC": "Lecture", "DIS": "Discussion", "LAB": "Lab", "SEM": "Seminar"}


def course(code: str, *parts: tuple[str, str, str, str]) -> tuple[Meeting, ...]:
    """A course's meetings: (section like "LEC 001", days, start, end) each."""
    return tuple(lecture(code, sec, days, a, b, SUBJECTS[sec.split()[0]]) for sec, days, a, b in parts)


BULK = (
    Letter("Cornell Dining <dining@cornell.edu>", "This week at Okenshields: Taco Tuesday is back",
           "Menus for the week. Brunch hours change Saturday.", bulk=True),
    Letter("Cornell Store <store@cornell.edu>", "Last day for 20% off Big Red gear!",
           "Sale ends tonight. Don't miss the deadline to save.", bulk=True),
    Letter("Bursar <bursar@cornell.edu>", "Your eBill has not been viewed",
           "Your November bill is ready. Payment is due by the 15th.", bulk=True),
    Letter("Cornell Chronicle <chronicle@cornell.edu>", "Cornell Chronicle: Today's news",
           "Researchers find… Read more stories.", bulk=True),
)  # fmt: skip


def monday_of(today: date) -> date:
    return today - timedelta(days=today.weekday())


def spoken(on: date) -> str:
    return f"{on:%A, %b} {on.day}"


def typed_date(on: date) -> str:
    return f"{on:%b}".lower() + f" {on.day}"


def dated(text: str, monday: date, form: Callable[[date], str] = spoken) -> str:
    """`{dN}` → the date N days after `monday` (N may be negative)."""
    out = text
    for n in range(-7, 7 * len(WEEKS)):
        out = out.replace(f"{{d{n}}}", form(monday + timedelta(days=n)))
    return out


def address(student: Student) -> str:
    """The Google account the stand-ins answer for."""
    return student.email or f"{student.netid}@cornell.edu"


def calendar_ids(student: Student) -> dict[str, str]:
    """Each calendar's id (its key, `@g`) and name; the primary one is the student's address."""
    names = CALENDARS | student.calendars | {"primary": address(student)}
    return {f"{key}@g": name for key, name in names.items()}


def term(student: Student, today: date, early: bool = False) -> Sample:
    """The student's Google, Gmail and AI, dated from the Monday of `today`'s week. `early`: as they were weeks
    before, when the student started (sim/history.py): classes, events (moved ones where they were), and the
    work and prelims of the weeks before this one; no mail yet."""
    monday = monday_of(today)
    if early:
        past = tuple(w for w in student.work if w.day < 0)
        then = tuple(replace(e, start=e.was[0], end=e.was[1]) if e.was else e for e in student.events)
        prelims = tuple(p for p in student.prelims if p.day < 0)
        student = replace(student, prelims=prelims, letters=(), work=past, events=then)
    names = calendar_ids(student)
    google = FakeGoogle({cid: [] for cid in names}, primary="primary@g", names=names)
    events = google.calendars_by_id
    for n, m in enumerate(student.meetings):
        key = f"m{n}"
        events[f"{m.calendar}@g"] += weekly(monday, key, m)
        google.rules[key] = "FREQ=WEEKLY;BYDAY=" + ",".join(RRULE_DAYS[LETTERS[d]] for d in m.days) + until(m, monday)
    for p in student.prelims:
        prelim = timed(f"p:{p.title}", p.title, monday + timedelta(days=p.day), p.start, p.end)
        events["classes@g"].append(prelim | ({"location": p.where} if p.where else {}))
    for w in student.work:  # ids by title, so an early read and a later one agree
        if w.via in ("canvas", "homework"):
            events[f"{w.via}@g"].append(due_event(f"w:{w.title}", w, monday))
    for e in student.events:
        on, eid = monday + timedelta(days=e.day), f"e:{e.title}"
        made = all_day(eid, e.title, on) if e.start is None else timed(eid, e.title, on, e.start, e.end or "")
        events[f"{e.calendar}@g"].append(made)
    gmail, answers = mailbox(student, monday)
    return Sample(google, gmail, ScriptedClient(answers, sorts(student)), monday)


def until(m: Meeting, monday: date) -> str:
    if m.until is None:
        return ""
    last = datetime.combine(monday + timedelta(days=m.until), time(23, 59), ZONE).astimezone(UTC)
    return f";UNTIL={last:%Y%m%dT%H%M%SZ}"


def weekly(monday: date, key: str, m: Meeting) -> list[dict[str, Any]]:
    """The meeting's instances, as Google gives them with `singleEvents`."""
    out = []
    for week in WEEKS:
        for letter in m.days:
            n = 7 * week + LETTERS[letter]
            if m.until is None or n <= m.until:
                on = monday + timedelta(days=n)
                out.append(timed(f"{key}_{on:%Y%m%d}", m.title, on, m.start, m.end) | {"recurringEventId": key})
    return out


def due_event(eid: str, w: Work, monday: date) -> dict[str, Any]:
    """Canvas puts work at its due time with no length; a homework calendar has it all day."""
    on = monday + timedelta(days=w.day)
    if w.via == "canvas":
        return timed(eid, w.raw or w.title, on, w.at, w.at)
    return all_day(eid, w.raw or f"{w.title} due", on)


def sorts(student: Student) -> dict[str, tuple[str, str]]:
    """How the small model sorts each calendar entry: its kind and a plain title."""
    found = {m.title: (m.kind, m.plain or m.title) for m in student.meetings}
    found |= {p.title: ("Exam", p.title) for p in student.prelims}
    found |= {w.raw or w.title: (w.kind, w.title) for w in student.work if w.via == "canvas"}
    return found | {e.title: (e.kind, e.title) for e in student.events}


def mailbox(student: Student, monday: date) -> tuple[FakeGmail, dict[str, dict[str, Any]]]:
    """The mail, newest first, and the AI's answer for each letter that has one (keyed by its subject)."""
    messages, answers = [], {}
    for n, letter in enumerate(reversed(student.letters)):
        body = dated(letter.body, monday)
        mid = f"mail{len(student.letters) - n}"
        messages.append(mail(mid, letter.sender, letter.subject, f"<p>{body}</p>", bulk=letter.bulk,
                             thread=letter.thread))  # fmt: skip
        if letter.finds:
            answers[letter.subject] = {"is_syllabus": False, "items": [found(w, monday) for w in letter.finds]}
    return FakeGmail(messages), answers


def found(w: Work, monday: date) -> dict[str, Any]:
    on = monday + timedelta(days=w.day)
    return {"title": w.title, "preset": w.kind, "due": f"{on}T{w.at}", "confidence": 0.9,
            "quotes": {"title": w.title, "due": spoken(on)}}  # fmt: skip
