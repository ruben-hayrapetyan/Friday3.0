"""A stand-in for the Anthropic client: it answers every call with the tool input it was given."""

from dataclasses import dataclass, field
from typing import Any

from friday.sim.fakes import answered

FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:lecture-1
SUMMARY:CS 1110 Lecture
DTSTART:20261020T140000Z
DTEND:20261020T151500Z
RRULE:FREQ=WEEKLY;BYDAY=TU,TH;COUNT=20
END:VEVENT
BEGIN:VEVENT
UID:ps4
SUMMARY:Due: PS4
DTSTART:20261023T035900Z
DTEND:20261023T035900Z
END:VEVENT
BEGIN:VEVENT
UID:holiday
SUMMARY:Fall break
DTSTART;VALUE=DATE:20261026
DTEND;VALUE=DATE:20261028
END:VEVENT
BEGIN:VTODO
UID:essay
SUMMARY:Essay draft
DUE;VALUE=DATE:20261030
END:VTODO
END:VCALENDAR
"""


@dataclass
class FakeClient:
    answer: dict[str, Any]
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def messages(self) -> "FakeClient":
        return self

    def create(self, **request: Any) -> Any:
        self.calls.append(request)
        return answered(self.answer)
