"""LLM extraction (DESIGN §22.5–22.7): one call per input with structured output (a JSON schema), so the model
can only propose `add` inputs, each field with the source text it came from. Nothing here writes or decides;
`commands/inbox.py` stores the proposals as suggestions for you to accept. The client is passed in (the Anthropic
SDK's, or a fake).
"""

import json
import re
from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol

from friday.ingest.ics import Proposed

DATE_FIELDS = ("due", "start", "end", "release")
MAX_TOKENS = 16384  # a syllabus with its readings runs to dozens of items
MIN_PER_PAGE = 3  # a reading's length from its pages, when the source gives pages but no time
UNCHECKED_CONFIDENCE = 0.7  # quotes from a PDF or image can't be checked against text Friday doesn't read


class Client(Protocol):
    messages: Any


# What the built-in kinds mean, so the model can tell them apart; a kind you added is described by its timing.
MEANING = {
    "Assignment": "coursework handed in by a deadline: homework, problem sets, lab reports, essays, a proposal, "
    "an online quiz",
    "Exam": "a test sat at a set time: exam, prelim, midterm, final, an in-class quiz",
    "Class": "a lecture, lab section, discussion, seminar or recitation",
    "Meeting": "a meeting with other people: office hours, a club or team meeting, a one-on-one",
    "Appointment": "a personal appointment: doctor, dentist, advisor, haircut",
    "Event": "anything else at a set time: a talk, a fair, a social, a game",
    "Reading": "reading to finish by a date",
    "Project": "a big piece of work over several weeks (about 10 hours or more): a term project or paper; one "
    "step of it, like a proposal, is an Assignment",
    "Errand": "a small task that isn't coursework: forms and paperwork, a reply or email to send, booking, "
    "something to pick up",
    "Chore": "a small task at home",
}


def maybe(kind: str, description: str = "") -> dict[str, Any]:
    """An optional field: the value, or null."""
    found: dict[str, Any] = {"anyOf": [{"type": kind}, {"type": "null"}]}
    return found | ({"description": description} if description else {})


QUOTE = {
    "type": "object",
    "properties": {"field": {"type": "string"}, "words": {"type": "string"}},
    "required": ["field", "words"],
    "additionalProperties": False,
}
ITEM = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short, as the person would write it: 'PS4', 'Midterm 1'"},
        "preset": {"type": "string", "description": "One of the person's kinds"},
        "area": maybe("string", "One of the person's areas, or a course code"),
        "due": maybe("string", "Local time YYYY-MM-DDTHH:MM"),
        "start": maybe("string", "For something at a set time, YYYY-MM-DDTHH:MM"),
        "end": maybe("string"),
        "duration_min": maybe("integer", "Only when the source says how long"),
        "pages": maybe("integer", "For a reading: how many pages, when the source gives pages or a page range"),
        "every": maybe("string", "A repeat like 'mon,wed until 12-11'"),
        "before": maybe("string", "For exam prep: the exam's title"),
        "quotes": {
            "type": "array",
            "description": "For each field you filled, the exact words of the source it came from",
            "items": QUOTE,
        },
        "confidence": {"type": "number", "description": "0–1: how sure this is a real task or event for them"},
    },
    "required": ["title", "preset", "area", "due", "start", "end", "duration_min", "pages", "every", "before",
                 "quotes", "confidence"],
    "additionalProperties": False,
}  # fmt: skip
PROPOSE = {
    "type": "object",
    "properties": {"is_syllabus": {"type": "boolean"}, "items": {"type": "array", "items": ITEM}},
    "required": ["is_syllabus", "items"],
    "additionalProperties": False,
}
QUICK_ADD = ITEM


def told(notes: Sequence[str]) -> str:
    """What the person told Friday about themselves, for the model to follow; empty when nothing."""
    if not notes:
        return ""
    listed = "\n".join(f"- {n}" for n in notes)
    return (
        "\n\nThe person has told Friday these things about how they work. Follow them whenever they apply: "
        f"leave out what they say needs no time, use the lengths they give, use the names they use.\n{listed}"
    )


