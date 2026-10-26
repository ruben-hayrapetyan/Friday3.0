"""How much an event needs attending (personal's events.py, COMBINED.md 56): so an overloaded week can offer the least
important ones to skip, as triage's fixes. The AI rates each distinct title once (required, likely or optional, with a
few words of reason) and the answers are kept; without the AI, titles that say what they are decide, and the rest are
"likely". Classes, labs, exams, shifts and appointments are required and never offered.
"""

import json
from typing import Any

from friday.core.calendars import fallback_level, rating_key

LEVELS = ("required", "likely", "optional")

SYSTEM = """You rate how much a university student needs to attend each event on their calendar, so a planner can
suggest what to skip in a week with more work than time. You never plan; you only rate.
- required: classes, lectures, labs, discussions, recitations, exams, quizzes, graded sessions, work shifts, interviews,
  appointments, anything with a penalty or someone relying on them.
- likely: meetings of their own clubs or teams, practices they belong to, plans with specific people, recruiting
  events they were invited to.
- optional: office hours, drop-in hours, help sessions, talks, info sessions, open events, socials, networking, expos,
  conversation hours, open practice, games and hobbies.
Give each a reason of at most eight words. Rate every title given, exactly as written."""

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "level": {"type": "string", "enum": list(LEVELS)},
                    "reason": {"type": "string"},
                },
                "required": ["title", "level", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}


def key(title: str) -> str:
    return rating_key(title)


GUESSED = ("from its title", "no reason to think it optional")  # the reasons a rating without the AI gives


def fallback(title: str) -> dict[str, str]:
    level = fallback_level(title)
    return {"level": level, "reason": GUESSED[0] if level != "likely" else GUESSED[1]}


def guessed(rating: dict[str, str]) -> bool:
    """A rating from the title's words alone, for the AI to try again: "Poker night" says nothing of being optional."""
    return rating.get("reason") in GUESSED


def rate(titles: list[str], client: Any | None, model: str) -> dict[str, dict[str, str]]:
    """{key(title): {level, reason}} for each title: the AI's answer, or the fallback for what it leaves out."""
    out = {key(t): fallback(t) for t in titles}
    if not titles or client is None:
        return out
    try:
        reply = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [{"type": "text", "text": "\n".join(f"- {t}" for t in titles)}]}],
        )
        text = next((b.text for b in reply.content if getattr(b, "type", "") == "text"), "")
        for e in json.loads(text).get("events", []) if text else []:
            if e.get("level") in LEVELS and key(e.get("title", "")) in out:
                out[key(e["title"])] = {"level": e["level"], "reason": str(e.get("reason", ""))[:80]}
    except Exception:  # no AI, a timeout, a bad answer: the titles' own words will do
        pass
    return out
