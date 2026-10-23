"""Rules from sentences (v22 Rules, M11): a fixed grammar, no LLM, from what you type to a Reading (what, when,
which days), and from a Reading and a strength to one of the planner's rule types. It reads:

- `lunch before 1pm`, `no work after 10pm on weekdays`, `deep work in the morning`, `gym between 5 and 7pm`:
  `time_preference` (Always forbids the other hours);
- `no work on sundays`, `reading only on weekends`: `time_preference` by day;
- `keep saturday mornings free`, `keep evenings free`: `reserve` (Always forbids the window);
- `at most 6 hours a day`, `no more than 2h of reading a day`: `daily_load`;
- `finish things a day early`, `finish essays 2 days before they're due`: `finish_early`;
- `gym right after class`: `after_event`.
"""

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from friday.core.time import ampm_in

Strength = Literal["Prefer", "Strongly", "Always"]
Kind = Literal["window", "days", "free", "cap", "early", "after"]
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NAMES = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}
PARTS = {
    "morning": ("08:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "22:00"),
    "night": ("22:00", "02:00"),
}
EVERYTHING = {"work", "anything", "things", "tasks", "stuff", "it"}
DEEP = {"deep work", "focused work", "hard work", "focus work"}
TIME = r"(noon|midnight|\d{1,2}(?::\d\d)?\s*(?:am|pm)?)"
DAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?"
DAY_WORDS = rf"((?:{DAY}|weekdays?|weekends?|every day)(?:\s*(?:,|and|&)\s*{DAY})*)"


@dataclass(frozen=True)
class Reading:
    kind: Kind
    subject: str = "work"  # "work" is everything; else deep work, an area, a preset or a title
    rel: Literal["before", "after", "between", "on", "not_on"] | None = None
    at: str | None = None  # HH:MM
    until: str | None = None  # HH:MM, for between
    days: tuple[str, ...] | None = None  # None is every day
    amount: float | None = None  # hours a day for cap, days for early
    event: str | None = None  # after

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clock(text: str) -> str | None:
    t = text.strip().lower().replace(" ", "")
    if t == "noon":
        return "12:00"
    if t == "midnight":
        return "00:00"
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?(am|pm)?", t)
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2] or 0)
    if m[3] == "pm" and hour < 12:
        hour += 12
    if m[3] == "am" and hour == 12:
        hour = 0
    if not m[3] and hour < 7:  # "between 5 and 7" means the evening, as people say it
        hour += 12
    return f"{hour % 24:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def days_of(text: str) -> tuple[str, ...] | None:
    t = text.lower()
    if "every day" in t:
        return None
    out: list[str] = []
    if "weekday" in t:
        out += DAYS[:5]
    if "weekend" in t:
        out += DAYS[5:]
    for word in re.findall(r"[a-z]+", t):
        for name, short in NAMES.items():
            if word.rstrip("s") in (name, short, name[:3], name[:4]) or word == name + "s":
                out.append(short)
    found = tuple(d for d in DAYS if d in out)
    return found or None


def read(text: str) -> tuple[Reading | None, Strength]:
    """What a sentence asks for, and how strongly; None when the grammar can't read it."""
    t = " " + re.sub(r"\s+", " ", text.lower().strip().rstrip(".!")) + " "
    strength: Strength = "Prefer"
    if re.search(r"\b(always|never|must|absolutely)\b", t):
        strength = "Always"
    elif re.search(r"\b(really|strongly|definitely)\b", t):
        strength = "Strongly"
    t = re.sub(
        r"\b(i(?:'d| would)? (?:really )?(?:prefer|like|want)(?: to)?|please|ideally|always|really|strongly"
        r"|definitely|try to|i)\b",
        " ",
        t,
    )
    t = re.sub(r"\s+", " ", t)
    negated = bool(re.search(r"\b(no|never|don't|not|avoid)\b", t))
    t = re.sub(r"\b(no|never|don't do|don't|do not|not|avoid)\b", " ", t)
    for parse in (read_cap, read_early, read_free, read_window, read_days, read_after):
        found = parse(" " + " ".join(t.split()) + " ", negated)
        if found:
            return found, strength
    return None, strength


def subject_of(words: str) -> str:
    s = re.sub(r"\b(eating|having|doing|do|my|the|a|an|any|of|to)\b", " ", words).strip()
    s = " ".join(s.split())
    if not s or s in EVERYTHING:
        return "work"
    return "deep work" if s in DEEP else s