def system(today: date, tz: str, areas: Sequence[str], presets: Sequence[str], notes: Sequence[str] = ()) -> str:
    kinds = "; ".join(f"{p} ({MEANING[p]})" if p in MEANING else p for p in presets)
    return (
        f"Today is {today:%A %Y-%m-%d}; the person's timezone is {tz}. Their areas: {', '.join(areas) or 'none'}. "
        f"Their kinds, one per item: {kinds}. Propose only real tasks, deadlines and events for them; newsletters, "
        "receipts and marketing propose nothing. Resolve dates to local YYYY-MM-DDTHH:MM (a due date with no time "
        "is 23:59). Quote the source exactly for every field you fill. A syllabus gives the class meetings as a "
        "repeating Class, each assignment and exam, an 'Exam prep' item before each exam, and each assigned reading "
        "as a Reading: titled by what to read ('Read ch. 4', 'Read Smith 2019'), due at the start of the class it is "
        "for (or by its own date), with its pages when the syllabus gives them. Leave out readings marked optional "
        "or recommended."
    ) + told(notes)


def blocks(content: str, media_type: str) -> list[dict[str, Any]]:
    if media_type == "application/pdf":
        return [{"type": "document", "source": {"type": "base64", "media_type": media_type, "data": content}}]
    if media_type.startswith("image/"):
        return [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": content}}]
    return [{"type": "text", "text": content}]


def call(client: Client, model: str, system_text: str, content: list[dict], schema: dict) -> tuple[dict, int]:
    """The answer, as JSON matching `schema` (structured output), and the tokens spent."""
    reply = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_text,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    used = reply.usage.input_tokens + reply.usage.output_tokens
    text = next((b.text for b in reply.content if getattr(b, "type", "") == "text"), "")
    return (json.loads(text) if text else {}), used


def quotes_of(item: dict[str, Any]) -> dict[str, str]:
    """Quotes by field, from the list the model gives (or a map, as older answers had)."""
    given = item.get("quotes") or []
    pairs = given.items() if isinstance(given, dict) else ((q.get("field"), q.get("words")) for q in given)
    return {str(k): str(v) for k, v in pairs if k and v}


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def item_fields(item: dict[str, Any]) -> dict[str, Any]:
    """An answer's `add` fields: what the model filled, with a reading's pages as its length when no time was given."""
    fields = {
        k: v for k, v in item.items() if k not in ("quotes", "confidence", "before", "pages") and v not in (None, "")
    }
    pages = item.get("pages")
    if isinstance(pages, int) and pages > 0 and not fields.get("duration_min"):
        fields["duration_min"] = max(15, round(pages * MIN_PER_PAGE / 15) * 15)
    return fields


def checked(item: dict[str, Any], source: str | None) -> Proposed | None:
    """The proposal, with date fields whose quote isn't in the source dropped (all kept, less sure, without text)."""
    quotes = quotes_of(item)
    fields = item_fields(item)
    confidence = float(item.get("confidence", 0.5))
    if source is None:
        confidence = min(confidence, UNCHECKED_CONFIDENCE)
    else:
        text = squash(source)
        for name in DATE_FIELDS:
            if name in fields and squash(quotes.get(name, "\0")) not in text:
                fields.pop(name)
                quotes.pop(name, None)
                confidence *= 0.7
    if not fields.get("title"):
        return None
    if "pages" in quotes and "duration_min" in fields and not item.get("duration_min"):
        quotes["duration_min"] = quotes.pop("pages")
    if item.get("before"):
        fields["before_title"] = item["before"]
    return Proposed("add", fields, quotes, round(confidence, 2), fixed=False)


def extract(
    client: Client,
    model: str,
    content: str,
    media_type: str,
    today: date,
    tz: str,
    areas: Sequence[str],
    presets: Sequence[str],
    notes: Sequence[str] = (),
) -> tuple[list[Proposed], bool, int]:
    """Proposals from one input, whether it is a syllabus, and the tokens spent."""
    instructions = system(today, tz, areas, presets, notes)
    found, used = call(client, model, instructions, blocks(content, media_type), PROPOSE)
    source = content if media_type.startswith("text/") else None
    proposals = [p for p in (checked(i, source) for i in found.get("items", [])) if p is not None]
    return proposals, bool(found.get("is_syllabus")), used


def quick_add(
    client: Client,
    model: str,
    line: str,
    today: date,
    tz: str,
    areas: Sequence[str],
    presets: Sequence[str],
    notes: Sequence[str] = (),
) -> tuple[dict[str, Any], int]:
    """The `add` input one free-form line asks for (§22.7); you confirm it before anything runs."""
    instructions = system(today, tz, areas, presets, notes)
    found, used = call(client, model, instructions, [{"type": "text", "text": line}], QUICK_ADD)
    return item_fields(found), used
