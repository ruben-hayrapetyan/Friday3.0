"""Services connected by the calendar link they publish (C96, your choices: Blackboard, Moodle, Brightspace/D2L and
Schoology for school; When I Work, Deputy, 7shifts and Sling for shift work). Each is a calendar link Friday already
reads (ingest/ics.py); what differs is how its events are read. A school system's are read as the Canvas feed's are
(assignments and exams by their words, suggested in your Inbox); a shift app's are your shifts, fixed work time that
goes straight in, as they're your schedule, not a suggestion. Homebase puts shifts in your phone's calendar instead of
publishing a link, so it reaches Friday through the Mac's calendars (the gallery says how)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkService:
    name: str
    kind: str | None  # how its events are read: a kind of yours ("Event"), or None for the feed's own words
    trusted: bool  # what it brings goes straight in (your shifts), not to your Inbox


LINKS = {
    "blackboard": LinkService("Blackboard", None, False),
    "moodle": LinkService("Moodle", None, False),
    "brightspace": LinkService("Brightspace", None, False),
    "schoology": LinkService("Schoology", None, False),
    "wheniwork": LinkService("When I Work", "Event", True),
    "deputy": LinkService("Deputy", "Event", True),
    "7shifts": LinkService("7shifts", "Event", True),
    "sling": LinkService("Sling", "Event", True),
}
