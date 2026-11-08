"""Rules the grammar of `rule_text.py` leaves, read by their words (8 Nov: "test a very wide range of possible rules a
user can type ... fully deterministic with absolutely minimal use of ai"). The grammar matches whole phrasings, so a
rule said a new way went to the AI ("fridays: easy. saturdays: push. sundays: normal", "no late homework. strictly.",
"book club is an only-if-im-ahead thing", "dont waste small gaps, throw a quick task in there"). Here each kind is
known by the words that only it uses, and its details (days and paces, the events named) are taken from the rest.
`read` tries this only after the grammar can't read the sentence and the sentence isn't two rules or a rule Friday
has no kind for; a reading here must say what was meant (every labelled corpus in tests/core/data holds it)."""

import re

from friday.core.rule_text import DAYS, PACE_WORDS, Reading, days_of, titles_in

MEALS = r"\b(?:breakfast|brunch|lunch|dinner|supper|meals?|meal times?|eating|eat|food)\b"
MEAL_NAMES = ("breakfast", "lunch", "dinner")
DAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?s?"
DAYS_SAID = rf"(?:{DAY}|weekends?|weekdays?)(?:(?:\s*(?:,|and|&|or|/)\s*|\s+)(?:{DAY}|weekends?|weekdays?))*"
# Whatever else in a sentence says it's another kind of rule: a clock time, an amount of time, a buffer.
OTHER_RULE = r"\b\d{1,2}(?::\d\d)?\s*(?:am|pm)\b|\b\d+(?:\.\d+)? ?(?:h|hrs?|hours?|m|mins?|minutes?)\b|\d:\d\d"


def read_more(t: str, unsure: bool = False) -> Reading | None:
    """One of the kinds below, or None. `t` is the sentence as the grammar's readers take it (rule_text.spoken);
    `unsure` when it has an if, unless or when, which only some kinds read as part of them."""
    readers = (read_meals_learned, read_meals_kept, read_running, read_fit_gaps, read_ahead, read_deadlines)
    for reader in readers if unsure else (*readers, read_pace, read_after):
        if found := reader(t):
            return found
    return None


def meals_in(t: str) -> tuple[str, ...]:
    named = tuple(m for m in MEAL_NAMES if re.search(rf"\b{m}\b", t))
    return named or MEAL_NAMES


LEARN = (
    r"\b(?:learn|learns|learned|figure (?:it )?out|figure out|work out|pick (?:it|that) up|notice|watch (?:what|when)"
    r"|from my (?:habits|week|logs|history)|my (?:eating )?(?:habits|pattern)|on (?:ur|your|its) own|over time"
    r"|let (?:friday|it|the app|you) (?:decide|figure|learn|work)|you decide|decide (?:for me|whether|if)"
    r"|based on what i (?:usually|actually)|don't assume|don't force|stop adding|i'?m not consistent|varies)\b"
)


def read_meals_learned(t: str) -> Reading | None:
    """Friday decides whether a meal happens from what you do: "idk when i eat lunch, just learn it"."""
    if not re.search(MEALS, t) or not re.search(LEARN, t) or re.search(OTHER_RULE, t):
        return None
    return Reading("meals_learned", "meals", events=meals_in(t))


KEEP_MEAL = (
    r"\b(?:never (?:skip|drop|cut)|(?:don't|do not|never) (?:skip|drop|cut|plan (?:work )?over|put (?:tasks|work|"
    r"anything) (?:on top of|over|thru|through)|schedule (?:tasks|work|anything) (?:thru|through|over))"
    r"|keep my|stays|comes? first|matters? more|more than (?:finishing|work)|must eat|actually eat|> ?work"
    r"|eaten up|never gets|protect|non[- ]negotiable|always (?:have|eat|keep))\b"
)


def read_meals_kept(t: str) -> Reading | None:
    """Meals kept even when work is late: "food > work. dont drop my meals when things get busy"."""
    if not re.search(MEALS, t) or not re.search(KEEP_MEAL, t) or re.search(OTHER_RULE + r"|\blearn", t):
        return None
    return Reading("meals_kept", "meals", events=meals_in(t))


