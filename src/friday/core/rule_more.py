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
    later = (read_free, read_pace, read_after, read_days, read_cap, read_early, read_window)
    for reader in readers if unsure else (*readers, *later):
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
    titles = titles_in(rest)  # "only and if i'm ahead" leaves "and": no event (audit, 12 Nov)
    return Reading("ahead", "events", events=titles) if titles else None


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
        r"\b(?:free|off|no work|nothing|only|(?<!of the )week|appts?|appointments?|meetings?|to next|mornings?"
        r"|afternoons?|evenings?|nights?|stuff|tasks?|things|essays?|homework|hw|reading|studying|assignments?|papers?"
        r"|if|unless)\b",
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


WORD_HOURS = {w: n for n, w in enumerate("one two three four five six seven eight nine ten eleven twelve".split(), 1)}
NUMBER = "|".join(WORD_HOURS)


def hour_of(word: str) -> int:
    return WORD_HOURS.get(word, int(word) if word.isdigit() else 0)


# Clock times however they're written, put as the readers below take them.
CLOCK_SAID = (
    (r"[–—]", "-"),
    (r"\b(\d{1,2}(?::\d\d)?)\s*a\.\s?m\.?", r"\1am"),
    (r"\b(\d{1,2}(?::\d\d)?)\s*p\.\s?m\.?", r"\1pm"),
    (r"\b(\d{1,2}(?::\d\d)?)\s+(am|pm)\b", r"\1\2"),
    (r"\bo'?clock\b", ""),
    (rf"\b(?:a )?quarter to ({NUMBER}|\d{{1,2}})\b", lambda m: f"{hour_of(m[1]) - 1 or 12}:45"),
    (rf"\b(?:a )?quarter (?:past|after) ({NUMBER}|\d{{1,2}})\b", lambda m: f"{hour_of(m[1])}:15"),
    (rf"\bhalf (?:past|after) ({NUMBER}|\d{{1,2}})\b", lambda m: f"{hour_of(m[1])}:30"),
    (rf"\b({NUMBER}|\d{{1,2}}) in the morning\b", lambda m: f"{hour_of(m[1])}am"),
    (rf"\b({NUMBER}|\d{{1,2}}) (?:at night|in the evening)\b", lambda m: f"{hour_of(m[1])}pm"),
    (rf"\b({NUMBER}) ?(am|pm)\b", lambda m: f"{hour_of(m[1])}{m[2]}"),
    (r"\b(\d{1,2})(\d\d)\s*-\s*(\d{1,2})(\d\d)\b", lambda m: f"{int(m[1])}:{m[2]}-{int(m[3])}:{m[4]}"),
    (r"\b(by|before|after|until|till|til|past|at|from|to|than) ([01]?\d|2[0-3])([0-5]\d)\b", r"\1 \2:\3"),
    (r"\b([01]?\d|2[0-3])([0-5]\d)\s*(am|pm)\b", r"\1:\2\3"),
    (r"\bm\s*-\s*f\b", "weekdays"),
    (r"(?<!school )(?<!week )\b(?:nite|night|nightly|evening|daily|my) (?=cutoff|cut off|curfew)", ""),
    (r"\b(?:scheduel|shedule|schedual)\b", "schedule"),
    (r"\b(?:school|week) ?nights? (?=mornings?|afternoons?|evenings?)", "sun/mon/tue/wed/thu "),
    (r"\b(?:school|week) ?nights?\b", "sun/mon/tue/wed/thu nights"),
    (rf"\b({NUMBER})(?= (?:pm|am|is (?:my|the) [a-z -]*(?:cutoff|limit)))", lambda m: str(hour_of(m[1]))),
)
TIME = r"(?:noon|midnight|\d{1,2}:\d\d(?:am|pm)?|\d{1,2}(?:am|pm))"
BARE = r"(?:\d{1,2})(?![\d:.])(?! ?(?:h|hrs?|hours?|m|mins?|minutes?|days?|weeks?|x|%)\b)"
TIME_CUE = r"(?:by|before|after|until|till|til|past|at|from|starts?|ends?|cutoff|cut off|is|than|stop|finish|end)"
END = (
    r"\b(?:by|before|until|till|til|cutoff|cut off|cuts? off|ends?|ending|stops?|stopping|finish(?:ed|es)?|done"
    r"|wrap(?:s|ped)? up|latest|clocks? out|no later than|at the latest|and earlier|prior to)\b"
)
START = (
    r"\b(?:after|past|later than|beyond|starts?|starting|begins?|from|earliest|no earlier than|onwards?|and later"
    r"|or later|not human|boot(?:s|ed)? up)\b"
)
PART = r"\b(?:the )?(morning|afternoon|evening|night|nighttime)s?\b|\bthe (am)\b"
# What may come before a part of the day when it's a time ("in the evening", "weekday mornings"); any other word makes
# it an event's name ("movie night", "date night").
BEFORE_PART = (
    r"(?:^|in|the|during|all|every|each|my|no|of|on|these|those|late|early|then|only|any|and|or|weekday|weekend"
    rf"|{DAY}|sat|sun|mon|tue|wed|thu|fri)"
)
PARTS = {"morning": ("08:00", "12:00"), "am": ("08:00", "12:00"), "afternoon": ("12:00", "17:00"),
         "evening": ("17:00", "22:00"), "night": ("22:00", "02:00"), "nighttime": ("22:00", "02:00")}  # fmt: skip
