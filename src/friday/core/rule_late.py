"""Late work's last chance in words (8 Nov: "If math homework becomes overdue, it must be done before sunday"): once
that work is overdue it's done before (or by) a weekday, and never planned after (planner/late_cutoff.py). Read from
your words as typed, before the grammar's spelling turns "be done before sunday" into a time window."""

import re

from friday.core.rule_text import Reading, subject_of

DAY = r"(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|nesday|rsday|urday|sday)?"
WHEN = r"(?:next |this |the |that |the following |the next )?"
DONE = (
    r"(?:(?:it|they|that|those|i|you)(?: (?:'ll|will))? )?"
    r"(?:(?:must|has to|have to|need to|needs to|should|gotta|got to|is to|are to) )?"
    r"(?:(?:be|get|gets) )?(?:done|finished|completed|submitted|handed in|turned in|in|do it|do them"
    r"|finish it|finish them|get it done|get them done|complete it|submit it|hand it in|turn it in)? ?"
)
LATE = r"(?:overdue|late|past (?:its|their|the) due(?: date)?|past due|behind)"
SAID = (
    # "if math homework becomes overdue, it must be done before sunday"
    rf"^(?:if|when|once|whenever|in case) (?P<subject>.+?) (?:becomes?|is|are|gets?|goes|go|ends? up|turns?|falls?)"
    rf" (?:ever )?{LATE}[ ,]+(?:then )?{DONE}(?P<rel>before|by|no later than|until|till|by the end of) {WHEN}{DAY}"
    r"(?: at the latest)?$",
    # "overdue math homework has to be finished by sunday", "late readings: done before saturday"
    rf"^(?:any |my |the |all )?{LATE} (?P<subject>.+?)[ :,]+{DONE}(?P<rel>before|by|no later than|until|till"
    rf"|by the end of) {WHEN}{DAY}(?: at the latest)?$",
    # "math homework can be late but it must be done by sunday"
    rf"^(?P<subject>.+?) (?:can|may|is allowed to|are allowed to) (?:be|go|run) {LATE}[ ,]+(?:but |only |but only )*"
    rf"{DONE}(?P<rel>before|by|no later than|until|till|by the end of) {WHEN}{DAY}(?: at the latest)?$",
)


def read_late_cutoff(text: str) -> Reading | None:
    """`Reading("late_cutoff", subject, rel="before" or "on", days=(day,))`: "on" is by the end of that day."""
    t = " ".join(text.lower().replace("’", "'").split()).rstrip(".!")
    for pattern in SAID:
        if m := re.search(pattern, t):
            said = re.sub(r"^(?:my|the|any|all|an?) ", "", m["subject"].strip())
            # "if it is late": what "it" is, the grammar can't say; "late night study": a time, not lateness
            if said in ("i", "it", "you", "this", "that", "they", "anything", "something") or re.match(
                r"(?:night|nights|evening|evenings|morning|mornings|afternoon)\b", said
            ):
                return None
            subject = subject_of(said)
            if not subject:
                return None
            rel = "before" if m["rel"] in ("before", "no later than") else "on"
            return Reading("late_cutoff", subject, rel=rel, days=(m[m.lastindex or 0][:3],))
    return None
