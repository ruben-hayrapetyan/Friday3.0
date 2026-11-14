"""How much an event needs attending (personal's events.py, COMBINED.md 56): so an overloaded week can offer the least
important ones to skip, as triage's fixes. The AI rates each distinct title once (required, likely or optional, with a
few words of reason) and the answers are kept; without the AI, titles that say what they are decide, and the rest are
"likely". Classes, labs, exams, shifts and appointments are required and never offered. Given your categories, it also
names the one each event fits (26 Oct: an event no category's words found, "Dinner with Sam", wore no color).
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


BATCH = 40  # titles a call


def rate(
    titles: list[str],
    client: Any | None,
    model: str,
    categories: list[str] | None = None,
    told: dict[str, str] | None = None,
    examples: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """{key(title): {level, reason, category?}} for each title: the AI's answer, or the fallback for what it leaves
    out. With `categories`, each answer names the one it fits, or none (""): weighing what Friday knows of a title
    (`told`: its calendar, place, sender, the event it's most like) and what each category has meant for you
    (`examples`), as clues rather than rules (31 Oct)."""
    told = told or {}
    out = {key(t): fallback(t) for t in titles}
    if not titles or client is None:
        return out
    named = list(categories or [])
    system, schema = SYSTEM, SCHEMA
    if named:
        system += (
            '\nAlso give each event the category from this list it fits best, exactly as written, or "" when none '
            "fits: " + "; ".join(named)
        )
        if examples:
            system += "\nWhat each category has meant for this student: " + "; ".join(
                f"{c}: {', '.join(titles_)}" for c, titles_ in examples.items() if c in named
            )
        if told:
            system += (
                "\nUnder some titles, indented, is what the planner knows of the event: its calendar, its place, who "
                "sent it, the event it is most like. Weigh it as a clue; the title comes first. Answer with the "
                "title alone, as written on its first line."
            )
        item = schema["properties"]["events"]["items"]
        item = item | {"properties": item["properties"] | {"category": {"type": "string"}},
                       "required": [*item["required"], "category"]}  # fmt: skip
        schema = {**schema, "properties": {"events": {**schema["properties"]["events"], "items": item}}}

    def line(title: str) -> str:
        return f"- {title}" + (f"\n    {told[title]}" if title in told else "")

    for start in range(0, len(titles), BATCH):
        part = titles[start : start + BATCH]
        try:
            reply = client.messages.create(
                model=model,
                max_tokens=4000,
                system=system,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": [{"type": "text", "text": "\n".join(map(line, part))}]}],
            )
            text = next((b.text for b in reply.content if getattr(b, "type", "") == "text"), "")
            for e in json.loads(text).get("events", []) if text else []:
                said = str(e.get("title", "")).split("\n")[0].strip()
                if e.get("level") in LEVELS and key(said) in out:
                    found = {"level": e["level"], "reason": str(e.get("reason", ""))[:80]}
                    if named:
                        found["category"] = e.get("category") if e.get("category") in named else ""
                    out[key(said)] = found
        except Exception:  # no AI, a timeout, a bad answer: the titles' own words will do
            continue
    return out