NO = r"\b(?:no|never|not|don't|dont|nothing|zero|avoid|can't|cant|won't|isn't|shouldn't|stays? out|is a no|crash)\b"
# Words of a rule's frame: how it's asked, what it's about in general, the rule's own cue words. Anything left beyond
# these and the subject means the sentence says more than one rule's worth: the AI reads it.
FRAME = set(
    """i i'm i'd i'll me my myself the a an any anything nothing something stuff things thing work tasks task schedule
    scheduled book put give gimme plate calendar on in at of for to it that this there these them so and or is are be
    am was should will would can could must need want gotta have has do does done get let keep make sure every each all
    only just also really like about around happen happens happening goes go time day days daily no never not don't
    dont zero avoid can't cant won't isn't shouldn't allowed ok fine here by before after until till til past from
    start starts starting end ends ending cutoff cut off stop stops stopping finish finished wrap up latest earliest
    later earlier than prior beyond onward onwards stays stay out pls please thx thanks tbh honestly lol seriously
    when then those hours hour gets happens get going be done stuff's everything productive willing working work's
    plan planned planning anymore period anytime whatsoever""".split()
) - {"work", "stuff", "things", "tasks", "task", "for", "of"}
# Words that tell of the person or the day, not a kind of work: a subject with one is no subject.
NOT_SUBJECT = set(
    """doesn't does soonest human crack book bartend available person waits wait written write get gets reserved owl
    need needs wind down i'm i am is are be can i'll night morning evening day zo done productive willing brain mind
    body clocks clock cutoff nite home head heads sleep lazy grandpa happens happen anything nothing calendar plate
    everything something mentally earliest latest soonest best worst person allowed late early outside inside
    happens""".split()
)
NARRATION = (
    r"\b(?:i'?m|i (?:head|go|get|sleep|work|bartend|have|study|do|am|can|can't|need|like|get)|my (?:brain|body|mind)"
    r"|class (?:goes|runs|ends)|because|cause|bc|since|lazy|grandpa|human|tired|fried|dead|sleep in)\b"
)
EXCEPT = (
    rf"\b(?:except|but not|other than|besides|aside from|apart from|excluding|outside of|minus) (?:on |for )?"
    rf"({DAYS_SAID})|({DAYS_SAID}) (?:excluded|aside|is the exception|'s the exception|are the exception)"
    rf"|unless it'?s (?:a )?({DAY})"
)


def days_said(t: str) -> tuple[tuple[str, ...] | None, str]:
    """The days a sentence names, those it excepts taken out, and the sentence without them."""
    excepted: set[str] = set()
    for m in re.finditer(EXCEPT, t):
        excepted |= set(days_of(next(g for g in m.groups() if g)) or ())
    t = re.sub(EXCEPT, " ", t)
    named = [m[0] for m in re.finditer(DAYS_SAID, t)]
    days = set(days_of(" ".join(named)) or ()) if named else set(DAYS) if excepted else set()
    t = re.sub(rf"\b(?:on |every |each )?(?:the )?{DAYS_SAID}\b", " ", t)
    found = tuple(d for d in DAYS if d in days - excepted)
    return (found or None), t


