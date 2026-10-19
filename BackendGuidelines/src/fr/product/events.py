"""How much a calendar event needs attending, so an overloaded week can offer the least important ones to skip.

Claude rates each distinct title once (required / likely / optional, with a few words of reason), through the same
`claude` CLI as the constraint parser; ratings are cached in the engine state and the user's own answers override
them ("I go to these" makes a title required for good). The engine never removes an event: a skipped occurrence only
stops blocking time in Friday's plans.
"""
from __future__ import annotations

import re

from .parse import call_claude

LEVELS = ("required", "likely", "optional")

SYSTEM = """You rate how much a university student needs to attend each event on their calendar, so a planner can
suggest what to skip in a week with more work than time. You never plan; you only rate.
- required: classes, lectures, labs, discussions, recitations, exams, quizzes, graded sessions, work shifts, interviews,
  appointments, anything with a penalty or someone relying on them.
- likely: meetings of their own clubs or teams, practices they belong to, plans with specific people, recruiting
  events they were invited to.
- optional: office hours, drop-in hours, help sessions, talks, info sessions, open events, socials, networking, expos,
  conversation hours, open practice.
Give each a reason of at most eight words. Rate every title given, exactly as written."""

SCHEMA = {
    "type": "object",
    "properties": {"events": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "level": {"type": "string", "enum": list(LEVELS)},
                       "reason": {"type": "string"}},
        "required": ["title", "level", "reason"], "additionalProperties": False}}},
    "required": ["events"], "additionalProperties": False,
}

# Without Claude: titles that say what they are
_FALLBACK = [
    ("required", re.compile(r"\b(lec(ture)?|lab|disc(ussion)?|recitation|section|seminar|exam|prelim|midterm|quiz|"
                            r"final|interview|appointment|shift)\b", re.I)),
    ("optional", re.compile(r"\b(office hours|drop.?in|help session|talk|info session|social|networking|expo|open|"
                            r"conversation hours|zoom)\b", re.I)),
]


def key(title: str) -> str:
    """One rating per series: case, spacing and trailing numbers don't make a new event."""
    return re.sub(r"\s+", " ", re.sub(r"\s*#?\d+\s*$", "", title.strip().lower()))


def fallback(title: str) -> dict:
    for level, rx in _FALLBACK:
        if rx.search(title):
            return dict(level=level, reason="from its title")
    return dict(level="likely", reason="no reason to think it optional")


def rate(titles: list[str], caller=call_claude) -> dict[str, dict]:
    """{key(title): {level, reason}} for each title, from Claude; titles it leaves out or garbles get the fallback."""
    out = {key(t): fallback(t) for t in titles}
    if not titles:
        return out
    try:
        r = caller(SYSTEM, "Rate these events:\n" + "\n".join(f"- {t}" for t in titles), SCHEMA)
        for e in (r.get("structured") or {}).get("events", []):
            if e.get("level") in LEVELS and key(e.get("title", "")) in out:
                out[key(e["title"])] = dict(level=e["level"], reason=str(e.get("reason", ""))[:80])
    except Exception:  # no CLI, a timeout, a bad reply: the titles' own words will do
        pass
    return out