def read_running(t: str) -> Reading | None:
    """Things that run by themselves go while you work: "slow uploads can run while i do other work, not during
    class"."""
    runs = (
        r"\b(?:runs? (?:in the background|by (?:itself|themselves))|background|unattended|auto(?:matic)? stuff"
        r"|exports?|uploads?|renders?|processing|downloads?|set[- ]and[- ]forget|babysit)\b"
    )
    working = (
        r"\b(?:while i'?m (?:busy )?working|while i (?:do|work)|alongside my tasks|overlap my work|only while"
        r"|not (?:during|my) (?:events|calls|class|meetings))\b"
    )
    return Reading("runs_while_working", "work") if re.search(runs, t) and re.search(working, t) else None


def read_fit_gaps(t: str) -> Reading | None:
    """Short tasks in short gaps, long in long: "fill the cracks in my schedule with little to-dos"."""
    gap = (
        r"\b(?:gaps?|cracks|free slots?|open blocks?|(?:big|long|open) (?:open )?(?:blocks?|stretches|afternoons?)"
        r"|between (?:lectures|meetings|classes)"
        r"|(?:\d+|odd) (?:min |minute |hr |hour )?(?:gaps?|windows?|half hours))\b"
    )
    size = r"\b(?:small|little|tiny|quick|short|long|big|5 min|bite[- ]sized)\b"
    if re.search(gap, t) and re.search(size, t) and not re.search(r"\b(?:at least|every|break|keep \w+ free)\b", t):
        return Reading("fit_gaps", "work")
    return None


AHEAD = r"(?:i'?m|i am|work is|i'?ve|everything is) (?:way |well |fully |not |all )?(?:ahead|caught up)"


def read_ahead(t: str) -> Reading | None:
    """An event you go to only when ahead: "book club is an only-if-im-ahead thing", "never go to happy hour unless im
    ahead", "if im ahead i can go to salsa, otherwise skip it"."""
    t = re.sub(r"\bonly[- ]if[- ]i(?:'?m)?[- ]ahead\b", "only if i'm ahead", t)
    if not re.search(rf"\b(?:if|unless|when|for when) {AHEAD}\b", t) or re.search(OTHER_RULE, t):
        return None
    rest = re.sub(rf"\b(?:only |never |always )?(?:if|unless|when|for when) {AHEAD}(?: (?:of|on) [a-z ]+)?\b", " ", t)
    rest = re.sub(
        r"\b(?:only|go to|go|keep|skip|skipping|attend|basically|really|want to|i can|can|strictly|never|no|thing"
        r"|is an?|is|are|the|my|a|an|it|otherwise|by default|reward|for|i|i'?d|i'll|like to|should|just|then)\b",
        " ",
        rest,
    )
    rest = " ".join(re.sub(r"[,.;:]", " ", rest).split())
    if not rest or len(rest.split()) > 3 or re.search(r"\b(?:extra|more|longer|day|days|week|less)\b", rest):
        return None  # "if I'm ahead, go to the gym an extra day": more of it, not whether to go
    return Reading("ahead", "events", events=titles_in(rest))


LATE = r"\b(?:late|overdue|past (?:the |its |their )?(?:deadline|due date)|due dates?|deadlines?|on time|by its due)\b"


def read_deadlines(t: str) -> Reading | None:
    """Nothing late: "no late homework. strictly.", "i'd rather work extra than submit anything late", "finish
    everything before its due, no exceptions"."""
    if re.search(r"\blate (?:nights?|at night|evenings?)\b|\b(?:stay up|work|sleep) late\b|\bcan be late\b", t):
        return None
    if re.search(OTHER_RULE, t) or re.search(r"\b(?:skip|ditch|miss) (?!any|a |the )", t) or re.search(MEALS, t):
        return None
    if re.search(
        r"\b(?:don't bother|once (?:they'?re|they'?ve|it'?s|its)|(?:don't|doesn't|dont) count|gets? (?:a )?0"
        r"|zero credit|start|early|as late as|close to|just before|pointless|no point|later than)\b"
        r"|\b\d{1,2}\b|\b(?:a|one|two|three|four|five|six|seven) (?:days?|weeks?) before\b",
        t,
    ):
        return None  # work that's pointless late (a setting), a start window, close to due: other kinds
    late = re.search(LATE, t) or re.search(r"\bbefore (?:it'?s|its|they'?re) due\b", t)
    against = re.search(
        r"\b(?:no|never|don't|dont|can't|cant|not|hate|rather|avoid|zero|matter|get everything done|finish everything"
        r"|everything done|more time|extra|whatever it takes|on schedule)\b",
        t,
    )
    return Reading("deadlines", "work") if late and against else None