def clock_of(said: str, rel: str | None) -> str | None:
    """A clock time as said: a bare hour that ends a day (7 to 11) is the evening's, any under 7 the afternoon's."""
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?(am|pm)?|noon|midnight", said.strip())
    if not m:
        return None
    if said.strip() in ("noon", "midnight"):
        return "12:00" if said.strip() == "noon" else "00:00"
    h, mm = int(m[1]), int(m[2] or 0)
    if h > 23 or mm > 59:
        return None
    if m[3] == "pm" and h < 12:
        h += 12
    elif m[3] == "am" and h == 12:
        h = 0
    elif not m[3] and not m[1].startswith("0") and (h < 7 or (rel == "before" and 7 <= h <= 11)):
        h += 12  # "no work past 10" is 10pm; "between 5 and 7" the evening
    return f"{h:02d}:{mm:02d}"


def subject_left(words: str) -> str | None:
    """What the rule is about: the words left once its frame, times, days and parts are gone; "work" when none."""
    from friday.core.rule_text import JUNK_SUBJECT, subject_of

    words = re.sub(
        r"\b(?:i )?(?:only )?(?:can't |cannot )?(?:start|study|do|work on|write|read) (?:for )?(?=[a-z])", " ", words
    )
    left = [w for w in re.findall(r"[a-z0-9']+", words) if w not in FRAME]
    while left and left[0] in ("for", "of", "work"):
        left = left[1:] if len(left) > 1 or left[0] != "work" else left
        if left == ["work"]:
            break
    while left and left[-1] in ("for", "of"):
        left = left[:-1]
    if not left or left in (["stuff"], ["things"], ["tasks"], ["task"], ["work"]):
        return "work"
    subject = subject_of(" ".join(left))
    if subject in ("work", "deep work", "light work", "exam prep"):
        return subject
    if len(left) > 3 or any(w in NOT_SUBJECT or w.isdigit() for w in left):
        return None
    return None if re.search(JUNK_SUBJECT, subject) else subject


def read_window(t: str) -> Reading | None:
    """When a kind of work goes, by the clock or part of the day, said any way: "nite cutoff is 10, dont scheduel
    past it", "M–F: studying ends at 9:45pm", "earliest I'm willing to crack a book is 8", "problem sets: afternoons
    only"."""
    if re.search(
        r"\b(?:free|open|clear|empty|max|at most|most|a day|per day|daily|early|due|buffer|deadline|if|unless|when"
        r"|sleep|bed|wake|asleep|lunch|dinner|breakfast|meals?|night before|optional|skip|ahead|break|next day|eve"
        r"|tomorrow|ease|easier|lighter|less packed|stacked|packed|block|blocked|reserved|night owl|morning person"
        r"|early bird|the only|each way|before and|after and|i have|i've got|i got)\b"
        r"|\b\d+(?:\.\d+)? ?(?:h|hrs?|hours?|m|mins?|minutes?)\b|\bhalf an hour\b|\bmy [a-z ]+ days\b"
        r"|\bonly (?:do )?(?:easy|light|hard|deep|mindless|brainless|focus(?:ed)?)\b"
        rf"|\b(?:are|is) (?:on )?{DAYS_SAID}\b|\bfor (?:the|my) [a-z]+ ?$"
        r"|\b(?:before|after) (?:the |my |a |each |every |class|practice|work\b|lab|gym|lecture|school)",
        t,
    ):
        return None
    for pattern, put in CLOCK_SAID:
        t = re.sub(pattern, put, t)
    days, t = days_said(t)
    pieces = [p for p in re.split(r"\s*(?:[,.;!]|\s-\s|=|\bso\b|\bthen\b)\s*", t) if p.strip()]
    timed = [p for p in pieces if re.search(rf"{TIME}|\b{TIME_CUE} {BARE}|{PART}|{BARE}\s*-\s*{BARE}", p)]
    if not timed:
        return None
    rule = " ".join(timed)
    topics = [re.split(r"(?<!\d):(?!\d)", p)[0] for p in pieces if re.search(r"(?<!\d):(?!\d)", p)]
    topic = " ".join(x for x in topics if not re.search(rf"{TIME}|\d", x))
    rule = re.sub(r"(?<!\d):(?!\d)", " ", rule)
    plain = " ".join(p for p in pieces if not re.search(NARRATION, p))
    negated = bool(re.search(NO, f"{rule} {plain}")) and not re.search(r"\bnot outside\b", rule)
    span = re.search(
        rf"(?:between |from )?({TIME}|{BARE})\s*(?:-|to|until|till|thru|through|and)\s*({TIME}|{BARE})"
        rf"|start(?:s|ing)? (?:at )?({TIME}|{BARE})\b.*\bend(?:s|ing)? (?:at )?({TIME}|{BARE})"
        rf"|({TIME}|{BARE}) start\b.*\b({TIME}|{BARE}) (?:finish|end)",
        rule,
    )
    times = re.findall(TIME, rule) + [m[1] for m in re.finditer(rf"\b{TIME_CUE} ({BARE})\b(?!\s*(?:am|pm))", rule)]
    if span:
        a, b = [g for g in span.groups() if g][:2]
        until = clock_of(b, "before")
        at = clock_of(a, None)
        if at and until and not re.search(r"am|pm|noon|midnight", a) and re.search(r"pm", b) and at < "12:00":
            at = f"{int(at[:2]) + 12:02d}{at[2:]}" if int(at[:2]) + 12 < int(until[:2]) else at
        rel = "not_between" if negated else "between"
        cleaned = rule.replace(span[0], " ")
        reading = Reading("window", "work", rel=rel, at=at, until=until, days=days) if at and until else None
    elif len(set(times)) == 1:
        rel = direction(rule, negated)
        at = clock_of(times[0], rel)
        cleaned = re.sub(rf"\b({TIME_CUE}) {BARE}\b", r"\1 ", re.sub(TIME, " ", rule))
        reading = Reading("window", "work", rel=rel, at=at, days=days) if rel and at else None
    elif (
        not times
        and (part := re.search(PART, rule))
        and re.search(r"\b(?:in|during|only|then|no|except|out of)\b", rule)
        and re.search(rf"(?:{BEFORE_PART})\s+{re.escape(part[0].strip())}|^\s*{re.escape(part[0].strip())}", rule)
    ):
        start, end = PARTS[part[1]]
        rel = "not_between" if negated or re.search(r"\bexcept\b", rule) else "between"
        cleaned = rule.replace(part[0], " ")
        reading = Reading("window", "work", rel=rel, at=start, until=end, days=days)
    else:
        return None
    if reading is None:
        return None
    cleaned = re.sub(r"\b(?:and )?not outside (?:of )?(?:it|that|those|them|this)\b|\bhappens?\b", " ", cleaned)
    cleaned = re.sub(rf"{END}|{START}|{NO}|{PART}|\bexcept\b|\bin\b|\bonly\b", " ", cleaned)
    subject = subject_left(f"{topic} {cleaned}")
    if subject is None or re.search(r"\b(?:meetings?|calls?|classes|lectures?|appointments?)\b", subject):
        return None
    return Reading("window", subject, rel=reading.rel, at=reading.at, until=reading.until, days=reading.days)