def read_cap(t: str, negated: bool) -> Reading | None:
    m = re.search(
        r"(?:at most|no more than|more than|max(?:imum)?|up to) (\d+(?:\.\d+)?) ?(?:h|hrs?|hours?)"
        r"(?: of ([a-z ]+?))? (?:a|per|each) day",
        t,
    )
    if not m:
        return None
    return Reading("cap", subject_of(m[2] or "work"), amount=float(m[1]))


def read_early(t: str, negated: bool) -> Reading | None:
    m = re.search(r"finish(?: ([a-z ]+?))? (a|one|two|three|\d+) days? (?:early|before|ahead)", t)
    if not m:
        return None
    n = {"a": 1, "one": 1, "two": 2, "three": 3}.get(m[2]) or int(m[2])
    return Reading("early", subject_of(m[1] or "work"), amount=float(n))


def read_free(t: str, negated: bool) -> Reading | None:
    m = re.search(
        rf"keep (?:my )?{DAY_WORDS}? ?(mornings?|afternoons?|evenings?|nights?)? ?"
        rf"(?:from {TIME} (?:to|until|-) {TIME} )?(?:free|clear|open)",
        t,
    )
    if not m or not (m[1] or m[2] or m[3]):
        return None
    part = (m[2] or "").rstrip("s")
    start, end = PARTS.get(part, (clock(m[3]) if m[3] else None, clock(m[4]) if m[4] else None))
    return Reading("free", "work", rel="between" if start else None, at=start, until=end, days=days_of(m[1] or ""))


def read_window(t: str, negated: bool) -> Reading | None:
    on = re.search(rf" on {DAY_WORDS} ", t)
    days = days_of(on[1]) if on else None
    if on:
        t = t.replace(on[0], " ")
    if m := re.search(r"^ ?([a-z ]*?) ?(?:in the|during the) (morning|afternoon|evening|night)s? ", t):
        start, end = PARTS[m[2]]
        return Reading("window", subject_of(m[1]), rel="between", at=start, until=end, days=days)
    if m := re.search(rf"^ ?([a-z ]*?) ?(?:between|from) {TIME} (?:and|to|until|-) {TIME} ", t):
        start, end = clock(m[2]), clock(m[3])
        if start and end and end <= start and not re.search(r"(am|pm)", m[3]) and int(end[:2]) < 12:
            end = f"{int(end[:2]) + 12:02d}{end[2:]}"
        return (
            Reading("window", subject_of(m[1]), rel="between", at=start, until=end, days=days)
            if start and end
            else None
        )
    if m := re.search(rf"^ ?([a-z ]*?) ?(before|after|by|until|past) {TIME} ", t):
        at = clock(m[3])
        rel = "before" if m[2] in ("before", "by", "until") else "after"
        if negated:
            rel = "after" if rel == "before" else "before"
        return Reading("window", subject_of(m[1]), rel=rel, at=at, days=days) if at else None
    return None


def read_days(t: str, negated: bool) -> Reading | None:
    m = re.search(rf"^ ?([a-z ]*?) ?(only )?on {DAY_WORDS} ", t) or re.search(rf"^ ?(rest|off) {DAY_WORDS} ", t)
    if not m:
        return None
    if m[1] in ("rest", "off"):
        return Reading("days", "work", rel="not_on", days=days_of(m[2]))
    rel = "not_on" if negated else "on"
    return Reading("days", subject_of(m[1]), rel=rel, days=days_of(m[3]))


def read_after(t: str, negated: bool) -> Reading | None:
    m = re.search(r"^ ?([a-z ]+?) (?:right |straight |just )?after (?:my |the )?([a-z ]+?) ", t)
    if not m or clock(m[2]) or negated:
        return None
    return Reading("after", subject_of(m[1]), event=m[2].strip())


def with_overrides(r: Reading, overrides: dict[str, Any]) -> Reading:
    known = {
        k: (tuple(v) if k == "days" and v is not None else v)
        for k, v in overrides.items()
        if k in Reading.__dataclass_fields__
    }
    return replace(r, **known)


DAY_LABEL = {("mon", "tue", "wed", "thu", "fri"): "on weekdays", ("sat", "sun"): "on weekends"}


def days_words(days: tuple[str, ...] | None) -> str:
    if not days:
        return ""
    return DAY_LABEL.get(days) or "on " + ", ".join(d.capitalize() for d in days)