PACES = {**PACE_WORDS, "grind": "Push", "grinding": "Push", "push": "Push", "beast mode": "Push", "go hard": "Push",
         "big work day": "Push", "light load": "Easy", "normal": "Normal", "normal-ish": "Normal", "regular": "Normal",
         "recovery": "Easy", "easy": "Easy", "light": "Easy", "chill": "Easy"}  # fmt: skip
PACE_SAID = "|".join(sorted((re.escape(w) for w in PACES), key=len, reverse=True))


def read_pace(t: str) -> Reading | None:
    """How hard each named day goes, however it's said: "fridays: easy. saturdays: push. sundays: normal", "go light on
    the days i have choir, which is tues and thurs", "on saturdays i can grind, on sundays go easy, rest of the week
    just normal". Each clause gives days, a pace, or both; a pace said without days goes with the days next to it."""
    if re.search(OTHER_RULE, t) or re.search(
        r"\b(?:free|off|no work|nothing|only|(?<!of the )week|appts?|appointments?|meetings?|to next|mornings?|afternoons?"
        r"|evenings?|nights?|stuff|tasks?|things|essays?|homework|hw|reading|studying|assignments?|papers?|if|unless)\b",
        t,
    ):
        return None
    found: dict[str, str] = {}
    pending_pace, pending_days = None, None
    rest_of_week = None
    t = re.sub(rf"({DAY}|weekends?|weekdays?)\s+(?:and|&)\s+(?=(?:{DAY}|weekends?|weekdays?)\b)", r"\1/", t)
    for clause in re.split(r"\s*(?:[,;.]|\band\b|\bbut\b|\bthen\b)\s*", t.replace(":", " ")):
        if not clause.strip():
            continue
        negated = re.search(r"\b(?:not|no|don't|never)\b", clause)
        word = re.search(rf"\b({PACE_SAID})\b", clause)
        pace = PACES[word[1]] if word and not negated else None
        if re.search(r"\b(?:rest of the week|other days|every other day|the rest)\b", clause):
            rest_of_week = pace
            continue
        said = re.search(DAYS_SAID, clause)
        days = days_of(said[0]) if said else None
        if days and pace:
            found.update(dict.fromkeys(days, pace))
        elif days and pending_pace:
            found.update(dict.fromkeys(days, pending_pace))
            pending_pace = None
        elif pace and pending_days:
            found.update(dict.fromkeys(pending_days, pace))
            pending_days = None
        elif days:
            pending_days = days
        elif pace:
            pending_pace = pace
    if pending_days or pending_pace or not found:
        return None
    if rest_of_week:
        found.update({d: rest_of_week for d in DAYS if d not in found})
    return Reading("pace", "pace", paces=tuple((d, found[d]) for d in DAYS if d in found))


def read_after(t: str) -> Reading | None:
    """Something done right after an event: "go to the gym straight after work", "after soccer, do reading", "review
    notes right after each lecture". A meal isn't an event to follow (the grammar's rule too)."""
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r",? (?:never later|not later|asap|pls|please)\b", " ", t)
    m = re.search(
        r"^ ?(.+?) (?:right|straight|just|directly|immediately)? ?after (?:each |every |my |the )*(.+?) ?$", t
    )
    if m and re.match(r"^ ?after\b", t):
        m = None
    if not m and (n := re.search(r"^ ?after (?:each |every |my |the )*([a-z ]+?),? (?:do |go to |hit )?(.+?) ?$", t)):
        event, subject = n[1], n[2]
    elif m:
        subject, event = m[1], m[2]
    else:
        return None
    subject = re.sub(
        r"^(?:(?:i|i'd|i'll|always|really|definitely|pls|please|can you|could you|want|like to|i like to|have|schedule"
        r"|put|do|go to|go|hit|the|my|a)\s+)+",
        "",
        subject.strip(),
    )
    subject = re.sub(r" time$", "", subject)
    event = event.strip()
    if (
        not subject
        or re.search(MEALS, event)
        or re.search(
            r"\d|\b(?:waking|wake|getting up|i|it|its|that|work out|class(?:es)? end|due)\b", event + " " + subject
        )
        or re.search(r"\b(?:no|nothing|never|not|don't|dont)\b|\b(?:week|day|break)$", subject)
        or len(subject.split()) > 3
        or len(event.split()) > 3
    ):
        return None
    return Reading("after", subject, event=event)