def direction(rule: str, negated: bool) -> str | None:
    """Whether work goes before the time or after it."""
    if re.search(r"\b(?:until|till|til)\b", rule):
        held = negated or re.search(r"\b(?:wait|waits|start|can't|not human|boot)", rule)
        return "after" if held else "before"
    if re.search(r"\b(?:before|prior to|earlier than|and earlier)\b", rule):
        return "after" if negated else "before"
    if re.search(END, rule):
        return "before"
    if re.search(START, rule):
        return "before" if negated and not re.search(r"\bearliest|no earlier\b", rule) else "after"
    return None


DAYS_OFF = (
    r"\b(?:no|never|not|don't|avoid|off|no[- ]go|no[- ]school|(?:school|work|study|homework)[- ]free|day of rest"
    r"|rest days?|(?:are|is) (?:mine|for me|for family|family days?)|family day|no school)\b"
)
DAYS_ON = (
    r"\b(?:only|go(?:es)? on|gets? done on|happens? on|nowhere else|fine for (?:work|school|studying)|study days"
    r"|work days|the only days)\b"
)


def read_days(t: str) -> Reading | None:
    """Which days a kind of work goes on, said any way: "orgo is a no-go on sundays", "Sat: off. Sun: off.", "monday
    thru saturday only, sundays are mine", "every day except tuesday is fine for work"."""
    if re.search(rf"{OTHER_RULE}|{PART}|\b(?:if|unless|when|week|pace|easy|push|grind|chill|hard|light(?:er)?)\b", t):
        return None
    if re.search(r"\b(?:month|monthly|other|alternate|delete|add|move|cancel|remove)\b", t):
        return None  # "two rest days a month", "every other friday", "delete the gym event on monday"
    if re.search(r"\b(?:after|before|during|around)\b|^ ?only (?!on\b)[a-z]", t):
        return None  # "no work after dinner on fridays" (an event's time); "only reading on sundays" (nothing else)
    if re.search(r"\b(?:are|is) (?:just |only )?for (?!me\b|family|rest)|\bmeetings?\b|\bcalls?\b", t):
        return None  # "tuesdays are for CS only": one kind of work kept to a day (no such rule); meetings are events
    t = re.sub(r"\bone day off a week and it'?s (?:always )?", "off on ", t)
    pieces = [p for p in re.split(r"\s*(?:[,.;!]|\bso\b)\s*", t) if p.strip()]
    on_days: set[str] = set()
    off_days: set[str] = set()
    subject_words = []
    for piece in pieces:
        days, rest = days_said(piece)
        if not days:
            if re.search(DAYS_OFF + "|" + DAYS_ON, piece):
                return None  # a rule's word without its days: something else is said
            continue  # a reason ("I work retail")
        off = bool(re.search(DAYS_OFF, piece)) and not re.search(r"\bnowhere else\b", piece)
        if not off and not re.search(DAYS_ON + r"|\bare\b|\bwhenever\b|\bwork\b", piece):
            return None
        (off_days if off else on_days).update(days)
        subject_words.append(
            re.sub(rf"{DAYS_OFF}|{DAYS_ON}|\b(?:are|is|days?|whenever|i can|fine|mine|mode)\b", " ", rest)
        )
    if on_days & off_days:
        return None  # the same day both ways
    on = on_days or set(DAYS) - off_days
    if not on or on == set(DAYS):
        return None
    said = " ".join(subject_words)
    if not re.search(r"[a-z]", re.sub(r"\bonly\b", " ", said)) and not re.search(
        r"\b(?:off|study|studying|work|school|free|rest|mine)\b", t
    ):
        return None  # "thurs only", "never weekends" alone name nothing (halves of rules said whole)
    subject = subject_left(said)
    if subject is None:
        return None
    return Reading("days", subject, rel="on", days=tuple(d for d in DAYS if d in on))