def sentence(r: Reading) -> str:
    """The rule in plain words, as the Rules list shows it, on a 12-hour clock."""
    return ampm_in(said(r))


def said(r: Reading) -> str:
    subject = "Work" if r.subject == "work" else r.subject[0].upper() + r.subject[1:]
    on = (" " + days_words(r.days)) if r.days else ""
    if r.kind == "window":
        if r.rel == "between":
            return f"{subject} between {r.at} and {r.until}{on}"
        if r.subject == "work":  # "no work after 22:00" says it the way people do
            return f"No work {'after' if r.rel == 'before' else 'before'} {r.at}{on}"
        return f"{subject} {r.rel} {r.at}{on}"
    if r.kind == "days":
        return f"No {r.subject} {days_words(r.days)}" if r.rel == "not_on" else f"{subject} only {days_words(r.days)}"
    if r.kind == "free":
        when = f" {r.at}–{r.until}" if r.at else ""
        return f"Keep {days_words(r.days).removeprefix('on ') or 'every day'}{when} free"
    if r.kind == "cap":
        of = "" if r.subject == "work" else f" of {r.subject}"
        return f"At most {r.amount:g} h{of} a day"
    if r.kind == "early":
        n = int(r.amount or 1)
        return (
            f"Finish {'things' if r.subject == 'work' else r.subject} {n} day{'s' if n > 1 else ''} before they're due"
        )
    return f"{subject} right after {r.event}"


def scope_of(subject: str, areas: list[str], presets: list[str]) -> dict[str, Any] | None:
    if subject == "work":
        return None
    if subject == "deep work":
        return {"energy": "deep"}
    for a in areas:
        if a.lower() == subject:
            return {"area": a}
    for p in presets:
        if p.lower() in (subject, subject.rstrip("s")):
            return {"preset": p}
    return {"title": subject}


PRICE = {"Prefer": 2.0, "Strongly": 6.0}
WEIGHT = {"Prefer": 1.0, "Strongly": 3.0, "Always": 10.0}


def spec(r: Reading, strength: Strength, name: str, areas: list[str], presets: list[str]) -> dict[str, Any]:
    """The planner rule for a reading: {type, name, weight, scope, reason, params}."""
    scope = scope_of(r.subject, areas, presets)
    price: Any = "forbid" if strength == "Always" else PRICE[strength]
    base = {"name": name, "scope": scope, "reason": sentence(r)}
    if r.kind == "window":
        # The hours to avoid: after `at` (for before), before it (for after), outside [at, until) (for between).
        start, end = {"before": (r.at, "04:00"), "after": ("04:00", r.at), "between": (r.until, r.at)}[
            r.rel or "before"
        ]
        params = {"start": start, "end": end, "price": price} | ({"days": list(r.days)} if r.days else {})
        return base | {"type": "time_preference", "weight": 1.0, "params": params}
    if r.kind == "days":
        key = "days" if r.rel == "not_on" else "days_except"
        return base | {"type": "time_preference", "weight": 1.0, "params": {key: list(r.days or ()), "price": price}}
    if r.kind == "free":
        window = {"start": r.at, "end": r.until} if r.at else {}
        days = {"days": list(r.days)} if r.days else {}
        if strength == "Always":
            return base | {
                "type": "time_preference",
                "weight": 1.0,
                "scope": None,
                "params": window | days | {"price": "forbid"},
            }
        hours = hours_between(r.at, r.until) if r.at and r.until else 24
        return base | {
            "type": "reserve",
            "weight": WEIGHT[strength] * 2,
            "scope": None,
            "params": window | days | {"free": f"{hours:g}h"},
        }
    if r.kind == "cap":
        return base | {"type": "daily_load", "weight": WEIGHT[strength] * 5, "params": {"threshold": f"{r.amount:g}h"}}
    if r.kind == "early":
        return base | {"type": "finish_early", "weight": WEIGHT[strength], "params": {"days": int(r.amount or 1)}}
    events = {"event_kind": "class"} if (r.event or "").rstrip("s") in ("class", "lecture") else {"title": r.event}
    params = {"events": events, "measure_from": "last", "slope": 1, "cap": 3}
    return base | {"type": "after_event", "weight": WEIGHT[strength], "params": params}


def hours_between(start: str, end: str) -> float:
    a = int(start[:2]) * 60 + int(start[3:])
    b = int(end[:2]) * 60 + int(end[3:])
    return ((b - a) % 1440) / 60