PER_DAY_SAID = (
    r"\b(?:a|per|each|every|one|any one|a single|into one|in a|in one) day\b|\bdaily\b|\bday's\b|/day\b|\btotal\b"
)
CAP_SAID = (
    r"\b(?:tap out|not a minute more|exceed|plenty|never more|more than|ceiling|cap|max(?:es)?(?: out)?|most|at or"
    r" below|up to|only good for|only do|can only|beyond|never longer|limit|stack|tops|or less)\b"
)


def read_cap(t: str) -> Reading | None:
    """At most so long a day, said any way: "I tap out after five and a half hours a day", "8hrs/day is plenty, never
    more", "most I can handle per day is 6 and a half hours", "on fridays I'm only good for about 2 hours"."""
    if re.search(r"\b(?:at least|minimum|week|weekly|or more|every hour|in a row|break|if|unless|when|sleep)\b", t):
        return None
    if re.search(r",? and (?:only|never|no|not)\b", t):
        return None  # "max 2 hours of orgo a day, and only on weekdays": two rules
    amount = re.search(r"\b(\d+(?:\.\d+)?) ?(h|hrs?|hours?|m|mins?|minutes?)\b", t)
    if not amount or len(re.findall(r"\b\d+(?:\.\d+)? ?(?:h|hrs?|hours?|m|mins?|minutes?)\b", t)) > 1:
        return None
    days, rest = days_said(t)
    if not re.search(CAP_SAID, t) or not (re.search(PER_DAY_SAID, t) or days):
        return None
    hours = round(float(amount[1]) / (60 if amount[2].startswith("m") else 1), 2)
    rest = rest.replace(amount[0], " ")
    rest = re.sub(rf"{CAP_SAID}|{PER_DAY_SAID}|\b(?:workload|study time|about|around|handle|can|do|i'?m|good|absolute"
                  r"|burnt out|burned out|dead|fried)\b", " ", rest)  # fmt: skip
    subject = subject_left(re.split(r"\s*(?:,|\bbecause\b|\bbc\b|\bor\b)\s*", rest)[0])
    return Reading("cap", subject, amount=hours, days=days) if subject else None


EARLY_SAID = (
    r"\b(?:early|ahead|in advance|before (?:it'?s|they'?re|stuff is|the|its|their|i|we) (?:due|due date|deadline"
    r"|present|close|closes)|out from (?:the )?deadline|wiggle room|in the bag|by the day before)\b"
)


def read_early(t: str) -> Reading | None:
    """Work done some days before it's due, said any way: "lab reports: aim to have them ready 48 hours ahead", "submit
    applications a week before they close", "never leave essays to the last day, finish them 1 day early"."""
    if not re.search(EARLY_SAID, t) or re.search(r"\b(?:start|starting|begin|if|unless|week before (?:the|my) )", t):
        return None
    t = re.sub(r"\ba fortnight\b", "14 days", t)
    t = re.sub(r"\b(?:a|one) week\b", "7 days", t)
    t = re.sub(r"\b(?:a|one) day\b|\bthe day before\b", "1 day", t)
    found = re.findall(r"\b(\d+(?:\.\d+)?) ?(days?|hours?|hrs?|weeks?)\b", t)
    if len(found) != 1:
        return None
    n, unit = float(found[0][0]), found[0][1]
    days = n / 24 if unit.startswith("h") else n * 7 if unit.startswith("w") else n
    what = re.sub(r"\b(?:don't|dont) wait (?:till|until|til) the last minute\b", " ", t)
    what = re.sub(r"\b(?:on|for) (?:every|each|all|any) (?:of my )?deadlines?\b", " ", what)
    named = re.search(r"\bleave ([a-z ]+?) (?:to|till|until) the last\b", what)
    what = re.sub(r"\bnever leave [a-z ]+? (?:to|till|until) the last \w+\b", " ", what)
    what = re.sub(
        rf"{EARLY_SAID}|\b\d+(?:\.\d+)? ?(?:days?|hours?|hrs?|weeks?)\b|\b(?:finish(?:ed)?|done|ready|submit|have|aim"
        r"|to|be|with|need|needs|always|at least|by|before|all|everything|i like being|i want|being)\b",
        " ",
        what,
    )
    words = re.split(r"\s*[,:]\s*", what.strip())
    words = [w for w in words if w.strip() and not re.fullmatch(r"\s*(?:them|it|those|these)\s*", w)]
    if named and not words:
        words = [named[1]]
    subject = subject_left(" ".join(words)) if len(words) <= 1 else None
    return Reading("early", subject, amount=round(days, 3)) if subject else None


FREE_SAID = r"\b(?:free|open|clear|empty|wide open|block(?:ed)? (?:out|off))\b"
LIGHTER_SAID = r"\b(?:lighter|less packed|less busy|stacked|ease off|go easier|easier on me)\b"


def read_free(t: str) -> Reading | None:
    """Time kept free, all of it or some, said any way: "wednesdays stay clear all day", "keep saturday afternoons and
    evenings free", "make tuesday mornings less packed", "on weeknights I need 8-9pm open to call home"."""
    lighter = re.search(LIGHTER_SAID, t)
    if not (re.search(FREE_SAID, t) or lighter) or re.search(
        r"\b(?:at least|minimum|if|unless|when|week|front ?load|after|meetings?|calls?|grind|push|go hard|lock in)\b"
        r"|\b(?:school|work|study|homework|screen|phone) free\b",
        t,
    ):
        return None
    t = re.sub(r"\bevnings?\b", "evenings", t)
    for pattern, put in CLOCK_SAID:
        t = re.sub(pattern, put, t)
    recurring = re.search(rf"\b(?:{DAY})s\b|\bweek(?:end|day|night)s?\b|\bevery\b|\beach\b|\bdaily\b", t)
    days, rest = days_said(t)
    parts = [m[1] or m[2] for m in re.finditer(PART, rest)]
    span = re.search(rf"({TIME}|{BARE})\s*(?:-|to|until)\s*({TIME}|{BARE})", rest)
    if re.search(r"\bfor (?:the|my) [a-z]+\b", rest) and not recurring:
        return None  # "block out 4-6 on friday for the dentist": once, an event
    if span:
        until = clock_of(span[2], "before")
        at = clock_of(span[1], None)
        if at and until and at < "12:00" and int(at[:2]) + 12 < int(until[:2] or 0) + 12 and "pm" in span[2]:
            at = f"{int(at[:2]) + 12:02d}{at[2:]}" if int(at[:2]) + 12 <= int(until[:2]) else at
        window = (at, until) if at and until else None
    elif parts:
        ordered = sorted({PARTS[p] for p in parts})
        if any(a[1] != b[0] for a, b in zip(ordered, ordered[1:], strict=False)):
            return None  # "friday nights and saturday mornings": two stretches
        window = (ordered[0][0], ordered[-1][1])
    else:
        window = None
    if window is None and not days:
        return None
    if window is None and lighter:
        return None  # a whole day lighter is a pace
    share = 0.5 if lighter else None
    if window:
        return Reading("free", "work", rel="between", at=window[0], until=window[1], days=days, amount=share)
    return Reading("free", "work", days=days)
