"""Rules from sentences (v22 Rules, M11): a fixed grammar, no LLM, from what you type to a Reading (what, when,
which days), and from a Reading and a strength to one of the planner's rule types. It reads:

- `lunch before 1pm`, `no work after 10pm on weekdays`, `deep work in the morning`, `gym between 5 and 7pm`:
  `time_preference` (Always forbids the other hours);
- `no work on sundays`, `reading only on weekends`: `time_preference` by day;
- `keep saturday mornings free`, `keep evenings free`: `reserve` (Always forbids the window);
- `at most 6 hours a day`, `no more than 2h of reading a day`: `daily_load`;
- `finish things a day early`, `finish essays 2 days before they're due`: `finish_early`;
- `gym right after class`: `after_event`;
- `go easier on saturday and go harder on sunday`, `take it easy on weekends`: a pace for those weekdays, every week
  (not a planner rule: `pace.weekly`, which the day's dials come from);
- `push when necessary for work not to be late`, `don't let work be late`: deadlines first, which is built in
  (`late_work`), so it's said to be on already rather than added;
- `gym and climbing club are optional`, `skip gym if there's too much work`: `skippable`, events whose time is
  used only when work would otherwise be late;
- `climbing club only if I'm ahead`, `I usually skip climbing club`: `skippable` the other way round, events whose
  time work takes first, so you go only in weeks the work fits without it;
- `no work after 10pm the night before climbing club`, `if I'm going to climbing club the next day, the day before
  must end at 10`: `before_event`, which holds only when you're going;
- `30 minutes before and after gym`, `leave 15 minutes around climbing club`, `20 min before gym and 40 after`:
  `travel`, time kept free around those events (to get there, change, shower), on top of each kind's;
- `exam prep as close to the exam as possible`, `prep for the math quiz close to the quiz with a day of buffer`,
  `readings as late as possible`: `close_to_due`, work planned in the last free time before it's due (for prep, the
  exam), or before a buffer kept clear ahead of it;
- `never skip lunch or dinner`, `always keep my meals`: those meals' routines kept even when work is late
  (`elastic_shortfall` in the deadlines stage); `let Friday decide breakfast`, `learn whether I have breakfast`:
  Friday plans that meal or stops, and when, from what meal tracking learns (`meal_learned`, applied each night);
- `short tasks in short gaps, long tasks in long stretches`, `fit tasks to the gaps`, `save big blocks for long
  work`: each task priced by how far its sitting is from the free stretch it's in (`fit_gaps`);
- `things that run by themselves only while I'm working, not during events`, `background tasks must not run during
  class`: a task that runs by itself started only where all its running time misses events and the night
  (`runs_while_working`);
- `I want at least 7 hours of sleep per night`, `never less than 7h of sleep`, `8 hrs of sleep on school nights`: the
  hours before each morning's wake kept for sleep (`sleep_min`); a bedtime alone (`bed by 11`) is the sleep setting.
"""

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from friday.core.time import ampm_in

Strength = Literal["Prefer", "Strongly", "Always"]
Kind = Literal[
    "window", "days", "free", "cap", "early", "after", "pace", "deadlines", "optional", "ahead", "night_before",
    "around", "close", "meals_kept", "meals_learned", "fit_gaps", "runs_while_working", "sleep_min", "spacing",
]  # fmt: skip
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
EVERYTHING = {"work", "anything", "things", "tasks", "stuff", "it", "everything", "all", "all work", "my work"}
DEEP = {"deep work", "focused work", "hard work", "focus work", "hard stuff", "hard tasks", "hardest work",
        "hard focus", "brain-heavy stuff", "brain heavy stuff", "brain-heavy work", "heavy stuff", "heavy work",
        "heavy tasks", "hard thinking", "thinking work", "brainy stuff", "difficult work", "difficult stuff",
        "challenging work", "intense work", "intense stuff", "concentrated work", "heavy focus work",
        "brain intensive work", "brain intensive stuff", "mentally heavy work", "mentally heavy stuff",
        "hard focus stuff", "focus stuff", "focused stuff", "deep focus"}  # fmt: skip
# Light work is work marked light (energy): `shallow work after 8pm` was a rule about a task titled "shallow work".
LIGHT = {"light work", "shallow work", "easy work", "low energy work", "low energy tasks", "low-energy tasks",
         "low-effort stuff", "low effort stuff", "mindless stuff", "mindless work", "mindless tasks", "busywork",
         "busy work", "admin stuff", "admin work", "admin", "low-energy stuff", "low energy stuff", "easy things",
         "brainless tasks", "brainless stuff", "brainless work", "mindless things", "low effort tasks", "light stuff",
         "easy tasks", "light tasks", "easy stuff", "low effort work", "low-effort work",
         "shallow tasks",
         "shallow stuff"}  # fmt: skip
TIME = r"(noon|midnight|\d{1,2}(?::\d\d)?\s*(?:am|pm)?)"
DAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?"
DAY_WORDS = (
    rf"((?:{DAY}|weekdays?|weekends?|every day)(?:(?:\s*(?:,\s*(?:and|or)?|and|&|or|/|\+)\s*|\s+)(?:{DAY}|weekends?))*)"
)
UNIT = r"(?:h|hrs?|hours?|m|mins?|minutes?)"
NIGHT_BEFORE_SAID = r"\b(?:next (?:day|morning)|(?:night|day|evening) before|tomorrow)\b"  # the night-before reader's
NUMBER = r"(\d+(?:\.\d+)?)"
SPAN_OF = rf"{NUMBER} ?({UNIT})\b"


@dataclass(frozen=True)
class Reading:
    kind: Kind
    subject: str = "work"  # "work" is everything; else deep work, an area, a preset or a title
    rel: Literal["before", "after", "between", "not_between", "on", "not_on"] | None = None
    at: str | None = None  # HH:MM
    until: str | None = None  # HH:MM, for between
    days: tuple[str, ...] | None = None  # None is every day
    amount: float | None = None  # hours a day for cap, days for early
    event: str | None = None  # after
    paces: tuple[tuple[str, str], ...] | None = None  # pace: (weekday, pace name), every week
    events: tuple[str, ...] | None = None  # optional, ahead, night_before, around: words in the events' titles
    before_min: int | None = None  # around: minutes kept free before those events
    after_min: int | None = None  # around: and after them

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
    if not m[3] and hour < 7 and not m[1].startswith("0"):  # "between 5 and 7" is the evening; "07:00" isn't
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


# Spoken forms put the way the readers read them (a corpus of 522 student rules, 26 Oct, found 71 read wrongly, most
# from these): typos and contractions, negations said other ways, "done by" as a limit, hours said without am or pm.
WORD_HOURS = {w: n for n, w in enumerate("one two three four five six seven eight nine ten eleven twelve".split(), 1)}
HOUR = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"


def night_time(said: str) -> str:
    """A bedtime said without am or pm: 12:30 and 1 are after midnight, 11 is the evening."""
    m = re.fullmatch(r"(\d{1,2})(:\d\d)?", said.strip())
    if m and (int(m[1]) == 12 or int(m[1]) < 6):
        return f"{said.strip()}am"
    return said


def after_hour(said: str) -> str:
    """A time work ends after, said without am or pm: 7 to 11 are the evening's ("no work after 10" is 10pm)."""
    said = said.strip()
    return f"{said}pm" if re.fullmatch(r"(?:7|8|9|10|11)(?::\d\d)?", said) else said


def before_hour(said: str) -> str:
    """A time work starts after, said without am or pm: 5 to 11 are the morning's ("no work before 9" is 9am)."""
    said = said.strip()
    return f"{said}am" if re.fullmatch(r"(?:5|6|7|8|9|10|11)(?::\d\d)?", said) else said


def pm(said: str) -> str:
    """An hour of the afternoon or evening said bare: "3" in "between 3 and 4 in the afternoon"."""
    said = said.strip()
    return said if re.search(r"am|pm|noon|midnight", said) else f"{said}pm"


def hour_of(word: str) -> int:
    return int(word) if word.isdecimal() else WORD_HOURS[word]


def through(m: re.Match[str]) -> str:
    """`mon-fri`, `tues through thurs`: every day from the first to the last, listed."""
    first, last = days_of(m[1]), days_of(m[2])
    if not first or not last:
        return m[0]
    i, j = DAYS.index(first[0]), DAYS.index(last[0])
    return ", ".join(DAYS[(i + k) % 7] for k in range((j - i) % 7 + 1))


# Ways of saying it the readers don't read, put in the ways they do (27 Oct: each went to Claude): typos and shorthand,
# 10.30pm and 2230, half past ten, a range as 5-7pm, days as mon-fri or sat/sun, "no later than", "onwards",
# "sundays off", "weekdays only", finishing so many hours or weeks before, a part of a day free.
EARLY_SAID = (
    # Shorthand for days: wknds, M/W/F, T/Th.
    (r"\bwk ?e?nds?\b", "weekends"),
    (r"\bwk ?days?\b", "weekdays"),
    (r"\b(?:m/w/f|mwf|m-w-f)\b", "mon, wed and fri"),
    (r"\b(?:t/th|tth|tu/th|t/r|tr)\b", "tue and thu"),
    (r"\b(?:m/w|mw)\b", "mon and wed"),
    (r"\bduring the week\b", "on weekdays"),
    (r"\s*\((?![^)]*\d)[a-z' ]{1,25}\)", " "),  # "(trivia)"; "(with 1 day of buffer)" says something
    # The days first ("on fridays no more than 4 hours", "on fridays I stop at 6pm"): put last, where readers look.
    (rf"^ ?on {DAY_WORDS},? (.+?) ?$", r" \2 on \1 "),
    # Work by other names: grinding, school stuff, wrapping up, locking in; the noun after "don't touch / don't do".
    (r"\bgrind (?=on )", "push "),
    (r"\block(?:ed|ing)? in (?=on )", "push "),
    (r"\b(?:i )?(?:don't|do not|never) (?:touch|do) ", "no "),
    (r"\b(?:i )?get nothing done (after|before|past)\b", r"no work \1"),
    (r"\bno more work\b", "no work"),
    (r"\b(?:i )?stop (?:at|by) (?=\d|noon|midnight)", "no work after "),
    (
        r"\b(?:grinding|lock(?:ed|ing)? in|wrap(?:ping)? up|be productive|get (?:stuff|things|work) done"
        r"|studyin|studyng|school ?(?:stuff|work)|(?<!grad )(?<!high )(?<!med )(?<!law )(?<!after )(?<!before )"
        r"school(?! ?nights)|more work"
        r"|work hours|scheduling"
        r"|schedule (?:stuff|things|anything|work))\b",
        "work",
    ),
    # "readings: max 90 min daily", "CS 3110 assignments: finish 2 days ahead".
    (
        r"^ ?([a-z0-9 ]+?): ?(max(?:imum)?|at most|no more than|up to|under|less than) (\d+(?:\.\d+)?) ?"
        r"(h|hrs?|hours?|m|mins?|minutes?)\b",
        r" \2 \3 \4 of \1",
    ),
    (
        r"^ ?([a-z0-9 ]+?): ?finish (a|one|\d+) (days?|hours?|weeks?) (?:ahead|early|before)\b",
        r" finish \1 \2 \3 early",
    ),
    # "as close to the prelim as I can"; "flashcards for the spanish quiz as close to it as possible".
    (r"\bas (?:i|we) (?:can|could)\b", "as possible"),
    (
        r"\b(?:for|of) (?:the |my )?([a-z0-9 ]+?) as close to (?:it|them) as possible",
        r" as close to the \1 as possible",
    ),
    # 24h times in a range: "0900-1700".
    (r"\b([01]\d|2[0-3])([0-5]\d) ?(?:-|–) ?([01]\d|2[0-3])([0-5]\d)\b", r"\1:\2 - \3:\4"),
    (r"\baftr\b", "after"),
    (
        rf"^ ?{DAY_WORDS}(?: (?:mornings?|afternoons?|evenings?|nights?))?,? ((?:i )?(?:stop|no work|nothing) .+?) ?$",
        r" \2 on \1 ",  # DAY_WORDS is group 1 here
    ),
    (r"\b(?:b4|befor|bfore)\b", "before"),
    (r"\btill?\b", "until"),
    (r"\b(\d{1,2})\.(\d\d)(?=\s*(?:am|pm)?\b)", r"\1:\2"),
    (r"\b(after|before|by|past|until|from|at|to|and) ([01]\d|2[0-3])([0-5]\d)\b", r"\1 \2:\3"),
    (rf"\bhalf past {HOUR}\b", lambda m: f"{hour_of(m[1])}:30"),
    (rf"\b(?:a )?quarter past {HOUR}\b", lambda m: f"{hour_of(m[1])}:15"),
    (rf"\b(?:a )?quarter to {HOUR}\b", lambda m: f"{(hour_of(m[1]) - 2) % 12 + 1}:45"),
    (r"\b(?:hard|strict|firm|soft) rule\s*:?\s*|,?\s*no exceptions\b", " "),
    (r",\s*except\b", " except"),
    (r"\bthe latest i(?:'ll| will| would)? work is\b", "no work after"),
    (r"\b(?:no work|work no|no studying) later than\b|\bstop (?:work|working|studying) at\b", "no work after"),
    (r"\b(?:start|begin) (?:my day|the day|my work|work|working|studying)(?: at| from)\b", "no work before"),
    (r"\b(?:i )?(?:can't|cannot|can not|dont|don't|do not) (?:work|study)\b", "no work"),
    (rf"\b(?:from )?{TIME} onwards?\b", r"after \1"),
    (rf"\b(?:from )?{TIME} ?(?:-|–) ?{TIME}(?=\s)", r"between \1 and \2"),
    (rf"\b({DAY}) ?(?:-|–|through|thru|to|until) ?({DAY})\b", through),
    (rf"\b({DAY})/({DAY})\b", r"\1 and \2"),
    (r"\bthe weekend\b", "weekends"),
    (
        r"\b(after|before|by|until|past) (\d{1,2}(?::\d\d)?) (?:at night|in the evening|tonight)\b",
        lambda m: f"{m[1]} {m[2]}" + ("am" if m[2].split(":")[0] == "12" else "pm"),  # 12:30 at night is 00:30
    ),
    (r"\b(after|before|by|until|past) (\d{1,2}(?::\d\d)?) (?:in the morning)\b", r"\1 \2am"),
    (r"\bin the (?:morning|afternoon|evening|night) (before|after|until|past) ", r"\1 "),
    (r"\b(?:at|late at|late) night\b|\blate nights\b", "in the night"),
    (r"\b(no work|work) (mornings|afternoons|evenings|nights)\b", r"\1 in the \2"),
    (
        rf"\b(?:take )?({DAY_WORDS}) (?:off|are (?:my )?(?:rest|off|free) days?"
        r"|is (?:my )?(?:day off|rest day|off day|free day)|are (?:my )?days? off"
        r"|are for (?:rest|resting|fun|chilling))\b",
        r"no work on \1",
    ),
    (rf"\b(?:a )?(?:free|rest|off) day (?:every|on) ({DAY_WORDS})\b", r"no work on \1"),
    (r"^ ?(?:work )?(weekdays|weekends) only\b", r" work only on \1"),
    (rf"\bkeep ([a-z0-9 ]+?) to ({DAY_WORDS})\b", r"\1 only on \2"),
    (rf"\b(no work|work only|work) ({DAY_WORDS})(?= |$)", r"\1 on \2"),
    (
        rf"^ ?(?:i(?:'d| would)? (?:like|love|want)(?: to)? |i wanna )?(?:have |keep )?({DAY_WORDS}) "
        r"?(mornings?|afternoons?|evenings?|nights?)? (?:free|clear)\b",
        r" keep \1 \3 free",  # DAY_WORDS is a group of its own: \2
    ),
    (
        r"\b(?:get|have|complete|submit|turn in|hand in|do) ([a-z0-9 ]+?) "
        r"(?:done |in |submitted |finished |completed )?"
        r"(a|one|\d+(?:\.\d+)?) (days?|hours?|weeks?) "
        r"(?:before (?:the deadline|deadlines?|they're due|it's due|due)|early|ahead)\b",
        r"finish \1 \2 \3 early",
    ),
    (
        r"\b(?:finish|get|have|complete|submit) ([a-z0-9 ]+?) (?:done )?(?:by )?the (?:day|night) before"
        r"(?: (?:it's|they're) due| the deadline)?\b",
        r"finish \1 1 day early",
    ),
    # The whole sentence: "lab reports a day early" (not "… as possible but finish a day early").
    (
        r"^ ?(?! ?finish\b)((?:(?!\b(?:but|and|or)\b)[a-z0-9 ])+?) (a|one|\d+) (days?|weeks?) early ?$",
        r" finish \1 \2 \3 early ",
    ),
)
# After the old ones, which make "don't schedule anything" into "no work": a day straight after it is "on" that day.
LATE_SAID = (
    (r"\bon on\b", "on"),
    (rf"^ ?((?:(?!\bon\b)[a-z0-9 ])+?) only {DAY_WORDS} ?$", r" \1 only on \2 "),
    (
        rf"^ ?([a-z0-9 ]+?):\s*at most {SPAN_OF}(.*)$",
        lambda m: (
            f" at most {m[2]} {m[3]}{m[4]} on {m[1]} " if days_of(m[1]) else f" at most {m[2]} {m[3]} of {m[1]}{m[4]} "
        ),
    ),
    (rf"\b(at most|max(?:imum)?|no more than|up to) {SPAN_OF} {DAY_WORDS}(?= |$)", r"\1 \2 \3 a day on \4"),
    (rf"^ ?((?:(?!\bon\b)[a-z0-9 ])+?) {DAY_WORDS} only ?$", r" \1 only on \2 "),  # "readings tues-thurs only"
    (rf"\b(no work|work only|work) {DAY_WORDS}(?= |$)", r"\1 on \2"),
    (rf"(?<![\d:]){TIME} {DAY_WORDS}(?= |$)", r"\1 on \2"),
    # "groceries on sunday afternoons": that part of those days (not all of Sunday); "no work on…" is kept free below.
    (
        rf"^ (?!no |never |don't |nothing )([a-z0-9 ]+?) on {DAY_WORDS} (morning|afternoon|evening|night)s?\b",
        r" \1 in the \3 on \2",
    ),
)
SAID_AS = (
    (r"\b(?:wrok|wokr|wrk)\b", "work"),
    (r"\bnoo+\b", "no"),
    (r"\bdont\b", "don't"),
    (r"\bi'(?:ll|d|m|ve)\b", "i"),
    (r"\b(?:i )?(?:would )?rather not\b", "no"),
    # Asleep by a time means work done by it: "sleep before 1am", "bed by 11" (your bedtime itself is a setting).
    (
        r"^ ?(?:always |must |i |please |ideally |really |strongly |definitely |try to |want to |like to |to )*"
        r"(?:go to |be in |in |get to |be )?(?:bed|sleep|asleep|lights out)(?: by| before| at)? "
        r"(noon|midnight|\d{1,2}(?::\d\d)?\s*(?:am|pm)?)\b(?! ?(?:hours?|hrs?|h\b))",
        lambda m: f" no work after {night_time(m[1])}",
    ),
    (r"\bhalf an hour\b", "30 minutes"),
    (r"\ba quarter (?:of an )?hour\b", "15 minutes"),
    (r"\b(?:an|one) hour\b", "1 hour"),
    (r"\bweekend work\b", "work on weekends"),
    (r"\b(?:school ?work|any ?thing)\b", "work"),
    (r"\b(?:start|starting|begin|beginning) (work|working|studying)\b", r"\1"),
    (r"\bmust have (breakfast|lunch|dinner|supper)\b", r"must \1"),
    (r"\bp\.?m\.?(?=\s)", "pm"),
    (r"\ba\.?m\.?(?=\s)", "am"),
    (r"\b(?:i )?(?:don't|do not) (?:want|like|wanna) to\b", "no"),
    (r"\b(?:never ever|under no circumstances)\b", "never"),
    (r"\b(?:never|don't|do not) (?:schedule|plan|put) (?:anything|any work|work)\b", "no work"),
    (r"\b(?:don't|do not) (?:schedule|plan|put)\b", "no"),
    (r"\bnothing (?:scheduled|planned)\b", "no work"),
    (r"^\s*nothing\b", " no work"),
    (r"\bavoid (?:working|work)\b", "no work"),
    (r"\b(?:stop working|finish (?:work|working|everything)|be done|done) (?:by|before)\b", "no work after"),
    (r"\b(?:school ?nights|weeknights)\b", "sun, mon, tue, wed and thu"),
    (r"\bonly (work|study|studying|working)\b", r"\1 only"),
    (r"\b(?:if possible|preferably|at all costs)\b", " "),
)
# Said the way people type before anything else is read (27 Oct: "the barebones rules parsing [should be] much more
# comprehensive instead of having to ask claude for everything"): shorthand and missing apostrophes, filler that says
# nothing about the rule ("tryna", "if I can", "unless it's an emergency": a preference, which is the default), and
# the reason tacked on the end ("…, my brain is fried", "… bc of practice"). What's left is the rule.
REASON = (
    # A reason joined by its own word may follow a space ("no CS after 11 bc my brain is fried"); one that's a sentence
    # of its own follows a comma or a dash ("…, too tired").
    r"(?:\s(?:because|becuase|becasue|bc|b/c|cuz|cause|due to)\b"
    r"|\s(?:since|because) i\b"
    r"|\s?[,;]\s*(?:since (?:i|my|it|that|there|the)|as i'?m)\b"
    r"|\s?(?:[,;]| -)\s*(?:that'?s (?:lunch|dinner|breakfast|it|enough|my (?!ceiling|limit|max|cap|most)\w+|when \w+)\b"
    r"|my (?:brain|body|head) (?:is|gets|goes)\b|too (?:tired|exhausted|sleepy|drained|hectic|busy|packed|crazy|full"
    r"|much going on)\b|i'?m (?:too )?(?:tired|fried|exhausted|dead|useless|wiped|done|cooked)\b"
    r"|i (?:have|work|get|got) (?!to\b)|even (?:in|during|on|when)\b|i (?:can't|cant) (?:focus|think|function)\b"
    r"|period\b|no excuses\b|seriously\b|for real\b|i'?m\b)"
    r"|\s?[,;]\s*(?:i need (?:to )?(?:sleep|rest|my sleep|my rest|a break|to recharge|downtime)|i sleep\b|i eat\b"
    r"|i go home\b|i commute\b|i think better|i focus better|i work better|i'?m part time|then i'?m done\b"
    r"|that'?s (?:family|my|me|friend|church|gym|rest) time\b"
    r"|my brain (?:melts|dies|hurts|is mush|turns off|shuts off|is fried))"
    r"|\swhen it'?s (?:quiet|calm)\b"
    r"|\s?,?\s*while (?:it'?s|its|it is) (?:still )?fresh\b|\s?,?\s*based on [a-z ]+$"
    r"|\s?,?\s*(?:when|since|it'?s when) (?:my brain|i'?m (?:sharpest|most focused|freshest|awake|at my best)"
    r"|i focus best|i think best)\b"
    r"|\sso (?:that )?(?:my \w+ can|i can|we can|i have time|there'?s time)\b)"
    r".*$"
)
PLAIN = (
    # 8 Nov corpus: a title in quotes is the title ("\"Yoga\" is skippable"); "id like", "ill skip" are I'd, I'll;
    # "knitting circle: only if ahead" names what's only if ahead.
    (r"[\"“”]", " "),
    (
        r"\bid (?=(?:(?:really|so|truly|definitely|honestly|also|just|much) )*"
        r"(?:like|love|rather|prefer|want|never)\b)",
        "i'd ",
    ),
    (r"\bill (?=skip|go|do|take|drop|miss|ditch|work|study|finish)", "i'll "),
    (r"(?<=[a-z]): (?=only (?:if|when)\b)", " "),
    (r"\b(?:wkdays?|wk days?)\b", "weekdays"),
    (r"\bas (?:u|you|i|we) can\b", "as possible"),
    (
        r"^ ?i (?:work|nurse|have|do|am|teach|coach|commute|drive|bartend)\b"
        r"(?:(?!morning|evening|afternoon)[a-z ])*? so"
        r" (?=no |nothing |don't |never |keep |only )",
        " ",
    ),
    (r"\bwrite up (?=[a-z])", "write "),
    (r"\bdef\b(?= (?:no|not|never|want|need|don't|dont)\b)", "definitely"),
    (r"\b(do|does|is|are|was|should|would|could|ca|wo|did|have|has)nt\b", r"\1n't"),
    (r"\bcant\b", "can't"),
    (r"\bwont\b", "won't"),
    (r"\bim\b", "i'm"),
    (r"\bive\b", "i've"),
    (r"\bthats\b", "that's"),
    (r"\btheres\b", "there's"),
    (r"\bw/o\b", "without"),
    (r"\bb/w\b|\bbtwn\b|\bbtw(?= \d)", "between"),
    (r"(?<![a-z/])w/ ?(?![a-z]/)", "with "),  # not M/W/F
    (r"\b(?:pls|plz|plez)\b", "please"),
    (r"\bmidnite\b", "midnight"),
    (r"\b(\d{1,2}(?::\d\d)?)(a|p)\b", lambda m: f"{m[1]}{m[2]}m"),
    (r"\bthr?usday", "thursday"),
    (r"\bwe(?:n|dn)sday", "wednesday"),
    (r"\btuseday", "tuesday"),
    (r"\bm w f\b", "mon, wed and fri"),
    (r"\bt th\b", "tue and thu"),
    (r"\.\s*(?:ever|never|nothing|period|seriously)\.?\s*$", " "),
    (r"\b(?:all three|all 3|every|each) meals?\b", "meals"),
    (r"\b(?:anything |stuff )?school[- ]related(?: stuff)?\b", "work"),
    (r"\bas (?:i|we) can get\b", "as possible"),
    (r"\b(whether|if) i even\b", r"\1 i"),
    (r"\b(?:a bit|a little(?! work)|from my tracking|from what i log|from my logs)\b", " "),
    (
        r"^ ?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?: (thirty|fifteen|forty five))?"
        r" (?=a\.?m|p\.?m)",
        lambda m: f" {WORD_HOURS[m[1]]}" + {"thirty": ":30", "fifteen": ":15", "forty five": ":45"}.get(m[2] or "", ""),
    ),
    (r"\b(?:homwork|homewrk|hmwk|homewok|homeowrk)\b", "homework"),
    (r"\b(?:studdying|studing|stuyding|sutdying)\b", "studying"),
    (r"\?", " "),
    (r"\bas late as (?:they|it|that) can (?:go|be)\b", "as late as possible"),
    (r"\b(?:an? )?hour and a half\b", "1.5 hours"),
    (r"\b(?:a|one) day and a half\b", "1.5 days"),
    (r"\b(?:a )?half (?:a )?day\b(?! buffer| of buffer)", "0.5 day"),
    (
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)(?: and a half| ?½)"
        r" (hours?|hrs?|days?|weeks?)\b",
        lambda m: f"{WORD_HOURS.get(m[1], m[1])}.5 {m[2]}",
    ),
    (
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)[ -](hours?|hrs?|minutes?|mins?|days?"
        r"|weeks?|h|hr)\b",
        lambda m: f"{WORD_HOURS[m[1]]} {m[2]}",
    ),
    (
        r"\b(after|before|by|at|until|till|past|from|to|and|hits|thru|through) (one|two|three|four|five|six|seven|eight"
        r"|nine|ten|eleven|twelve)(?: (thirty|fifteen|forty[- ]five|o'?clock))?\b(?! (?:hours?|hrs?|days?|weeks?"
        r"|minutes?|mins?|of|and a half))",
        lambda m: (
            f"{m[1]} {WORD_HOURS[m[2]]}"
            + {"thirty": ":30", "fifteen": ":15", "forty-five": ":45", "forty five": ":45"}.get(m[3] or "", "")
        ),
    ),
    # 8 Nov: "I really would love to have lunch after noon" is "I want to have lunch after noon", said more strongly
    # (the strength is read first): any order of I, I'd, would, really, so, truly with like, want, prefer or love.
    (
        r"^ ?(?:i(?:'d)?(?: (?:would|really|so|truly|definitely|also|just|honestly|much))*"
        r" (?:like|want|prefer|love|wish)(?: it if| to)?|i wanna|i need to)\s+(?=[a-z])",
        " ",
    ),
    (r"\bright up (?:until|till)\b", "right up to"),
    (r"\bpre-?(?=\d)", "before "),
    (r"\bmake sure (?:that )?(?=i'?m\b|im\b|to\b|it\b|there\b|nothing\b)", ""),
    (r",?\s*(?:no matter what|regardless|whatever happens)\b", " "),
    (r"\bmust[- ]haves\b|\ba must[- ]have\b", "non-negotiable"),
    (r"\bzero (?=work|studying|homework|school|hw|late|overdue)", "no "),
    (r"\b(?:m-th|m-thu|mon-thu|m-thurs)\b", "mon, tue, wed and thu"),
    (r"\bhalf an hour\b", "30 minutes"),
    (r"\b(?:an|one) hour\b", "1 hour"),
    (r"\bpost-?(?=\d)", "after "),
    (r"\b(?:m-f|mon-fri|mon thru fri|monday-friday)\b", "weekdays"),
    (rf"\b({DAY}) ?(?:-|–|through|thru|to|until) ?({DAY})\b", through),
    (r"\bevery day (?:but|except) ", "except "),
    (
        r"\b(?:besides|other than|apart from|aside from|excluding)(?= (?:on )?(?:mon|tue|wed|thu|fri|sat|sun|week))",
        "except",
    ),
    (r"\b(?:absolutely|literally|seriously)\s+(?=nothing\b|no\b|never\b)", ""),
    (r"\b(?:m/w/f|mwf|m-w-f)\b", "mon, wed and fri"),
    (r"\b(?:t/th|tth|tu/th|t/r|tr)\b", "tue and thu"),
    (r"\b(?:m/w|mw)\b", "mon and wed"),
    (r"\s*,\s*(?:always|please|pls|thanks|ok|okay)\s*$", " "),
    (
        r",?\s*even (?:during|in|on|for|when) (?:finals|exams?|midterms|prelims|crunch(?: time)?|busy weeks?)"
        r"(?: week| season| time)?\b",
        " ",
    ),
    (r"\bstrict(?:ly)?\b(?! rule)", " "),  # how strongly: read before this
    # "brain-heavy", "low-effort": one word or two, the same; but "mon-thu" is a run of days and "m-f" two letters.
    (
        r"\b([a-z]+)-([a-z]+)\b",
        lambda m: (
            m[0]
            if (re.fullmatch(DAY, m[1]) and re.fullmatch(DAY, m[2])) or len(m[1]) == 1 or len(m[2]) == 1
            else f"{m[1]} {m[2]}"
        ),
    ),
    (r"\b(?:b4|befor|bfore)\b", "before"),
    (r"\bnite\b", "night"),
    (r"\b(?:hrs?|hours?)\.", "hours"),
    (r"\bmins?\.", "minutes"),
    (r"(?<=\s)r(?= (?:for|my|off|free|rest)\b)", "are"),
    (r"(?<=\s)u(?=\s)", "you"),
    (r"\b(?:wknd|wkend)s?\b", "weekends"),
    (r"\bthe a\.?m\.?(?=\s|$)", "the morning"),
    (r"\bthe p\.?m\.?(?=\s|$)", "the afternoon"),
    (r"\b(?:the )?(?:afternoon|post[- ]?lunch) slump\b", "the afternoon"),
    # Filler: what says how much you mean it (a preference is the default) or nothing at all.
    (
        r"\b(?:tryna|trying to|try to|try and|aim to|aiming to|my goal is to|i(?:'d| would) love to|lowkey|highkey|ngl"
        r"|honestly|tbh|basically|literally|in general|as a rule|as much as possible|when(?:ever)? possible"
        r"|where possible|if at all possible|if (?:i|you|we) can(?: help it)?|if (?:it'?s )?possible|plan accordingly"
        r"|when(?:ever)? (?:i|you) can|when it works"
        r"|thanks|thx|ty|kinda|sorta|pretty much|just(?! in time| before| after)|personally|realistically|ideally"
        r"|actually"
        r"|on myself|on me(?= on))\b",
        " ",
    ),
    (
        r",?\s*unless (?:it'?s|there'?s|it is|there is) (?:an? )?(?:emergency|urgent|crunch|deadline|big deadline)\b"
        r"|,?\s*unless (?:i |you )?(?:really |absolutely )?(?:have to|need to|must|gotta|has to)\b"
        r"|,?\s*unless (?:absolutely |really )?(?:necessary|needed|unavoidable)\b",
        " ",
    ),
    (r"\blike (?=\d|an? (?:hour|day)|half)", ""),  # "like 4 hours"
    (REASON, " "),
)
EVENING_HOUR = r"\b(after|past|by|until|till)\s+(7|8|9|10|11)(:\d\d)?(?!\s*(?:am|pm|\d|:))\b"
WHEN_WORD = r"(?:before|after|by|past|until|till)"
ITEMISH = (
    r"^ ?(?:add |schedule |put |i have |my |a |an )?[a-z0-9 ]*?\b(?:office hours?|practice|rehearsal|shift|volunteer"
    r"|meeting|lesson|lecture|seminar|recitation|appointment|lunch break|game|match|service|church|mass|club"
    r"|ta hours|tutoring|work shift|job|study group|lab|dentist|doctor|therapy|haircut|interview|laundry|party"
    r"|concert|flight|study session|session with|with [a-z]+ (?:every|on)|work ?study|mailroom|shift at)\b"
)
ITEM_WHEN = (
    rf"\bevery (?:{DAY}|day|night|week|morning|evening)|{TIME} ?(?:-|–) ?{TIME}|\bfrom {TIME} to {TIME}|\bat \d"
    r"|\bis always\b|^ ?add\b"
)
RULE_WORDS = (
    r"\b(?:no|never|don't|not|avoid|optional|skip|before|after|around|only|ahead|free|between|must|end|stop|if"
    r"|when|unless|done|going)\b"
)
CAP_WORD = r"(?:at most|no more than|not more than|max(?:imum)?(?: of)?|up to|less than|under)"
TWO_RULES = (
    r"\b(?:and|but|;)\s+(?:no|never|don't|nothing|always)\b|, (?:no|never|don't)\b"
    # Two times, each with its own word: "no work before 9 or after 10", "lunch before 1 and dinner before 7".
    rf"|\b{WHEN_WORD} {TIME}\b.*\b(?:and|or|but)\b.*\b{WHEN_WORD} {TIME}"
    # "gym is optional but climbing club is mandatory"; "at most 6 hours a day and 4 on weekends".
    # A second clause with its own verb ("…, and let Friday figure out breakfast"); "but finish a day early" is a
    # buffer on the first.
    r"|\band\s+(?:let|keep|make|plan|put|finish|prioritize|leave|give)\b|\b(?:but|;)\s+(?:let|keep|make|plan|put"
    r"|prioritize|leave|give)\b|\band (?:none|nothing)\b"
    r"|,\s*and\s+\d|\band take a\b|\bbut\b.*\b(?:isn't|aren't)\b"
    rf"|\b{WHEN_WORD} {TIME}\b[^,]*,\s*{WHEN_WORD} {TIME}"
    r"|\b(?:a|one|\d+) days? (?:early|ahead)\b.*\band\b.*\b(?:a|one|\d+) days? (?:early|ahead)\b"
    rf"|\bbut\b.*\b(?:is|are)\b|\b{CAP_WORD} \d+(?:\.\d+)? ?(?:h|hrs?|hours?)\b.*\band \d"
    rf"|\d[^,;]*[,;] ?(?:and )?{DAY_WORDS}\b[^,;]*\d"
    r"|\b\d+(?:\.\d+)? ?(?:hours?|hrs?|h)?\s*of (?:it|that|those|them)\b"
    rf"|{TIME} ?(?:-|–) ?{TIME}\b.*\band\b.*{TIME} ?(?:-|–) ?{TIME}"
    r"|\bonly\b.*\b(?:and|but)\b.*\bonly\b"  # "light work only in the evening and hard stuff only before lunch"
)
# What no reader reads, so a rule would leave it out: a time of the term, a condition on your week, an exception that
# isn't a day, an event as an end ("work after class until dinner"). Claude reads these (27 Oct: each was dropped).
UNREAD_QUALIFIER = (
    r"\b(?:during|in|over) (?:midterms|finals|exams?|prelims?|exam week|finals week|reading week|break|the break)\b"
    r"|\bwhen i (?:have|'ve got|got)\b(?! (?:breakfast|brunch|lunch|dinner|supper|meals?|a lot|lots|too much|so much"
    r"|deadlines|work|stuff|things due|a deadline)\b)(?![a-z0-9 ]+ (?:the )?(?:next|following) (?:day|morning))"
    r"|\b(?:that|this|next) week\b"
    r"|\b(?:tmrw|tmr|tomorrow|tonight|today|this weekend|this (?:mon|tue|wed|thu|fri|sat|sun)[a-z]*)\b|\bnothing but\b"
    r"|\bthe week before (?:the |my )?[a-z]+"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]* \d{1,2}(?:st|nd|rd|th)?\b|\b\d{1,2}/\d{1,2}\b"
    r"|\b(?:on|in|during) weeks? (?:with|when|that have)\b|\bif it (?:rains|snows|'s raining|'s cold|'s nice)\b"
    r"|\bweather\b|\b(?:midterm|exam|finals?|prelim) (?:season|week|period|time)\b|\b(?:bulk|most|majority) of "
    r"(?:my |the )?work\b|\bexcept (?!(?:on |for )?(?:mon|tue|wed|thu|fri|sat|sun|week|when|if|before|after|during"
    r"|around)\w*)[a-z]+"
    r"|\bexcept (?:before|after|during|when|if|for|on exam|around)\b"
    rf"|\buntil (?!{TIME}|noon|midnight|the morning|morning)[a-z]+"
    # 8 Nov corpus: rules Friday has no kind for, which the readers took for others ("start working by 8:30" read as
    # stopping by 8:30pm; "after 2 hrs of studying i need a 20 min break" as work after 2pm)
    r"|\bstart(?:ing)?(?: (?:work|working|studying|my day|the day))? by\b|\bbe (?:working|at my desk|started) by\b"
    r"|\b\d+ ?(?:min|mins|minutes?|m|hours?|hrs?|h) breaks?\b"
    r"|\bbreaks? (?:every (?!day|night|morning|afternoon|evening)|after)\b"
    r"|\bafter (?:\d+(?:\.\d+)?|an?) ?(?:h|hrs?|hours?|min|mins|minutes?) of\b|\bevery (?:\d+ )?(?:hour|hr)\b"
    r"|\bonly after (?:i'?m|i am) done with\b"
    # "i nurse 7a-7p on tue wed thu so no tasks those days b4 8pm": the rule leans on times said for something else
    r"|^ ?i (?:work|nurse|have|teach|coach|commute|drive|bartend)\b[^,]*\d[^,]*? so\b"
    r"|^ ?(?:delete|remove|cancel|reschedule|move) (?:the|my|a|an|this|that)\b"  # a change to make once
)
# A limit for each of several days: "mondays 8h max, fridays 4h max" is the daily_cap setting (Claude's).
LIMIT_PER_DAY = rf"\b\d+(?:\.\d+)? ?(?:h|hrs?|hours?)\b[^;]*?,\s*(?:{DAY}[ ,]*)+(?:and )?(?:max |at most |cap )?\d"
NOT_WORK = (
    r"\bbedtime\b|\basleep from\b|^ ?up (?:by|at) \d"
    r"|^ ?(?:always |never |no |must |i )*(?:go to |be in |in |get to )?(?:bed|sleep"
    r"|sleep in"
    r"|wake up|get up|eating(?! (?:breakfast|brunch|lunch|dinner|supper))|eat(?! (?:breakfast|brunch|lunch|dinner"
    r"|supper))"
    r"|snacking)\b|^ ?(?:i )?(?:need|give me|let me)\b(?! (?:an? |\d))|\btake\b.*\boff\b|\b(?:is|are|it's) (?:fine|ok"
    r"|okay|allowed)\b(?!.*\b(?:deadlines?|due)\b)"
)


def spoken(t: str) -> str | None:
    """The sentence in the readers' words, or None when it should go to Claude: two rules in one sentence, or a
    rule about your sleep or eating rather than your work (`bed by 11` is the sleep setting)."""
    for pattern, put in PLAIN:
        t = re.sub(pattern, put, t)
    t = " " + " ".join(t.split()) + " "
    typed = t
    if re.search(ITEMISH, typed) and re.search(ITEM_WHEN, typed) and not re.search(RULE_WORDS, typed):
        return None  # an event to add, with its times: Claude adds it
    if re.search(UNREAD_QUALIFIER, typed) or re.search(LIMIT_PER_DAY, typed):
        return None
    t = night_before_said(t)
    for pattern, put in WIDER:
        t = " " + " ".join(re.sub(pattern, put, t).split()) + " "
    for pattern, put in (*EARLY_SAID, *SAID_AS, *LATE_SAID):
        t = re.sub(pattern, put, t)
    if not re.search(r"\b(?:breakfast|brunch|lunch|morning)s?\b", t):  # "after 9" in the evening, unless it's lunch
        t = re.sub(EVENING_HOUR, lambda m: f"{m[1]} {m[2]}{m[3] or ''}pm", t)
    if re.search(r"\b(?:dinner|supper|evening|tonight)\b", t):
        t = re.sub(
            r"\b(before)\s+(5|6|7|8|9|10|11)(:\d\d)?(?!\s*(?:am|pm|\d|:))\b",
            lambda m: f"{m[1]} {m[2]}{m[3] or ''}pm",
            t,
        )
    if m := re.search(rf"(?:\bon {DAY_WORDS} )?\bexcept (?:on |for )?{DAY_WORDS}", t):
        base = days_of(m[1]) if m[1] else None
        t = t.replace(m[0], " EXCEPT ")
        if base is None and (on := re.search(rf"\bon {DAY_WORDS}", t)):  # "on weeknights …, except thursdays"
            base = days_of(on[1])
            t = t.replace(on[0], " ")
        left = [d for d in (base or DAYS) if d not in (days_of(m[2]) or DAYS)]
        t = t.replace(" EXCEPT ", " on " + ", ".join(left) + " " if left else " ")
    sleep_amount = re.search(SLEEP_AMOUNT, t) is not None  # "sleep at least 7 hours" is a rule, not the setting
    if re.search(TWO_RULES, t) or (re.search(NOT_WORK, t) and not sleep_amount) or re.search(UNREAD_QUALIFIER, t):
        return None  # Claude splits two rules, reads what no reader does, and knows the sleep and meal settings
    # "no work on sunday mornings", "never work on tues and thurs evenings": that part of those days kept free.
    if m := re.search(
        rf"\b(?:no work|nothing|never work|don't work|do not work|never study|no studying) on {DAY_WORDS} "
        r"(mornings?|afternoons?|evenings?|nights?)\b",
        t,
    ):
        t = t.replace(m[0], f"keep {m[1]} {m[2]} free")
    return " " + " ".join(t.split()) + " "


# What a subject never is (27 Oct, a corpus of 844 wordings: "make sure im off the clock by 8pm" was a rule about a task
# called "make sure off clock"): words of the sentence around the rule, not a kind of work. A reading whose subject
# has one goes to Claude rather than make a rule about nothing.
JUNK_SUBJECT = (
    r"\b(?:be|done|make|sure|keep|give|me|myself|it|is|are|am|was|plan|planning|schedule|scheduled|start|starting"
    r"|try|window|inside|out|off|clock|every|each|zero|fine|any|wrap|wrapped|that|needs?|want|let|get|gets|put|do"
    r"|does|doing|go|going|so|than|can|nothing|finished|ready|submitted|completed|right|immediately|cram"
    r"|sacrifice|workload|hours?|hrs?|working|limit|cap|max|okay|ok|allowed|whatever|things that|stuff that"
    r"|burn|tonight|today|tomorrow|has|have|had|goes|land|lands|should|would|could|must|happen|happens|somewhere"
    r"|anywhere|book|send|open|touch|fit|end|ends|function|zone|table|total|first|nightly|nada|related|least|for"
    r"|from|with|to|at|by|then|will|may|might|did|got|makes|made|takes|puts|gives|keeps|lets|use|uses|wants"
    r"|tries|starts|stop|stops|plans|schedules|runs|i|you|we|they|he|she|textbook|calendar|plate|refuse|gimme"
    r"|productive"
    r"|last|task|save|mornings|evenings|afternoons|nights|weekdays?|weekends?|(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri"
    r"|sat(?:ur)?|sun)(?:day)?s?)\b|:"
)
KNOWN_SUBJECTS = {"work", "deep work", "light work", "undated work", "exam prep", "events", "meals", "pace"}
# Work with no due date, however it's said, read as "undated work" (3 Nov: undated work is placed by rules).
UNDATED = re.compile(
    r"\b(?:(?:work|tasks?|things|stuff|to-?dos?)\s+(?:with\s+no|without(?:\s+an?|\s+any)?)\s+(?:due\s+dates?|deadlines?|dues?)"
    r"|(?:undated|no-?deadline|deadline-?free)(?:\s+(?:work|tasks?|things|stuff|to-?dos?))?)\b",
    re.IGNORECASE,
)


def undated_said(text: str) -> str:
    """The sentence with its ways of saying work with no due date as "undated work"."""
    return UNDATED.sub("undated work", text)


# A clause about your sleep setting is a rule of its own, for telling two rules apart ("…, and wake me at 8").
SETTING_CLAUSE = r"^ ?(?:and )?(?:wake (?:me )?(?:up )?|get up|up|bedtime|bed|in bed|lights out)\b.*\d"


def read(text: str) -> tuple[Reading | None, Strength]:
    """What a sentence asks for, and how strongly; None when the grammar can't read it, or when it says two rules
    (each half a rule of its own, and not the same one: "keep sunday free and go easy on saturday")."""
    text = undated_said(text)
    found, strength = read_one(text)
    if found is None:
        return None, strength
    # A pace says several days at once; a buffer before a due ("but finish a day early") is part of its rule.
    if found.kind != "pace" and not (found.kind == "close" and found.before_min) and two_rules(text, found):
        return None, strength
    return found, strength


def two_rules(text: str, found: Reading) -> bool:
    t = " " + re.sub(r"\s+", " ", text.lower().replace("’", "'").strip().rstrip(".!")) + " "
    parts = [p for p in re.split(r"\s*(?:,|;|\band\b|\bbut\b|&|\bplus\b|\+)\s*", t) if p.strip()]
    days_only = (
        rf"^ ?(?:except |on |every |but |only |besides |other than |apart from |excluding )?(?:on )?{DAY_WORDS}"
        rf"(?: {DAY_PART})? ?$"
    )
    time_only = rf"^ ?(?:after|before|by|until|till|past|from) {TIME} ?$"
    if found.kind == "night_before":  # "no late work the night before a race, done by 8:30": when that night ends
        time_only += (
            rf"|^ ?(?:then )?(?:stop|done|be done|end|no work|nothing|wrap up|finish)\b[a-z ]*? (?:at|by|after|past)"
            rf" {TIME} ?$"
        )
    for i in range(1, len(parts)):
        left, right = " ".join(parts[:i]), " ".join(parts[i:])
        if any(re.search(days_only, x) or re.search(time_only, x) for x in (left, right)):
            continue  # "except thursdays, no work past 11", "lab reports on weekends, after noon": the rule's when
        a, b = read_one(left)[0], read_one(right)[0]
        cut = r"\b(?:by|after|until|till|past|at) \d"  # "stop by 11 the night before": a rule of its own
        night = rf"{cut}.*\b(?:night|day|evening) before\b|\b(?:night|day|evening) before\b.*{cut}"
        both = (a or re.search(SETTING_CLAUSE, left) or re.search(night, left)) and (
            b or re.search(SETTING_CLAUSE, right) or re.search(night, right)
        )
        # The same rule on other days is a second rule ("10-6 on weekdays and 12-4 on weekends"), unless it says
        # the other way round ("i work on weekdays and saturday, never sunday").
        other_days = a and b and a.days and b.days and a.days != b.days and a.rel == b.rel
        if both and (a is None or b is None or (a.kind, a.subject) != (b.kind, b.subject) or other_days):
            return True
    return False


def read_one(text: str) -> tuple[Reading | None, Strength]:
    """One rule's reading, before telling whether the sentence says two."""
    t = " " + re.sub(r"\s+", " ", text.lower().replace("’", "'").strip().rstrip(".!")) + " "
    strength: Strength = "Prefer"
    if re.search(
        r"\b(always|never|must|absolutely|strictly|strict|under no circumstances|hard rule|no exceptions"
        r"|non[- ]?negotiable|strict rule)\b",
        t,
    ):
        strength = "Always"
    elif re.search(r"\b(really|strongly|definitely)\b", t):
        strength = "Strongly"
    said = spoken(t)
    if said is None:
        return None, strength
    t = re.sub(
        r"\b(i(?:'d| would)? (?:really )?(?:prefer|like|want)(?: to)?|please|ideally|always|really|strongly"
        r"|definitely|absolutely|strictly|strict|must|try to|i)\b",
        " ",
        said,
    )
    t = re.sub(r"\s+", " ", t)
    nt = r"\b(?:should|must|can|could|would|wo|ca|does|did|is|are)n't\b"  # "shouldn't run during lectures"
    negated = bool(re.search(rf"\b(no|never|don't|not|avoid)\b|{nt}", t))
    t = re.sub(rf"\b(no|never|don't do|don't|do not|not|avoid)\b|{nt}", " ", t)
    readers = (read_spacing, read_sleep, read_pace, read_meals, read_running, read_fit_gaps, read_around, read_ahead,
               read_optional, read_night_before, read_close, read_cap, read_early, read_free, read_window, read_days,
               read_after, read_deadlines)  # fmt: skip
    # Only these read a condition ("only if I'm ahead", "skip it if there's too much work"); after them, a sentence
    # with one goes to Claude rather than lose it ("only work on sundays if I'm behind" isn't "work on Sundays").
    conditional = {
        read_ahead, read_optional, read_night_before, read_deadlines, read_pace, read_meals, read_running,
    }  # fmt: skip
    t = " " + " ".join(t.split()) + " "
    unsure = bool(re.search(r"\b(?:if|unless|when|whenever|depending)\b", t))
    for parse in readers:
        if unsure and parse not in conditional:
            continue
        found = parse(t, negated)
        if found:
            junk = found.subject not in KNOWN_SUBJECTS and re.search(JUNK_SUBJECT, found.subject)
            if not junk:
                return found, strength
            break  # a reading about words around the rule ("go to the gym"): the kinds' words may still read it
    from friday.core.rule_more import read_more  # the grammar's own words; it reads what's left by their kinds' words

    plain = " " + text.lower().replace("’", "'") + " "
    for pattern, put in PLAIN:  # spelled as the grammar spells it, but not put in its readers' order
        plain = re.sub(pattern, put, plain)
    found = read_more(" " + " ".join(plain.split()) + " ", unsure)
    junk = found and found.subject not in KNOWN_SUBJECTS and re.search(JUNK_SUBJECT, found.subject)
    return (None if junk else found), strength


WORK_WORDS = {"school", "school stuff", "studying", "study", "grinding", "day", "days", "my day", "school work"}
EXAM_PREP = (
    r"^(?:studying|study|prep|preparing|prepping|reviewing|review|revising|revision|cramming|cram) for (?:the |my )?"
    r"(?:exams?|tests?|prelims?|midterms?|finals?)$"
    r"|^(?:exams?|tests?|prelims?|midterms?|finals?) (?:prep|studying|review|reviewing|cramming|revision|revising)$"
)


def subject_of(words: str) -> str:
    # "prefer homework in the afternoon": the strength is read elsewhere, and isn't what the rule is about (3 Nov)
    words = re.sub(r"^ *(?:i )?(?:prefer(?:ably)?|ideally|rather) ", "", words)
    words = re.sub(r"^ *(?:work|anything|stuff|things) (?:for|on) ", "", words)  # "anything for MATH 2940"
    # What's done to it says nothing of what it is: "finish all hw", "submit", "write discussion responses".
    words = re.sub(
        r"^ *(?:(?:finish|finishing|submit|submitting|complete|completing|turn in|hand in|wrap up|write up|writing up"
        r"|work on|write|do) )+",
        " ",
        words,
    )
    s = re.sub(r"\b(eating|having|have|doing|do|my|the|a|an|any|all|of|to|only)\b", " ", words).strip()
    s = " ".join(s.split())
    s = re.sub(r"(?<=\w) (?:sessions?|blocks?)$", "", s)  # "deep focus sessions"
    s = re.sub(r"\b(\w+) \1\b", r"\1", s)  # "work work", from a day said first ("wkdays only work till 5")
    s = re.sub(r" (?:straight away|right away|immediately|asap|first thing)$", "", s)  # when, not what
    if re.fullmatch(EXAM_PREP, s):
        return "exam prep"
    if s in WORK_WORDS or s in ("finish", "submit", "complete", "write", "deadlines", "everything due"):
        return "work"
    bare = re.sub(r" (?:work|stuff|things|tasks)$", "", s)
    if bare != s and s not in DEEP | LIGHT | EVERYTHING and (re.search(r"\d", bare) or " " in bare):
        s = bare  # "CS 3110 work", "hist essay work"; "lab work" stays lab work
    s = (
        "work"
        if s
        in (
            "school work",
            "schoolwork",
            "study",
            "studying",
            "working",
            "anything",
            "uni work",
            "college work",
            "uni stuff",
            "college stuff",
        )
        else s
    )
    if not s or s in EVERYTHING:
        return "work"
    return "deep work" if s in DEEP else "light work" if s in LIGHT else s


PACE_WORDS = {
    **dict.fromkeys(
        (
            "easier",
            "easy",
            "lighter",
            "light",
            "less",
            "relaxed",
            "slower",
            "chill",
            "chiller",
            "chilled",
            "relaxing",
            "mellow",
            "slow",
            "gentle",
            "gentler",
            "calm",
            "calmer",
            "easygoing",
            "easy going",
            "laid back",
            "low key",
        ),
        "Easy",
    ),
    **dict.fromkeys(
        (
            "harder",
            "hard",
            "heavier",
            "heavy",
            "more",
            "push",
            "faster",
            "intense",
            "all out",
            "grind",
            "grinding",
            "full send",
            "all in",
        ),
        "Push",
    ),
    **dict.fromkeys(("normal", "regular", "usual", "standard", "average", "medium"), "Normal"),
}
PACE = "(" + "|".join(PACE_WORDS) + ")"
LEAD = r"(?:(?:go|take it|keep it|be|work|do|plan|push it|make it)\s+)?"
FULL_DAY = {short: name for name, short in NAMES.items()}


def read_pace(t: str, negated: bool) -> Reading | None:
    """`go easier on saturday and go harder on sunday`, `push on sundays`, `saturdays are easy`: every clause names a
    pace and days (a clause of days alone takes the one before's); anything else isn't read as paces."""
    if negated:
        return None
    found: dict[str, str] = {}
    pace = None
    waiting: list[str] = []  # days said before their pace: "mon, tue, wed, thu push"
    first = (
        rf"{LEAD}(?:at )?(?:an? )?{PACE}(?: hard| it| all out| load| workload| days?| pace| work)?(?: on| for)?"
        rf" {DAY_WORDS}"
    )
    last = rf"{DAY_WORDS} (?:are |is |should be |will be |as |at |can be )?(?:an? |my )?{PACE}(?: days?| pace)?"
    for clause in (c.strip() for c in re.split(r",|;|\band\b|\bbut\b|\bthen\b", t) if c.strip()):
        if m := re.fullmatch(first, clause):
            word, days = m[1], m[2]
        elif m := re.fullmatch(last, clause):
            days, word = m[1], m[2]
        elif re.fullmatch(rf"(?:on )?{DAY_WORDS}", clause):
            if not pace:
                waiting.append(clause)
                continue
            word, days = None, clause
        else:
            return None
        pace = PACE_WORDS[word] if word else pace
        for day in [d for said in (*waiting, days) for d in days_of(said) or DAYS]:
            found[day] = pace  # type: ignore[assignment]
        waiting = []
    if not found or waiting:
        return None
    return Reading("pace", "pace", paces=tuple((d, found[d]) for d in DAYS if d in found))


def titles_in(words: str) -> tuple[str, ...]:
    """The events a sentence names: `the gym sessions on tuesday and thursday as well as climbing club` is gym and
    climbing club (the days go: a title is matched on every day it's on)."""
    words = re.sub(rf"\b(?:on|every) {DAY_WORDS}", " ", words)
    out = []
    for said in re.split(r"\s*(?:,|&|\band\b|\bas well as\b|\bplus\b|\bor\b)\s*", words):
        part = re.sub(r"\b(?:make|the|my|any|all|going to|go to|sessions?|meetings?|practices?)\b", " ", said)
        if not re.sub(r"\b(?:to|for|so)\b.*$", "", part).strip():  # "practice" alone is the event's name
            part = re.sub(r"\b(?:make|the|my|any|all|going to|go to)\b", " ", said)
        part = " ".join(part.split())
        if part and not re.fullmatch(DAY_WORDS, part):
            out.append(part)
    return tuple(out)


OPTIONAL = r"(?:optional|skippable|flexible)"
REQUIRED = r"(?:mandatory|required|compulsory|necessary|essential)"
BUSY = (
    r"(?:too much|a lot|lots|busy|behind|swamped|work|late|time|deadlines?|due|slammed|drowning|crunch|needed"
    r"|overwhelmed|buried)"
)


def read_optional(t: str, negated: bool) -> Reading | None:
    """Events that give way to work: `X are optional`, `X not mandatory`, `skip X if there's too much work`."""
    found = (
        (not negated and re.search(rf"^ ?(?:make |treat |consider )?(.+?) (?:be |is |are |as )?{OPTIONAL}\b", t))
        or (negated and re.search(rf"^ ?(?:make |treat )?(.+?) (?:be|is|are) {REQUIRED}\b", t))
        or re.search(
            rf"^ ?(?:can |may |you can |friday can |ok to )?(?:skip|miss|drop) (.+?) (?:if|when|whenever) .*{BUSY}", t
        )
        or (not negated and re.search(r"^ ?(.+?) (?:can|may) be (?:skipped|missed|dropped)\b", t))
        or re.search(rf"^ ?if .*{BUSY}.*?,? (?:then )?(?:skip|miss|drop) (.+?) ?$", t)
        or (negated and re.search(rf"^ ?(?:go to|attend) (.+?) (?:if|when|whenever) .*{BUSY}", t))
        or re.search(
            r"^ ?(?:i'?ll |i |i'd )?(?:skip|miss|drop|ditch) (.+?) (?:rather than|instead of|before i'?d?|sooner than)"
            r" (?:let(?:ting)?|being|be|have|having|go)\b.*\b(?:late|slip|overdue|miss(?:ed)?)\b",
            t,
        )
        or re.search(r"^ ?i (?:don't|do not) mind (?:skipping|missing|dropping) (.+?) (?:if|when) .*\bcatch up\b", t)
    )
    titles = tuple(x for x in (titles_in(found[1]) if found else ()) if x not in ("it", "them", "that", "this"))
    if any(re.search(r"\b(?:due|deadlines?|assignments?|homework|work)\b", x) for x in titles):
        return None  # "cram more in so i dont miss due dates": nothing late (deadlines), no event skipped
    if any(re.fullmatch(rf"{MEAL}s?|meals?", x) for x in titles):
        return None  # a meal cut short when busy is no event to skip
    return Reading("optional", "events", events=titles) if titles else None


SPAN = r"(\d+(?:\.\d+)?) ?(minutes?|mins?|m|hours?|hrs?|h)\b"
SIDES = (
    r"(?:before and after|around|either side of|on either side of|on both sides of|each side of|on each side of"
    r"|on both ends of|both ends of|on either end of)"
)
ROOM = r"(?:(?:of |for )?(?:buffer|travel time|travel|time|room|a gap|gap|break|padding|pad|cushion|margin)s? )?"
AND_AFTER = r"(\d+(?:\.\d+)?) ?(minutes?|mins?|m|hours?|hrs?|h)? ?after ?$"  # "… and 40 after", the unit kept


def span_minutes(amount: str, unit: str) -> int:
    return round(float(amount) * (60 if unit.startswith("h") else 1))


def read_around(t: str, negated: bool) -> Reading | None:
    """Time kept free around events: `30 minutes before and after gym`, `leave 15 min around climbing club`, `a 20
    minute buffer around gym`, `20 min before gym and 40 after`, `45 minutes after gym`."""
    t = re.sub(r" (?:free|clear|open|empty)\b(?=[ ,]|$)", " ", t)  # "keep 45 minutes after practice free"
    lead = r"^ ?(?:leave |keep |give (?:me )?|add |have |allow |need )?(?:an? )?"
    if m := re.search(rf"{lead}{SPAN} ?{ROOM}{SIDES} (.+?) ?$", t):
        before = after = span_minutes(m[1], m[2])
        titles = titles_in(m[3])
    elif m := re.search(rf"{lead}{SPAN} ?{ROOM}before (.+?) and {AND_AFTER}", t):
        before = span_minutes(m[1], m[2])
        after = span_minutes(m[4], m[5] or m[2])
        titles = titles_in(m[3])
    elif m := re.search(rf"{lead}{SPAN} ?{ROOM}(before|after) (.+?) ?$", t):
        minutes = span_minutes(m[1], m[2])
        before, after = (minutes, 0) if m[3] == "before" else (0, minutes)
        titles = titles_in(m[4])
    else:
        return None
    titles = tuple(re.split(r" (?:to|for|so) ", x)[0] for x in titles)  # "after soccer to shower" is around soccer
    titles = tuple(re.sub(r" (?:free|clear|open|empty|blocked)$", "", x) for x in titles)  # "after practice free"
    # Words for a kind of event, not one by name, are its kind's buffer (Claude sets `event_kinds`): as a title they
    # matched nothing ("15 minutes before and after events", "an hour before any exam", 27 Oct).
    odd = (
        r"\b(?:each|every|any|all|minutes?|mins?|before|after|starting|anything|everything)\b"
        r"|(?<!office )\bhours?\b"
    )
    # A kind of event alone is its kind's buffer (Claude's event_kinds): "class", "meetings"; "spin class" isn't.
    kind = r"^(?:calendar |scheduled )?(?:class(?:es)?|work|events?|exams?|meetings?|appointments?|lectures?)$"
    if (
        not titles
        or any(re.search(odd, x) or re.fullmatch(kind, x) for x in titles)
        or not 0 < max(before, after) <= 6 * 60
    ):
        return None  # "after every 2 hours of work", "20 minutes after class before homework": Claude's to read
    return Reading("around", "events", events=titles, before_min=before, after_min=after)


AHEAD = (
    r"(?:(?:you ?|we ?)?(?:'m |am |'re |are |im |re |'ve |have |'ve got |got )?(?:all |fully |completely |well )?"
    r"(?:ahead|caught up"
    r"|on top of|on track|up to date|done with|finished with|(?:have |got )?(?:the |spare |free )?time)"
    r"|(?:all )?(?:my )?work(?:'s| is) (?:all )?done|everything(?:'s| is) done|all my work is done)"
)
# The reason people give after naming the event, typos and all: `because of my workload`, `bc of work`, `, so …`.
WHY = r"(?: (?:because|becasue|becuase|bc|cause|cuz|since|due to|as|so|given)\b.*|,.*)?"
USUALLY = r"(?:usually|mostly|often|normally|generally|tend to|typically|mostly just)"


def read_ahead(t: str, negated: bool) -> Reading | None:
    """Events you go to only when you're ahead: `climbing club only if I'm ahead`, `only go to climbing club when I'm
    caught up`, `skip climbing club unless I'm ahead`, `I usually skip climbing club`, `I usually don't go to climbing
    club because of my workload, so I'll only go if I'm ahead of my work`. The `usually` ones are tried first: what
    follows the reason (`so I'll only go if…`) names no event."""
    found = (
        re.search(rf"^ ?{USUALLY} (?:skip|miss|drop) (.+?){WHY} ?$", t)
        or (negated and re.search(rf"^ ?{USUALLY} (?:go to|attend|make it to) (.+?){WHY} ?$", t))
        or re.search(rf"^ ?(?:go to |do |attend )?(.+?) only (?:if|when|once) {AHEAD}", t)
        or re.search(rf"\bonly (?:go to|do|attend|make it to) (.+?) (?:if|when|once) {AHEAD}", t)
        or re.search(rf"^ ?(?:skip|miss|drop) (.+?) unless {AHEAD}", t)
        or re.search(rf"^ ?(?:go to |attend )(.+?) (?:if|when) {AHEAD}", t)
    )
    titles = titles_in(found[1]) if found else ()
    return Reading("ahead", "events", events=titles) if titles else None


PREPARING = {"prep", "preparation", "preparing", "prepping", "study", "studying", "revision", "revise", "revising",
             "cram", "cramming", "flashcards", "flash cards", "anki", "quizlet",
             "review", "reviewing"}  # fmt: skip
ANY_EXAM = {"exam", "exams", "test", "tests", "the exam", "the exams", "the test", "it", "them", "event", "the event",
            "test day", "exam day", "test date", "exam date", "the day", "day"}  # fmt: skip
WHEN_DUE = (
    r"(?:(?:it'?s|its|they'?re|their|when it'?s|when they'?re|the) ?(?:due|due date|due time|deadline)"
    r"|(?:the )?(?:deadline|due time|due date))"
)
CLOSE = (
    r"(?:as close (?:as possible )?to (.+?) as (?:possible|i can|can be|it can be)"
    rf"|as late as possible(?: before {WHEN_DUE})?|just in time"
    r"|(?:close|closer|right up) to (.+?)(?=,| with | but | leaving | and | ?$))"
)
BUFFER = r"(a half|half a|half|a|an|one|two|three|\d+(?:\.\d+)?) ?(days?|d|hours?|hrs?|h|minutes?|mins?|m)\b"
SPARE = (
    rf"(?:{BUFFER} (?:of )?(?:buffer|margin|spare|to spare|before|early|ahead|breathing room|cushion|slack|room)"
    rf"|(?:buffer|margin|cushion) of {BUFFER}"
    rf"|(?:leaving|leave) {BUFFER})"
)


def buffer_minutes(amount: str, unit: str) -> int:
    n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "half a": 0.5, "a half": 0.5, "half": 0.5}.get(amount)
    n = n or float(amount)
    return round(n * (1440 if unit.startswith("d") else 60 if unit.startswith("h") else 1))


def read_close(t: str, negated: bool) -> Reading | None:
    """Work as close to its due as it can be: `I prefer all sessions of exam prep tasks to be done as close to the exam
    as possible`, `interview prep as close to the interview as possible`, `prep for the math quiz close to the quiz,
    with 1 day of buffer`, `readings as late as possible`. Prep (study, review) is the Exam prep kind; a quiz, an
    interview or a course named, its prep alone; a buffer keeps that much clear before the due."""
    t = re.sub(r"\s*[()\[\]]\s*", " , ", t)  # `(with 1 day of buffer)` is an aside, as after a comma
    t = t.replace(":", " ")
    m = re.search(rf"^ ?(.*?) (?:(?:to )?be (?:done|planned|scheduled) )?{CLOSE}(.*)$", t)
    if not m or not m[1].strip() or negated or re.search(r"\b(?:i do|i work|i'?m|best|better)\b", m[1]):
        return None  # "i do best last minute, schedule essays near the deadline": whose subject is after a comma
    if re.search(r"\bbut (?!finish|leave|leaving|with|keep|done|have|be|get|aim|stop|wrap)[a-z]+", m[4] or ""):
        return None  # "readings as late as possible but problem sets 2 days early": another subject, a second rule
    spare = re.search(SPARE, m[4] + " ") or re.search(SPARE, " " + m[1] + " ")
    m1 = m[1].split(",")[-1] if "," in m[1] and not spare else m[1]
    buffer = buffer_minutes(*[g for g in spare.groups() if g][:2]) if spare else 0
    filler = (
        r"\b(?:all|every|each|sessions?|tasks?|work on|working on|doing|do|done|my|the|for|of|on|a|an|write|writing"
        r"|finish|finishing|complete|submit|leave|keep|but|otherwise|then|and|as|you|buffer|margin|cushion)\b"
    )
    subject = re.sub(filler, " ", re.sub(SPARE, " ", m1))
    words = subject.split()
    preparing = [w for w in words if w in PREPARING]
    named = " ".join(w for w in words if w not in PREPARING and w not in ANY_EXAM) if preparing else ""
    target = re.sub(r"\b(?:the|my|a|an|its|their)\b", " ", (m[2] or m[3] or "")).strip(" ,")
    target = " ".join(target.split())
    specific = target if target and target not in ANY_EXAM and not re.fullmatch(WHEN_DUE, target) else ""
    one = lambda w: "quiz" if w == "quizzes" else w[:-1] if w.endswith("s") and not w.endswith("ss") else w  # noqa: E731
    same = {one(w) for w in specific.split()} <= {one(w) for w in named.split()}
    events = named if named and same else specific or named  # math quiz > quiz; vocab quizzes > the quiz
    if preparing:
        return Reading("close", "exam prep", events=(events,) if events else None, before_min=buffer or None)
    what = subject_of(" ".join(words))
    return Reading("close", what, events=(specific,) if specific else None, before_min=buffer or None)


MEAL_NAMES = ("breakfast", "lunch", "dinner")
MEAL = r"(?:breakfast|brunch|lunch|dinner|supper)"
MEALS = rf"((?:(?:all |all of )?(?:my |the )?)?(?:{MEAL}|meals?)(?:\s*(?:,|and|or|&)\s*{MEAL})*)"
DECIDES = r"(?:decides?|learns?|figures? out|works? out)"


def meals_in(words: str) -> tuple[str, ...]:
    """The meals named: `lunch or dinner`, `my meals` (all three), brunch as lunch and supper as dinner."""
    if re.search(r"\bmeals?\b", words):
        return MEAL_NAMES
    said = {"brunch": "lunch", "supper": "dinner"}
    found = {said.get(w, w) for w in re.findall(r"breakfast|brunch|lunch|dinner|supper", words)}
    return tuple(m for m in MEAL_NAMES if m in found)


def read_meals(t: str, negated: bool) -> Reading | None:
    """Meals kept, whatever the work (`never skip lunch or dinner`, `always keep my meals`, `dinner is
    non-negotiable`), or left to what Friday learns (`let Friday decide breakfast`, `learn whether I have
    breakfast`, `plan breakfast only if I usually have it`)."""
    if m := (
        re.search(rf"^ ?(?:let )?friday {DECIDES} (?:(?:whether|if|when) (?:have |eat )?)?{MEALS}", t)
        or re.search(
            rf"^ ?(?:learn|figure out|work out) (?:(?:whether|if|when) )?(?:usually )?(?:have |eat )?{MEALS}", t
        )
        or re.search(rf"^ ?(?:plan )?{MEALS} only (?:if|when) (?:usually )?(?:have|eat) (?:it|them)", t)
    ):
        meals = meals_in(m[1])
        return Reading("meals_learned", "meals", events=meals) if meals else None
    kept = (
        (negated and re.search(rf"^ ?(?:skip|miss|drop|give up|lose|cut) (?:on )?{MEALS}\b", t))
        or (negated and re.search(rf"^ ?{MEALS} (?:is|are|gets?) (?:skipped|missed|dropped|cut|given up)\b", t))
        or re.search(rf"^ ?(?:keep|protect) {MEALS}(?: no matter what| every day| whatever)?\b", t)
        or re.search(
            rf"^ ?{MEALS} (?:is|are) (?:non[- ]?negotiable|a must|must haves?|mandatory|required|protected|sacred"
            r"|essential|a priority|untouchable|off limits)\b",
            t,
        )
    )
    if kept:
        meals = meals_in(kept[1])
        return Reading("meals_kept", "meals", events=meals) if meals else None
    return None


def named_meals(r: Reading) -> tuple[str, ...]:
    """The meals a reading names, however they were given (Claude's overrides too); all three when none are."""
    return meals_in(" ".join(r.events or ()).lower()) or MEAL_NAMES


def meals_said(meals: tuple[str, ...]) -> str:
    if set(meals) == set(MEAL_NAMES):
        return "Meals"
    names = [m.capitalize() if n == 0 else m for n, m in enumerate(meals)]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


SMALL = r"(?:short|shorter|shortest|small|smaller|smallest|little|quick|quicker|tiny|brief)"
BIG = r"(?:long|longer|longest|big|bigger|biggest|large|larger|largest|huge)"
GAP = (
    r"(?:gaps?|(?:time )?slots?|windows?|breaks?|blocks?(?: of time)?|stretch(?:es)?|chunks?(?: of time)?|holes?"
    r"|pockets?|spaces?)"
)
TASKS = r"(?:tasks?|work|things|to[- ]?dos?|stuff|assignments?|events?|items?)"


# What runs by itself, as it's said: "background tasks", "things done in the background", "tasks that run on their
# own", "anything that runs by itself" ("events" too, as you might call laundry).
RUNNING = (
    r"\b(?:(?:background|unattended) (?:tasks?|things?|jobs?|work|events?|stuff)"
    r"|(?:tasks?|things?|jobs?|work|events?|stuff|anything|what(?:ever)?)(?: that| which)?(?: (?:is|are|gets?|get))?"
    r" (?:(?:done|run|running|runs|going) )?(?:in the background|(?:by|on) (?:it|them)?sel(?:f|ves)"
    r"|on (?:its|their) own))\b"
)
AWAY = (
    r"\b(?:during|in|at|through|over|while (?:i'm |i am |am )?(?:in|at))(?: (?:my|an?|the))?"
    r" (?:events?|class(?:es)?|lectures?|meetings?|appointments?|event times?)\b"
)
# ("I" is gone by now: `read` takes it out with the hedges.)
WORKING = (
    r"\b(?:(?:during|in|at) (?:other |my )?work(?:ing)?(?: times?| hours?)?"
    r"|(?:while|when) (?:i'm |i am |am |i )?(?:working|work|at (?:my )?desk|home|around))\b"
)


# How much sleep (27 Oct: "I want at least 7 hours of sleep per night" went nowhere): a number of hours said with
# sleep, either way round ("7 hours of sleep", "sleep at least 7 hours"), "and a half" or ½ on top, a range's lower end.
SLEEP_WORD = r"(?:sleep|sleeping|shut[- ]?eye|zzz+|rest a night|in bed)"
SLEEP_HOURS = (
    r"(?:between )?(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)( and a half| ?½"
    r"| 1/2)?(?: ?(?:-|–|to|or|and) ?\d+(?:\.\d+)?)?\+? ?(?:hours?|hrs?|h)\b"
)
SLEEP_AMOUNT = (
    rf"{SLEEP_HOURS} (?:(?:a|per|each) night )?(?:(?:of|for|a night of|per night of|worth of|minimum of|min of"
    rf"|at least of) )?(?:good )?{SLEEP_WORD}"
    rf"|\b{SLEEP_WORD}\b[^.;]{{0,40}}?{SLEEP_HOURS}"
)
MOST_SLEEP = r"\b(?:at most|more than|max(?:imum)?|up to|tops|or less|cap(?:ped)?|limit)\b"


SPACED_AMOUNT = (
    r"(?:at least |a minimum of |min(?:imum)? |no less than )?(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven"
    r"|eight|nine|ten) ?(days?|d|weeks?|wks?|hours?|hrs?|h)"
)


def read_spacing(t: str, negated: bool) -> Reading | None:
    """A repeating task's times kept apart (C50): `laundry at least 7 days apart`, `workouts need to be at least 48
    hours apart`, `a week between laundry`. The subject is the repeat's title; the amount is days, start to start."""
    if negated:
        return None
    if m := re.search(
        rf"^ ?(?:keep |space |spread )?(?:my |the |each |every )?([a-z][a-z0-9 ]*?) (?:sessions? |times? |runs? )?"
        rf"(?:(?:should|need to|needs to|must|have to|has to) (?:be|have) )?(?:spaced )?{SPACED_AMOUNT} apart ?$",
        t,
    ):
        subject, amount, unit = m[1], m[2], m[3]
    elif m := re.search(
        rf"^ ?{SPACED_AMOUNT} (?:between|in between) (?:each |every |my |the )*([a-z][a-z0-9 ]*?)"
        r"(?: sessions?| times?)? ?$",
        t,
    ):
        amount, unit, subject = m[1], m[2], m[3]
    else:
        return None
    n = WORD_HOURS.get(amount) or (1 if amount in ("a", "an") else float(amount))
    days = n / 24 if unit.startswith("h") else n * 7 if unit.startswith("w") else n
    subject = re.sub(r"^(?:keep|space|spread|my|the|each|every|doing|do) ", "", subject.strip())
    if not subject or re.search(JUNK_SUBJECT, subject) or not 0 < days <= 366:
        return None
    return Reading("spacing", subject, amount=round(float(days), 3))


def read_sleep(t: str, negated: bool) -> Reading | None:
    """At least so many hours of sleep a night, on some nights or all: a floor, never a cap ("no more than 9 hours of
    sleep" isn't something Friday plans); "below" and "under" say the floor too ("don't let work cut my sleep below
    6.5 hours")."""
    m = re.search(SLEEP_AMOUNT, t)
    if not m or re.search(MOST_SLEEP, t):
        return None
    number, half = (m[1], m[2]) if m[1] else (m[3], m[4])
    hours = (float(number) if number[0].isdigit() else WORD_HOURS[number]) + (0.5 if half else 0)
    if not 3 <= hours <= 12:
        return None
    return Reading("sleep_min", "work", amount=hours, days=days_of(t))


# What runs by itself, by name (27 Oct): laundry, the dishwasher, model training, renders, downloads, 3d prints.
RUNNING_NAMED = (
    r"\b(?:laundry|dishwasher|dryer|washer|washing machine|slow cooker|crock ?pot|bread proofing|proofing"
    r"|model training"
    r"|training runs?|renders?|rendering|downloads?|compiles?|builds?|simulations?|sims|experiments?|3d prints?|prints?"
    r"|batch jobs?|jobs that run|auto(?:mated)? tasks|self running tasks|hands off (?:stuff|tasks)|backups?|dough"
    r"|(?:tasks|things) that run themselves|unattended (?:jobs"
    r"|tasks))\b"
)
THERE = (
    r"\b(?:while|when|during|unless) (?:i'?m |i am |am )?(?:home |at home )?(?:working|studying|doing homework"
    r"|at (?:my )?(?:desk"
    r"|computer)|around(?: to watch)?|home working|study time|in (?:my )?(?:work|study) (?:blocks?|sessions?|time))\b"
    r"|\bduring (?:my )?(?:work|study) (?:blocks?|sessions?|time)\b"
)
AWAY_TOO = (
    r"\b(?:during|while i'?m at|while i'?m in|at|in|overlap(?: with)?|over|overnight) (?:my |an? |the )?(?:practice"
    r"|lab|lectures?|meetings?|events?|class(?:es)?|out|overnight)\b|\bovernight\b|\bwhen i'?m out\b"
)


def read_running(t: str, negated: bool) -> Reading | None:
    """What runs by itself only while you're there to see to it: `background tasks only during work time, not during
    events`, `things that run by themselves must not run during class`, `run laundry-like tasks while I work`,
    `model training should only run while I'm at my desk`, `renders shouldn't run while I'm at practice`."""
    if not (re.search(RUNNING, t) or re.search(RUNNING_NAMED, t)):
        return None
    if re.search(WORKING, t) or re.search(THERE, t) or (negated and (re.search(AWAY, t) or re.search(AWAY_TOO, t))):
        return Reading("runs_while_working", "work")
    return None


def read_fit_gaps(t: str, negated: bool) -> Reading | None:
    """Tasks matched to the free time they fit: `shorter tasks in smaller time slots and longer ones in larger`,
    `fit tasks to the gaps`, `use small gaps for small tasks`, `save long stretches for long work`."""
    if negated:  # "don't waste big chunks of time on small stuff" says it the other way round
        sized = rf"(?:{BIG} |\d+ ?(?:hours?|hrs?|h) )"
        wasted = (
            re.search(
                rf"\bwaste (?:an? |the |my )?{sized}(?:free |open )?{GAP}(?: of time)? on\b.*\b(?:{SMALL}|\d+ ?min)", t
            )
            or re.search(rf"\b(?:(?:put|stick|schedule) )?{BIG} {TASKS} (?:in|into) {SMALL} {GAP}", t)
            or re.search(rf"\bkeep (?:the |my )?{BIG} (?:open |free )?{GAP} for {BIG}", t)
            or re.search(
                rf"\bbreak up (?:an? |my |the )?{BIG} (?:free |open )?(?:afternoons?|mornings?|evenings?|days?"
                rf"|{GAP}) with {SMALL}",
                t,
            )
        )
        return Reading("fit_gaps", "work") if wasted else None
    if (
        re.search(rf"\b(?:use|fill) .*\b(?:{GAP}|dead time|downtime)\b.*\b(?:for|with) .*\b(?:{SMALL}|\d+ ?min)", t)
        or re.search(
            rf"\bmatch (?:the |my )?{TASKS}(?: lengths?)? to (?:the )?(?:size|length) of (?:the |my )?(?:free )?{GAP}",
            t,
        )
        or re.search(rf"\bsqueeze {SMALL} {TASKS} (?:in )?between\b", t)
        or re.search(rf"\b{BIG} {GAP}(?: of (?:free )?time)? (?:are|is) for {BIG}\b", t)
        or re.search(rf"\b{SMALL} {GAP} (?:are|is) (?:for )?{SMALL}\b", t)
        or re.search(rf"\bput {BIG} {TASKS} where (?:there'?s|there is) (?:an? )?{BIG}(?: enough)? {GAP}", t)
        or re.search(rf"\bkeep (?:the |my )?{BIG} (?:open |free )?{GAP} for {BIG}", t)
        or re.search(
            rf"\b{SMALL}\b.*\b{GAP}\b.*\b(?:are|is) (?:perfect|great|good|ideal|best"
            rf"|made) for\b.*\b{SMALL}\b",
            t,
        )
        or re.search(rf"\b{BIG} (?:open |free )?{GAP}\b.*\buse it for (?:an? )?{BIG}", t)
        or re.search(
            rf"\b(?:slot|fit|squeeze|put|tuck) {SMALL} {TASKS} (?:in|into) (?:the )?(?:in[- ]?between|gaps?"
            rf"|{SMALL})",
            t,
        )
        or re.search(rf"\bgive (?:the |my )?{BIG} (?:free |open )?{GAP} to (?:the )?{BIG}", t)
        or re.search(rf"\b(\d+)[- ]?min(?:ute)?s? {TASKS} (?:belong|go|fit) in \1[- ]?min(?:ute)?s? {GAP}", t)
    ):
        return Reading("fit_gaps", "work")
    found = (
        re.search(rf"\b{SMALL} {TASKS} (?:in|into|for|during) (?:the |my )?(?:free )?{GAP}\b", t)
        or re.search(
            rf"\b(?:fit|match|size) (?:the |my )?{TASKS}(?: lengths?| sizes?)? (?:in)?to (?:the |my )?"
            r"(?:free (?:time|gaps?|slots?)|time available|available time|gaps?|openings?)\b",
            t,
        )
        or re.search(rf"\b{SMALL}\b.*\b(?:in|into|with|for|to|during)\b.*\b{SMALL} (?:free )?{GAP}", t)
        or re.search(rf"\b{BIG}\b.*\b(?:in|into|with|for|to|during)\b.*\b{BIG} (?:free )?{GAP}", t)
        or re.search(rf"\b{SMALL} (?:free )?{GAP} (?:for|with)\b.*\b{SMALL}\b", t)
        or re.search(rf"\b(?:save|keep|leave|use) (?:the |my )?{BIG} (?:free )?{GAP} for\b", t)
        or re.search(
            rf"\b(?:fit|match|size) (?:the |my )?{TASKS}(?: lengths?)? (?:in)?to (?:the |my )?(?:free )?{GAP}", t
        )
        or re.search(rf"\b(?:fill|use) (?:the |my )?{SMALL} (?:free )?{GAP} with\b", t)
    )
    return Reading("fit_gaps", "work") if found else None


def evening(raw: str) -> str | None:
    """A time the day ends at: `10` or `10:00` with no am or pm is the evening's."""
    at = clock(raw)
    if at and not re.search(r"(am|pm|noon|midnight)", raw) and int(at[:2]) < 12:
        at = f"{int(at[:2]) + 12:02d}{at[2:]}"
    return at


def read_night_before(t: str, negated: bool) -> Reading | None:
    """`no work after 10pm the night before climbing club`, `stop working at 10 before climbing club`, `if I'm going to
    climbing club the next day, the day before must end at 10`."""
    before = r"(?:on )?(?:the )?(?:night|day|evening)?s? ?before"
    stop = r"(?:stop working|stop work|end(?: the| my)? day|finish(?: work)?|be done|wrap up|go to bed|be in bed)"
    what = r"(?:work |anything |studying |study |homework |hw |school )?"
    ended = negated and re.search(rf"^ ?{what}(?:after|past) {TIME} {before} (.+?) ?$", t)
    if m := ended or re.search(rf"^ ?{stop} (?:at|by) {TIME} {before} (.+?) ?$", t):
        at, titles = evening(m[1]), titles_in(m[2])  # no work after 10pm, or stop working at 10, the night before X
    elif m := re.search(
        rf"^ ?if (?:'m |am |im )?(?:going to|have|got) (.+?) (?:the )?(?:next day|tomorrow|next morning),? (?:then )?"
        rf"(?:the )?(?:previous day|day before|night before|evening before|previous night)? ?"
        rf"(?:must |should |has to |needs to |to )?(?:(?:end|stop|finish|be done|wrap up) (?:at|by)"
        rf"|(?:no )?work after) {TIME}",
        t,
    ):
        titles, at = titles_in(m[1]), evening(m[2])
    else:
        return None
    return Reading("night_before", "work", at=at, events=titles) if at and titles else None


def read_deadlines(t: str, negated: bool) -> Reading | None:
    """Work more when it must, so nothing is late: what `late_work` already does, read last so any other rule wins."""
    pushed = r"\b(?:cram|push|work (?:more|longer|harder)|stay up|squeeze|more in)\b"
    if re.search(r"\b(?:can|may|could|fine|ok|okay|allowed)(?: to)? (?:be |to be |if )?late\b", t) or (
        re.search(r"\bif\b[^,]*\blate,", t) and not re.search(pushed, t)
    ):
        return None  # "readings can be late" says the opposite; "if a reading is late, skip it" is something else
    if re.search(
        r"\b(?:skip|skipping|miss|missing|ditch|drop|blow off|bail on) (?!(?:a |any |the |my )?(?:due|deadlines?"
        r"|assignments?|work|anything|nothing|homework)\b)",
        t,
    ):
        return None  # "skip the gym rather than letting something be late": the gym is optional (read_optional)
    if re.search(r"\bfirst\b.*,.*\b(?:after|later|second|next|last)\b", t):
        return None  # "near deadlines first, long projects after": which work first (Claude's setting)
    late = re.search(r"\b(late|on time|deadlines?|overdue|miss(?:ed|ing)?|due dates?|slip)\b", t)
    push = re.search(
        r"\b(push|harder|more|longer|later|necessary|needed|need|must|have to|whatever|sure|let|be|first|takes|hit"
        r"|meet|go over|over my|cram|long days?|late nights?|means|matter what|priority)\b",
        t,
    )
    return Reading("deadlines", "work") if late and push else None


CAP = r"(?:at most|no more than|not more than|more than|max(?:imum)?(?: of)?|up to|less than|under|limit (?:it )?to)"
AMOUNT = r"(\d+(?:\.\d+)?) ?(h|hrs?|hours?|m|mins?|minutes?)"
PER_DAY = r"(?: (?:a|per|each|every) (?:day|night)|/day| daily| a night)"


def read_cap(t: str, negated: bool) -> Reading | None:
    """`at most 6 hours a day`, `no more than 90 minutes of reading a day`, `under 6h of work daily`, `6h/day max`,
    `max 4h a day on weekends`, `don't work more than 4 hours on saturdays`: on those days only."""
    upto = rf"(?!{PER_DAY}| on (?:{DAY_WORDS[1:]})"  # "of deep work a day": the subject runs to the day's words
    m = re.search(rf"{CAP} {AMOUNT}(?: of ((?:{upto}[a-z0-9 ])+))?({PER_DAY})?(?: on {DAY_WORDS})?(?: |$)", t)
    if m and not (m[4] or m[5]):  # "at most 2 hours" alone is a sitting, not a day's
        m = None
    if m is None and (
        n := re.search(rf"^ ?{AMOUNT}(?:/| a | per )day max(?:imum)?(?: (?:for|of) ([a-z0-9 ]+?))? ?$", t)
    ):
        return Reading("cap", subject_of(n[3] or "work"), amount=hours_of(n[1], n[2]))  # "… a day max for client work"
    if m is None and (
        n := re.search(rf"^ ?{AMOUNT} max(?:imum)?(?: a day| per day| daily)?(?: on {DAY_WORDS})? ?$", t)
    ):
        return Reading("cap", "work", amount=hours_of(n[1], n[2]), days=days_of(n[3]) if n[3] else None)
    if m is None and (
        n := re.search(rf"^ ?(?:limit|keep|cap) ([a-z0-9 ]+?) (?:to|at) {AMOUNT}{PER_DAY}?(?: on {DAY_WORDS})? ", t)
    ):
        if days := days_of(n[1]):  # `cap mondays at 4 hours`: the days, not a subject
            return Reading("cap", "work", amount=hours_of(n[2], n[3]), days=days)
        return Reading("cap", subject_of(n[1]), amount=hours_of(n[2], n[3]), days=days_of(n[4]) if n[4] else None)
    if m is None:
        return None
    lead = re.match(rf"^ ?{DAY_WORDS}\b", t)  # "tuesdays I work a shift so 5 hours of school, max"
    subject = (m[3] or "").strip() or (
        re.search(r"^ ?(?:don't |do not )?(\w+(?: \w+)?) (?:for )?" + CAP, t) or [None, None]
    )[1]
    if subject and subject_of(subject) == "work":  # "deep work" is a kind of work; "studying" is all of it
        subject = None
    days = days_of(m[5]) if m[5] else days_of(lead[1]) if lead else None
    if not subject and (named := re.search(rf"{PER_DAY} for ([a-z0-9 ]+?) ?$", t)):
        subject = named[1]  # "at most 4 hrs a day for client work"
    return Reading("cap", subject_of(subject or "work"), amount=hours_of(m[1], m[2]), days=days)


def hours_of(amount: str, unit: str) -> float:
    return round(float(amount) / (60 if unit.startswith("m") else 1), 2)


def read_early(t: str, negated: bool) -> Reading | None:
    m = re.search(
        r"finish(?: ([a-z0-9 ]+?))? (a|one|two|three|\d+(?:\.\d+)?) (days?|hours?|hrs?|weeks?) (?:early|before|ahead)",
        t,
    )
    if not m:
        return None
    if re.fullmatch(r"(?:them|it|those|these|that|this|they)", (m[1] or "").strip()):
        return None  # "never leave essays to the last day, finish them 1 day early": what them is, Claude reads
    n = {"a": 1, "one": 1, "two": 2, "three": 3}.get(m[2]) or float(m[2])
    days = n / 24 if m[3].startswith("hour") else n * 7 if m[3].startswith("week") else n
    return Reading("early", subject_of(m[1] or "work"), amount=round(float(days), 3))


LIGHTER = r"lighter|light|easier|easy|quieter|quiet|calmer|less busy"
LIGHTER_SHARE = 0.5  # a lighter stretch keeps about half its time free: less work there, not none


def start_clock(start: str, end: str) -> str | None:
    """A span's start as people say it: bare, it takes the end's am or pm when it comes before it on the same clock
    (`8 to 11pm` is 8pm, `6 and 8am` is 6am, `10-2pm` is 10am)."""
    bare = re.fullmatch(r"(\d{1,2})(:\d\d)?", start.strip())
    meridiem = re.search(r"(am|pm)\s*$", end.strip())
    if not bare or not meridiem or bare[1].startswith("0"):
        return clock(start)
    hour, end_hour = int(bare[1]) % 12, int(re.match(r"\d+", end.strip())[0]) % 12  # type: ignore[index]
    same = meridiem[1] if hour <= end_hour else ("am" if meridiem[1] == "pm" else "pm")
    return clock(f"{start.strip()}{same}")


def span_end(start: str | None, end: str | None, said: str) -> str | None:
    """A span's end as people say it: `from 6 to 9` with no am or pm ends at 9pm, after it began; noon and midnight
    are what they say (`9pm to midnight` ends at midnight, not noon)."""
    if (
        start
        and end
        and end <= start
        and not re.search(r"(am|pm|noon|midnight)", said)
        and int(end[:2]) < 12
        and not re.match(r"0\d", said.strip())
    ):
        return f"{int(end[:2]) + 12:02d}{end[2:]}"
    return end


def read_free(t: str, negated: bool) -> Reading | None:
    """`keep saturday mornings free` keeps all of it; `keep friday and saturday nights lighter` (or `lighter friday
    evenings`, or the way Friday writes it back, `keep fri, sat 8pm–11:59pm lighter`) about half."""
    if re.search(r"\b(?:grind|push|go hard|lock in)\b", t):
        return None  # "grind tues/thurs. keep wed afternoon open": a pace too, two rules
    m = re.search(
        rf"(?:keep|make) (?:my )?{DAY_WORDS}? ?(mornings?|afternoons?|evenings?|nights?)? ?"
        rf"(?:(?:from |between )?{TIME} ?(?:to|until|and|-|–) ?{TIME} )?(free|clear|open|{LIGHTER})\b",
        t,
    )
    if m and (m[1] or m[2] or m[3]):
        days, part, start, end, how = m[1], m[2], m[3], m[4], m[5]
    elif m := re.search(rf"\b({LIGHTER}) {DAY_WORDS} ?(mornings?|afternoons?|evenings?|nights?)\b", t):
        how, days, part, start, end = m[1], m[2], m[3], None, None
    else:
        return free_span(t)
    if not days and (on := re.search(rf" on {DAY_WORDS} ", t)):  # "keep my evenings lighter on weekdays"
        days = on[1]
    if not days and (after := re.search(rf"\b(?:free|clear|open|{LIGHTER}) {DAY_WORDS}(?= |$|,)", t)):
        days = after[1]
    begins = (start_clock(start, end) if end else clock(start)) if start else None
    ends = span_end(begins, clock(end), end) if end else None
    span = PARTS.get((part or "").rstrip("s"), (begins, ends))
    share = None if how in ("free", "clear", "open") else LIGHTER_SHARE
    return Reading(
        "free", "work", rel="between" if span[0] else None, at=span[0], until=span[1], days=days_of(days or ""),
        amount=share,
    )  # fmt: skip


FREE_SAID = r"\b(?:free|open|clear|empty|unbooked|blocked off)\b"


def free_span(t: str) -> Reading | None:
    """A stretch of time said free however it's put ("6 to 7pm free every weekday", "free time from 8 to 10pm",
    "nothing between 3 and 4pm on wednesdays, keep it open"): kept free, never the only time work may go (8 Nov: the
    window reader made each the only hours for work)."""
    if not re.search(FREE_SAID, t) or re.search(r"\b(?:feel free|free to|if (?:i'?m|it'?s) free)\b", t):
        return None
    if (
        re.search(r"\b(?:at least|minimum|min)\b|\d+ (?:free )?(?:h|hrs?|hours?)\b", t)
        or len(set(re.findall(r"\b(morning|afternoon|evening|night)s?\b", t))) > 1
    ):
        return None  # "at least 2 free hours every evening" (no such rule); "friday nights and saturday mornings" (two)
    days = days_of(" ".join(m[0] for m in re.finditer(DAY_WORDS, t))) if re.search(DAY_WORDS, t) else None
    part = re.search(r"\b(morning|afternoon|evening|night)s?\b", t)
    if m := re.search(rf"(?:between |from )?{TIME} ?(?:to|until|and|-|–) ?{TIME}", t):
        start, end = start_clock(m[1], m[2]), None
        if start and part and part[1] != "morning" and not re.search(r"am|pm", m[1] + m[2]) and start < "12:00":
            start = f"{int(start[:2]) + 12:02d}{start[2:]}"  # "7 to 9 in the evening"
            end = clock(re.sub(r"^(\d{1,2})", lambda h: str(int(h[1]) + 12 if int(h[1]) < 12 else h[1]), m[2]))
        end = end or span_end(start, clock(m[2]), m[2])
        return Reading("free", "work", rel="between", at=start, until=end, days=days) if start and end else None
    if part:
        start, end = PARTS[part[1]]
        return Reading("free", "work", rel="between", at=start, until=end, days=days)
    return None


UNCLEAR = r"\b(?:during|after|before|while|until|at|with|when)\b"  # a subject that's a phrase, not a kind of work
# Events by kind, which a window or days rule can't move (8 Nov: "no meetings before 10" was a rule about a task
# called "meetings"): the calendar's to keep, Claude's to read.
EVENTS_BY_KIND = r"^(?:meetings?|calls?|zoom calls?|appointments?|appts?|classes|lectures?|events?|shifts?)$"


def read_window(t: str, negated: bool) -> Reading | None:
    if re.search(r"\b(?:night|day|evening) before\b|\beve of\b", t):
        return None  # "no tasks after 10 the night before an exam": that night only (read_night_before or Claude)
    on = re.search(rf" on {DAY_WORDS}(?= |,)", t)
    days = days_of(on[1]) if on else None
    if on:
        t = t.replace(on[0], " ")
    between = "not_between" if negated else "between"  # "no work between 7 and 10am" keeps those hours free
    if m := re.search(r"^ ?([a-z0-9 ]*?) ?(?:in the|during the) (morning|afternoon|evening|night)s? ", t):
        if re.search(r"\b(?:best|better|worst|well)\b", m[1]):
            return None  # "I work best late at night": a liking, Claude's to read
        start, end = PARTS[m[2]]
        return Reading("window", subject_of(m[1]), rel=between, at=start, until=end, days=days)
    if m := re.search(rf"^ ?([a-z0-9 ]*?) ?(?:between|from) {TIME} (?:and|to|until|-) {TIME} ", t):
        start = start_clock(m[2], m[3])
        end = span_end(start, clock(m[3]), m[3])
        return (
            Reading("window", subject_of(m[1]), rel=between, at=start, until=end, days=days) if start and end else None
        )
    if m := re.search(rf"^ ?([a-z0-9 ]*?) ?(before|after|by|until|past) {TIME} ", t):
        if re.match(r"^ ?only\b", t) and subject_of(m[1]) in ("light work", "deep work"):
            return None  # "only easy stuff after 10pm": nothing else then, which no rule says (Claude)
        at = clock(m[3])
        rel = "before" if m[2] in ("before", "by", "until") else "after"
        if negated:
            rel = "after" if rel == "before" else "before"
        subject = subject_of(m[1])
        if re.fullmatch(EVENTS_BY_KIND, subject):
            return None
        return Reading("window", subject, rel=rel, at=at, days=days) if at and not re.search(UNCLEAR, subject) else None
    return None


def read_days(t: str, negated: bool) -> Reading | None:
    m = re.search(
        rf"^ ?([a-z0-9 ]*?) ?(only )?(?<![a-z0-9])on {DAY_WORDS}(?= |, ?(?:i|i'm|my|it's|cause|because|bc|since)\b)"
        r"(?! ?(?:mornings?|afternoons?|evenings?|nights?))",
        t,
    ) or re.search(rf"^ ?(rest|off) {DAY_WORDS} ", t)
    if not m:
        return None
    if re.search(r"\bpace\b|\b(?:push|easy|easier|chill|grind|go hard)\b", t):
        return None  # "a normal pace on mondays, not push": how hard, not whether (read_pace or Claude)
    if m[1] in ("rest", "off"):  # `rest sundays` or `rest on sundays`: the days are the last group either way
        return Reading("days", "work", rel="not_on", days=days_of(m.groups()[-1]))
    if re.match(r"^ ?only \w", m[0]) and not re.match(r"^ ?only (?:work|working|study|studying)\b", m[0]):
        return None  # `only light work on weekends`: on those days nothing else, not that work only then (Claude)
    rel = "not_on" if negated else "on"
    if not days_of(m[3]) or re.search(r"\b\d+ ?(?:minutes?|mins?|hours?|hrs?|h|m)\b|\beach way\b|\bmax\b", m[1]):
        return None  # "every day" names no days; "commute 40 minutes each way on tuesdays" isn't work on days
    subject = subject_of(m[1])
    if re.search(UNCLEAR, subject) or re.fullmatch(EVENTS_BY_KIND, subject):
        return None  # "no work during movie night on thursdays" names no kind of work: Claude reads it
    return Reading("days", subject, rel=rel, days=days_of(m[3]))


def read_after(t: str, negated: bool) -> Reading | None:
    m = re.search(r"^ ?([a-z ]+?) (?:right |straight |just )?after (?:my |the )?([a-z ]+?) ?$", t)
    if not m or clock(m[2]) or negated:
        return None
    event = re.sub(r"^(?:last|first|next|final) ", "", m[2].strip())
    if re.search(
        r"^(?:waking|wake|getting up|long|short|busy|heavy|breakfast|brunch|lunch|dinner|supper)\b", event
    ) or re.search(r"^ ?(?:the )?(?:first|lighter|easier|light|heavy|more|less)\b", m[1]):
        return None  # "first hour after waking", "lighter evenings after long practice days": not a sitting
    odd = r"\b(?:each|every|my|hours?|minutes?|mins?|to|before|starting)\b"
    if re.search(odd, m[2]) or re.search(r"\d", t) or re.search(r"\b(?:week|day|time|need|break)\b", m[1]):
        return None  # "after each lecture", "after my 11am class", "easy week after midterms": not a sitting
    return Reading("after", subject_of(m[1]), event=event)


def with_overrides(r: Reading, overrides: dict[str, Any]) -> Reading:
    known = {
        k: (tuple(v) if k == "days" and v is not None else v)
        for k, v in overrides.items()
        if k in Reading.__dataclass_fields__
    }
    return replace(r, **known)


DAY_LABEL = {
    ("mon", "tue", "wed", "thu", "fri"): "on weekdays",
    ("sat", "sun"): "on weekends",
    ("mon", "tue", "wed", "thu", "sun"): "on school nights",
}


def days_words(days: tuple[str, ...] | None) -> str:
    if not days:
        return ""
    return DAY_LABEL.get(days) or "on " + ", ".join(d.capitalize() for d in days)


def titled(words: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in words.split())


def days_spoken(days: tuple[str, ...]) -> str:
    """Saturdays; Saturdays and Sundays; weekends."""
    if days in (DAYS[:5], DAYS[5:]):
        return "weekdays" if days == DAYS[:5] else "weekends"
    names = [FULL_DAY[d].capitalize() + "s" for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def sentence(r: Reading) -> str:
    """The rule in plain words, as the Rules list shows it, on a 12-hour clock."""
    return ampm_in(said(r))


def said(r: Reading) -> str:
    if r.kind == "deadlines":
        return "Deadlines come first"
    if r.kind == "optional":
        names = [titled(e) for e in r.events or ()]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return f"{listed} {'is' if len(names) == 1 else 'are'} optional: work takes the time when it must"
    if r.kind == "fit_gaps":
        return "Short tasks in short gaps, long ones in long stretches"
    if r.kind == "runs_while_working":
        return "Things that run by themselves run while you work, not during events or your sleep"
    if r.kind == "spacing":
        return f"{titled(r.subject)} at least {r.amount:g} {'day' if r.amount == 1 else 'days'} apart"
    if r.kind == "sleep_min":
        on = f" {days_words(r.days)}" if r.days else ""
        return f"At least {r.amount:g} h of sleep a night{on}"
    if r.kind == "meals_kept":
        meals = named_meals(r)
        return f"{meals_said(meals)} {'is' if len(meals) == 1 else 'are'} never skipped for work"
    if r.kind == "meals_learned":
        return f"Let Friday decide {meals_said(named_meals(r)).lower()} from your habits"
    if r.kind == "close":
        spare = f", finished {buffer_said(r.before_min)} before" if r.before_min else ""
        if r.subject == "exam prep":
            return f"Exam prep as close to {titled(r.events[0]) if r.events else 'the exam'} as possible{spare}"
        what = r.subject[:1].upper() + r.subject[1:]
        if r.events:
            return f"{what} as close to {titled(r.events[0])} as possible{spare}"
        return f"{what} as late as possible before it's due{spare}"
    if r.kind == "around":
        names = " and ".join(titled(e) for e in r.events or ())
        b, a = r.before_min or 0, r.after_min or 0
        if b == a:
            return f"{span_said(b)} before and after {names}"
        sides = [f"{span_said(b)} before {names}"] if b else []
        sides += [f"{span_said(a)} after" + ("" if b else f" {names}")] if a else []
        return " and ".join(sides)
    if r.kind == "ahead":
        names = [titled(e) for e in r.events or ()]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return f"{listed} only when you’re ahead: work takes {'its' if len(names) == 1 else 'their'} time first"
    if r.kind == "night_before":
        return f"No work after {r.at} the night before {' or '.join(titled(e) for e in r.events or ())}"
    if r.kind == "pace":
        by_pace: dict[str, list[str]] = {}
        for day, pace in r.paces or ():
            by_pace.setdefault(pace, []).append(day)
        return ", ".join(f"{pace} on {days_spoken(tuple(days))}" for pace, days in by_pace.items())
    subject = "Work" if r.subject == "work" else r.subject[0].upper() + r.subject[1:]
    on = (" " + days_words(r.days)) if r.days else ""
    if r.kind == "window":
        if r.rel == "between":
            return f"{subject} between {r.at} and {r.until}{on}"
        if r.rel == "not_between":
            return f"No {r.subject} between {r.at} and {r.until}{on}"
        if r.subject == "work":  # "no work after 22:00" says it the way people do
            return f"No work {'after' if r.rel == 'before' else 'before'} {r.at}{on}"
        return f"{subject} {r.rel} {r.at}{on}"
    if r.kind == "days":
        return f"No {r.subject} {days_words(r.days)}" if r.rel == "not_on" else f"{subject} only {days_words(r.days)}"
    if r.kind == "free":
        when = f" {r.at}–{r.until}" if r.at else ""
        how = "lighter" if r.amount else "free"
        return f"Keep {days_words(r.days).removeprefix('on ') or 'every day'}{when} {how}"
    if r.kind == "cap":
        of = "" if r.subject == "work" else f" of {r.subject}"
        on = f" {days_words(r.days)}" if r.days else ""
        return f"At most {r.amount:g} h{of} a day{on}"
    if r.kind == "early":
        what, days = "things" if r.subject == "work" else r.subject, r.amount or 1
        if days != int(days):  # `36 hours early`
            return f"Finish {what} {days * 24:g} h before they're due"
        n = int(days)
        return f"Finish {what} {n} day{'s' if n > 1 else ''} before they're due"
    return f"{subject} right after {r.event}"


def buffer_said(minutes: int) -> str:
    """`1 day`, `2 days`, `12 hours`, `90 min`: as `read_close` reads it back."""
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} day{'s' if days > 1 else ''}"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{minutes} min"


def span_said(minutes: int) -> str:
    """45 min, 1 h, 90 min: as the rule is read back (`1 h 30` wasn't, 27 Oct)."""
    return f"{minutes // 60} h" if minutes and not minutes % 60 else f"{minutes} min"


# What students call the kinds: "no homework after 10pm" is about Assignments.
KIND_WORDS = {"homework": "Assignment", "hw": "Assignment", "problem set": "Assignment", "pset": "Assignment",
              "assignment": "Assignment", "reading": "Reading", "studying for exam": "Exam prep",
              "exam prep": "Exam prep", "studying for test": "Exam prep", "chore": "Chore",
              "errand": "Errand"}  # fmt: skip


def scope_of(subject: str, areas: list[str], presets: list[str]) -> dict[str, Any] | None:
    if subject == "work":
        return None
    if subject == "deep work":
        return {"energy": "deep"}
    if subject == "light work":
        return {"energy": "light"}
    if subject == "undated work":
        return {"dated": False}
    for a in areas:
        if a.lower() == subject:
            return {"area": a}
    for p in presets:
        if p.lower() in (subject, subject.rstrip("s")):
            return {"preset": p}
    kind = KIND_WORDS.get(subject) or KIND_WORDS.get(subject.rstrip("s"))
    if kind is not None and kind in presets:
        return {"preset": kind}
    return {"title": subject}


PRICE = {"Prefer": 2.0, "Strongly": 6.0}
SLEEP_PRICE = {"Prefer": 40.0, "Strongly": 120.0}  # an hour of it: twice and six times an hour past bedtime
FIT_GAPS = {"Prefer": 1.0, "Strongly": 3.0, "Always": 10.0}  # a price, never a wall: the right gap may not exist
MEAL_KEPT = 10000.0  # a quarter hour short of a kept meal: above what work a day or two late costs
# Always: above anything lateness can cost. A quarter hour of work due weeks ago and left off the plan costs about
# 1e5 (late_tasks grows with the square of the hours late), so 10000 lost to it (30 Oct: "i put having lunch and
# dinner as a must and it didn't schedule that").
MEAL_ALWAYS = 10_000_000.0
CLOSE_INSIDE = 10.0  # an hour inside the buffer you keep before a due: more than a week early costs
AHEAD_PRICE = 1.0  # among your preferences, below a Prefer rule: work takes it before late nights or broken rules
WEIGHT = {"Prefer": 1.0, "Strongly": 3.0, "Always": 10.0}


def spec(r: Reading, strength: Strength, name: str, areas: list[str], presets: list[str]) -> dict[str, Any]:
    """The planner rule for a reading: {type, name, weight, scope, reason, params}."""
    if r.kind == "optional":  # their time is priced, not walled off (build), so it goes only when work must
        return {"name": name, "type": "skippable", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": {"titles": list(r.events or ()), "price": 8.0}}  # fmt: skip
    if r.kind == "around":  # not a priced rule: the plan's build keeps that time around those events (planner.build)
        params = {"titles": list(r.events or ()), "before_min": r.before_min or 0, "after_min": r.after_min or 0}
        return {"name": name, "type": "travel", "weight": 0.0, "scope": None, "reason": sentence(r), "params": params}
    if r.kind == "ahead":  # priced among preferences, not wellbeing: work takes the time before any late night does
        params = {"titles": list(r.events or ()), "price": AHEAD_PRICE, "ahead": True}
        return {"name": name, "type": "skippable", "weight": 1.0, "stage": "preferences", "scope": None,
                "reason": sentence(r), "params": params}  # fmt: skip
    if r.kind == "night_before":
        price: Any = "forbid" if strength == "Always" else PRICE[strength]
        return {"name": name, "type": "before_event", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": {"titles": list(r.events or ()), "after": r.at, "price": price}}  # fmt: skip
    if r.kind == "deadlines":  # built in: `rule_add` makes sure it's on rather than adding a second one
        return {"name": "late_work", "type": "late_work", "weight": 10.0, "scope": None, "reason": sentence(r),
                "params": {}}  # fmt: skip
    if r.kind == "runs_while_working":  # Always: never started where it would run through an event or the night
        price = "forbid" if strength == "Always" else PRICE[strength]
        return {"name": name, "type": "runs_while_working", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": {"price": price}}  # fmt: skip
    if r.kind == "spacing":  # not a planner rule: the repeat's min_gap_days (commands/rules.py, planner/spacing.py)
        return {"name": name, "type": "spacing", "weight": 0.0, "scope": None, "reason": sentence(r),
                "params": {"title": r.subject, "days": r.amount}}  # fmt: skip
    if r.kind == "sleep_min":  # the hours before waking: priced above a late night, or never used (Always)
        price = "forbid" if strength == "Always" else SLEEP_PRICE[strength]
        params = {"hours": r.amount or 7.0, "price": price} | ({"days": list(r.days)} if r.days else {})
        return {"name": name, "type": "sleep_min", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": params}  # fmt: skip
    if r.kind == "fit_gaps":  # a preference, held harder the stronger you say it
        return {"name": name, "type": "fit_gaps", "weight": FIT_GAPS[strength], "scope": None, "reason": sentence(r),
                "params": {"price": 2.0}}  # fmt: skip
    if r.kind == "meals_kept":  # their minimum in the deadlines stage, priced far above work being late
        names = "|".join(named_meals(r)).replace("dinner", "dinner|supper").replace("lunch", "lunch|brunch")
        scope = {"preset": "Routine", "title_regex": [rf"(?i)\b({names})s?\b"]}
        return {"name": name, "type": "elastic_shortfall", "weight": 1.0, "stage": "deadlines", "scope": scope,
                "reason": sentence(r), "params": {"steep": MEAL_ALWAYS if strength == "Always" else MEAL_KEPT,
                                                  "gentle": 0.0}}  # fmt: skip
    if r.kind == "meals_learned":  # not a priced rule: each night the learned meal routines are planned or stopped
        return {"name": name, "type": "meal_learned", "weight": 0.0, "scope": None, "reason": sentence(r),
                "params": {"meals": list(named_meals(r))}}  # fmt: skip
    if r.kind == "close":  # each hour costs more the earlier it is; Always rules out the buffer before the due
        scope = scope_of(r.subject, areas, presets) or {}
        if r.events:
            scope = scope | {"title_regex": [title_words(r.events[0])]}
        inside: Any = "forbid" if strength == "Always" and r.before_min else CLOSE_INSIDE
        params = {"buffer_min": r.before_min or 0, "inside": inside}
        return {"name": name, "type": "close_to_due", "weight": WEIGHT[strength], "scope": scope or None,
                "reason": sentence(r), "params": params}  # fmt: skip
    if r.kind == "pace":  # a setting, not a planner rule: `rule_add` writes `pace.weekly`
        return {"name": name, "type": "pace", "weight": 0.0, "scope": None, "reason": sentence(r),
                "params": {"weekly": dict(r.paces or ())}}  # fmt: skip
    scope = scope_of(r.subject, areas, presets)
    price: Any = "forbid" if strength == "Always" else PRICE[strength]
    base = {"name": name, "scope": scope, "reason": sentence(r)}
    if r.kind == "window":
        # The hours to avoid: after `at` (for before), before it (for after), outside [at, until) (for between),
        # inside it (for not_between).
        start, end = {
            "before": (r.at, "04:00"),
            "after": ("04:00", r.at),
            "between": (r.until, r.at),
            "not_between": (r.at, r.until),
        }[r.rel or "before"]
        params = {"start": start, "end": end, "price": price} | ({"days": list(r.days)} if r.days else {})
        return base | {"type": "time_preference", "weight": 1.0, "params": params}
    if r.kind == "days":
        key = "days" if r.rel == "not_on" else "days_except"
        return base | {"type": "time_preference", "weight": 1.0, "params": {key: list(r.days or ()), "price": price}}
    if r.kind == "free":
        window = {"start": r.at, "end": r.until} if r.at else {}
        days = {"days": list(r.days)} if r.days else {}
        if strength == "Always" and not r.amount:
            return base | {
                "type": "time_preference",
                "weight": 1.0,
                "scope": None,
                "params": window | days | {"price": "forbid"},
            }
        hours = hours_between(r.at, r.until) if r.at and r.until else 24
        kept = round(hours * (r.amount or 1) * 4) / 4  # lighter: about half kept free, to the quarter hour
        return base | {
            "type": "reserve",
            "weight": WEIGHT[strength] * 2,
            "scope": None,
            "params": window | days | {"free": f"{kept:g}h"},
        }
    if r.kind == "cap":
        days = {"days": list(r.days)} if r.days else {}
        return base | {
            "type": "daily_load",
            "weight": WEIGHT[strength] * 5,
            "params": {"threshold": f"{r.amount:g}h"} | days,
        }
    if r.kind == "early":
        days = r.amount or 1
        return base | {
            "type": "finish_early",
            "weight": WEIGHT[strength],
            "params": {"days": int(days) if days == int(days) else days},
        }
    events = {"event_kind": "class"} if (r.event or "").rstrip("s") in ("class", "lecture") else {"title": r.event}
    params = {"events": events, "measure_from": "last", "slope": 1, "cap": 3}
    return base | {"type": "after_event", "weight": WEIGHT[strength], "params": params}


def title_words(words: str) -> str:
    """A title with all these words in it, any case and order: `math quiz` finds `Prep: Math 1920 Quiz 3`."""
    return "(?i)" + "".join(rf"(?=.*\b{re.escape(w)})" for w in words.split())


def hours_between(start: str, end: str) -> float:
    a = int(start[:2]) * 60 + int(start[3:])
    b = int(end[:2]) * 60 + int(end[3:])
    return ((b - a) % 1440) / 60


DAY_PART = r"(?:mornings?|afternoons?|evenings?|nights?)"
# Other ways to say what the readers read (27 Oct, from the sentences that went to Claude though one rule says them):
# each puts a phrasing into one a reader takes, so the readers stay as they are. (`spoken` applies them after PLAIN.)
WIDER = (
    (r"\b(?:school ?nights|weeknights|week nights)\b", "sun, mon, tue, wed and thu"),
    (r"\bduring the week\b", "on weekdays"),
    (r"\bfor (after|before)\b", r"\1"),  # "never plan anything for after 1 am"
    (
        rf"\b(?:on )?(?:[a-z]+ )?[a-z]+ \(({DAY_WORDS})\)",
        r"on \1",
    ),  # "on game days (saturdays)", "on shabbat (saturdays)"
    # A time put first: "after 10 at night nothing gets scheduled", "after 22:30 im done", "before 9am is off limits".
    (
        rf"^ ?(after|past|before|until) {TIME}( at night| in the evening| in the morning)?,? (?:nothing|no work"
        r"|no studying)(?: gets?| is| will be| should be| can be)?(?: scheduled| planned| happens?| done)? ?$",
        r" no work \1 \2\3 ",
    ),
    (
        rf"^ ?(after|past) {TIME},? (?:i'?m|i am) (?:done|finished|off|out|offline|off the clock)\b.*$",
        r" no work \1 \2 ",
    ),
    (
        rf"^ ?(before|after) {TIME} (?:is|are) (?:off limits|a no go|no go|off|blocked|sacred|protected|not allowed"
        r"|forbidden)\b.*$",
        r" no work \1 \2 ",
    ),
    (
        rf"\b(?:i )?(?:can't|cannot|don't|do not) (?:focus|think|function|work well|concentrate) (after|past|before) "
        rf"{TIME}\b.*$",
        r"no work \1 \2",
    ),
    (
        rf"\b(?:don't|do not|never|no) (?:start|begin)(?: work| working| studying| anything)? (?:until|till|before) "
        rf"{TIME}",
        lambda m: f"no work before {before_hour(m[1])}",
    ),
    # A range said with its part of the day: "between 3 and 4 in the afternoon", "from 9 to 10 at night".
    (
        rf"\b(from|between) {TIME} (to|and|-|–) {TIME} (?:in the afternoon|in the evening|at night|tonight|pm)\b",
        lambda m: f"{m[1]} {pm(m[2])} {m[3]} {pm(m[4])}",
    ),
    (
        rf"^ ?{DAY_WORDS} ((?!(?:mornings?|afternoons?|evenings?|nights?)\b)[a-z]+(?: [a-z]+)?) (?:only )?"
        r"(between|from|before|after|until|by) (.+?) ?$",
        r" \2 \3 \4 on \1 ",
    ),
    # Time kept light said other ways: "less work on sunday mornings", "ease up on saturday mornings".
    (
        rf"^ ?(?:less work|not much work|only a little work|ease up|go easy|go light|go lighter|lighten up|take it easy"
        r"|chill|fewer tasks"
        r"|less on my plate|ease off)(?: on)?"
        rf" (?:my )?(?:{DAY_WORDS} )?(mornings?|afternoons?|evenings?|nights?)\b(?: on {DAY_WORDS})?",
        lambda m: f" keep {m[1] or m[3] or ''} {m[2]} lighter",
    ),
    (
        rf"^ ?(?:keep )?(?:my )?({LIGHTER}) (mornings?|afternoons?|evenings?|nights?)(?: on {DAY_WORDS})? ?$",
        lambda m: f" keep {m[3] or ''} {m[2]} lighter ",
    ),
    (
        r"\b(?:block|block off|block out|set aside|reserve|hold) (.+?) (?:as|for) (?:free|me|personal|down) time\b",
        r"keep \1 free",
    ),
    (rf"\bblock off {DAY_WORDS} (?:from )?{TIME} ?(?:to|-) ?{TIME}\b", r"keep \1 from \2 to \3 free"),
    (rf"\bblock off ((?:{DAY_WORDS} )?{DAY_PART})\b(?! free| for)", r"keep \1 free"),
    (rf"\bkeep an empty hour from {TIME} ?(?:to|-) ?{TIME} on {DAY_WORDS}", r"keep \3 from \1 to \2 free"),
    (r"\bkeep the whole of ", "keep "),
    (rf"^ ?i want ((?:{DAY_WORDS} )?{DAY_PART}) left (?:empty|free|open|clear)\b", r" keep \1 free"),
    (
        rf"^ ?(?:my )?((?:{DAY_WORDS} )?{DAY_PART}) (?:are|is) protected,? keep (?:them|it) (?:clear|free|open)\b",
        r" keep \1 free",
    ),
    (rf"^ ?((?:{DAY_WORDS} )?{DAY_PART}) should be ({LIGHTER})\b", r" keep \1 \3"),
    (
        rf"^ ?(?:go easy|ease off|ease up)(?: a bit)? on (?:the |my )?((?:{DAY_WORDS} )?{DAY_PART})\b",
        r" keep \1 lighter",
    ),
    # The cutoff named with what it's for: "work cutoff is 10pm".
    (r"\b(?:work|study|studying|school|homework) (?=(?:cut ?-?off|hard stop|curfew)\b)", ""),
    (r"\b(?:totally|completely|entirely|fully|100%|absolutely) (?=free|clear|open|off)\b", ""),
    (r"\s=\s", " is "),
    (r"^ ?sleep in\s*[:,\-–]\s*", " "),
    (r"\bhit (?:up )?(?=the |my )", "go to "),
    (
        r"\b(?:eat|have|grab) (breakfast|brunch|lunch|dinner|supper)\b(?= (?:before|after|by|between|at|around|from|no "
        r"later|in the|on|every|no earlier)\b)",
        r"\1",
    ),
    (r"\b(breakfast|brunch|lunch|dinner|supper|meals) (is|are) a must\b", r"\1 \2 non-negotiable"),
    # Times said other ways: "no later than", "any earlier than", "my cutoff is", "the latest I'll study is".
    (r"\b(?:no|not) later than\b", "before"),
    (r"\b(?:no|not) earlier than\b", "after"),
    (r"\b(?:any )?earlier than\b", "before"),
    (r"\b(?:any )?later than\b", "after"),
    (
        r"\b(?:my |the |nightly |daily )?(?:cut ?-?off|hard stop|stopping time|stop time|end time|quitting time|curfew)"
        r"(?: time)?"
        r"(?: for (?:work|studying|study|homework|school))?(?: is| at|:)?\s*(?=\d|noon|midnight)",
        "no work after ",
    ),
    (
        r"\b(?:the )?latest (?:i'?(?:ll|d)? |i (?:can|will|would|should) )?(?:study|work|do (?:any )?work|be working"
        r"|stay up working|grind|do anything|go|be up working)(?: until)? is\b",
        "no work after",
    ),
    (
        r"\b(?:the )?earliest (?:i'?(?:ll|d)? |i (?:can|will|would|should) )?(?:study|work|start|do (?:any )?work"
        r"|be working|get going)(?: at)? is\b",
        "no work before",
    ),
    (r"\b(?:be |get |am )?(?:finished|done|wrapped up|through) with ([a-z ]+?) (?:by|before)\b", r"no \1 after"),
    (
        r"\b(?:i'?m|i am) (?:useless|dead|a zombie|brain[- ]?dead|not functional|no good|not productive|unproductive"
        r"|a mess|fried|cooked|not a morning person) (?:before|until)\b",
        "no work before",
    ),
    (
        r"\b(?:i'?m|i am) (?:useless|dead|a zombie|brain[- ]?dead|not functional|no good|not productive|unproductive"
        r"|a mess|fried|cooked) (?:after|past)\b",
        "no work after",
    ),
    (
        r"\b(?:i )?(?:start|begin)(?: work| working| studying| my day| the day| things)? (?:at|from|after) "
        r"(?=\d|noon)",
        "no work before ",
    ),
    (
        r"\b(?:treat (?:school|work|studying|it|uni|college) like|like) an? 9 ?(?:to|-|–) ?5(?: job| schedule| day)?\b",
        "work between 9am and 5pm",
    ),
    # Seen in a final unseen set (28 Oct): a time put first, "saturday's the exception", what a time is for.
    (rf"^ ?(?:anything|everything) (after|past|before) {TIME} (?:is|=) too (?:late|early)\b.*$", r" no work \1 \2 "),
    (r"\bi refuse to (?:do |work on )?(work|school|studying|homework)\b", r"no \1"),
    (
        rf"^ ?{TIME} ?(?:-|–|to) ?{TIME} is [a-z ]+? time,? (?:leave|keep) (?:work|it|everything) (?:out|free"
        rf"|clear)\b.*$",
        r" no work between \1 and \2 ",
    ),
    (
        rf"^ ?{TIME} ?(?:-|–|to) ?{TIME} is ([a-z ]*?(?:hw|homework|report|essay|reading|study|studying|pset"
        rf"|problem set"
        r"|lab|coding|writing|math|physics|chem|bio|orgo|review)[a-z ]*?) time ?$",
        r" \3 between \1 and \2 ",
    ),
    (
        rf",?\s*{DAY_WORDS}(?:'s| is| are) (?:the )?exceptions?\b|,?\s*{DAY_WORDS} excluded\b",
        lambda m: f" except {m[1] or m[2]}",
    ),
    (
        rf"^ ?(?:past|after) {TIME},? i (?:can't|cannot|can not|don't) (?:do|study|focus on|work on) ([a-z0-9 ]+?)"
        r"(?: anymore| any more)? ?$",
        r" no \2 after \1 ",
    ),
    (
        r"^ ?(?:i (?:like|want|need) )?(?:my )?((?:(?!\b(?:be|get|i|done|everything|must|to)\b)[a-z ])+?) (?:finished"
        r"|done"
        r"|over|wrapped up) (by|before) ",
        r" \1 \2 ",
    ),
    (
        rf"\b(?:keep|leave|hold) {TIME} ?(?:to|-|–) ?{TIME} (free|open|clear) on {DAY_WORDS}",
        r"keep \4 from \1 to \2 \3",
    ),
    (
        rf"^ ?{DAY_WORDS} {TIME} ?(?:-|–|to) ?{TIME} (?:stays?|is|are|should be|kept) (free|open|clear)\b.*$",
        r" keep \1 from \2 to \3 \4 ",
    ),
    (r"\bonly a little work\b", "less work"),
    (rf"^ ?keep {DAY_WORDS} {PACE} and {DAY_WORDS} {PACE} ?$", r" \2 on \1 and \4 on \3 "),
    (
        r"\bright before (?:they|it) (?:happen|happens|are|is)\b|\bright before (?:they'?re|it'?s) on\b",
        "as close to it as possible",
    ),
    (
        r",? minus (?:a |an )?(\d+|one|two|three)[ -]?(days?|hours?|hrs?) (?:breather|break|cushion|buffer|gap)\b",
        r" leaving \1 \2",
    ),
    (rf"^ ?pad (?:my )?([a-z ]+?) by {SPAN_OF} on (?:both|each|either) sides?\b.*$", r" \2 \3 before and after \1 "),
    # A tail that only gives the reason ("…, church", "…, long lab", "…, then im done") goes.
    (
        r"\s*,\s*((?:(?!\b(?:no|never|not|nothing|only|before|after|between|until|till|by|max|maximum|most|least|skip"
        r"|miss"
        r"|tops|ceiling|don't|do not|can't|won't|cut|drop|learn|decide|figure|track|plan|schedule|work|study|studying"
        r"|optional|keep|free|clear|open|light\w*|easy|hard\w*|heav\w*|push|grind|chill|cap|limit|except|unless|if|when"
        r"|each|both|every|(?:mon|tue|wed|thu|fri|sat|sun|week|morning|afternoon|evening|night)\w*|noon|midnight|hours?"
        r"|hrs?|mins?|minutes?|sleep|lunch|dinner|breakfast|meals?|ahead|behind|and|or|so|is|are|ever|outside|more|less"
        r"|leav\w*|day\w*|buffer|cushion|spare|early|late|first|last|then|due|after|before)\b)[a-z' ])+)\s*$",
        lambda m: m[0] if re.search(r"\d", m[1]) or len(m[1].split()) > 4 else " ",
    ),
    (r",?\s*nothing outside (?:that|those hours|of that)\b", ""),
    # The end of the day, said yet more ways.
    (
        rf"^ ?{TIME} is when (?:i )?(?:clock out|stop|log off|call it|am done|'m done|i'?m done)\b.*$",
        r" no work after"
        r" \1 ",
    ),
    (r"\b(?:please )?stop giving me (?:stuff|work|anything|things|tasks) (after|past|before)\b", r"no work \1"),
    (rf"\b(?:i )?turn into a pumpkin (?:at|after) {TIME}\b.*$", r"no work after \1"),
    (r"\b(?:i'?d|i would) rather not (?:be )?(?:working|studying|doing work)\b", "no work"),
    (r"\bnothing (?:should be |is |goes )?on my plate (after|before|past)\b", r"no work \1"),
    (
        rf"^ ?(?:past|after) {TIME}( at night)?,? (?:i'?m|i am) (?:useless|dead|fried|done|cooked)\b.*$",
        r" no work after \1\2 ",
    ),
    (r"\bkeep (?:all )?(?:my )?(?:work|studying) (before|after|between)\b", r"work \1"),
    (rf"^ ?{TIME} is (?:the )?(?:absolute )?latest\b", r" no work after \1"),
    (r"\bstop doing (?:school|work|homework|hw)\b", "stop working"),
    (r"\b(?:don't|do not) have me (?:working|studying|work)\b", "no work"),
    (r"\bschedule nothing\b", "nothing"),
    (r"\b(?:the )?day'?s work (?:wraps|ends|stops|is done)(?: up)? (?:at|by)\b", "no work after"),
    (
        rf"\b(?:the |my )?(?:day|work ?day) (?:doesn't|does not|won't) start (?:until|till|before) {TIME}",
        lambda m: f"no work before {before_hour(m[1])}",
    ),
    (
        rf"^ ?{TIME} is the (?:soonest|earliest) (?:i'?(?:ll|d)? |i can |i will |anything (?:should |can )?)?"
        r"(?:work|study|start|do anything)?\b.*$",
        r" no work before \1 ",
    ),
    (
        rf"^ ?i have a slow morning(?: routine)?,? so (?:nothing|no work) (?:until|till|til|before) {TIME}",
        lambda m: f" no work before {before_hour(m[1])}",
    ),
    (r"\bhold off on (?:any )?(?:work|studying|anything) (?:until|till)\b", "no work before"),
    (rf"^ ?schedule (?:me )?{TIME} ?(?:to|-|–) ?{TIME}\b", r" work between \1 and \2"),
    (r"\bwork happens\b", "work"),
    (rf"^ ?after {TIME},? before {TIME} ?$", r" work between \1 and \2 "),
    (rf"\b(?:i )?can'?t start (?:until|till|before) {TIME}", lambda m: f"no work before {before_hour(m[1])}"),
    (r"\bcut it off (?:at|by)\b", "no work after"),
    (r"\bwork (?:stops|ends) (?:at|by)\b", "no work after"),
    (rf"^ ?{DAY_WORDS},\s*(?=work\b)", r" on \1, "),
    (rf"^ ?((?:{DAY_WORDS} )?)(?:work hours|working hours|study hours|studying hours)\s*(?:are|is|:)\s*", r" \1 "),
    (r"\bstudying window\b", "work"),
    (r"\bkeep ([a-z ]+?) to (after|before)\b", r"\1 \2"),
    (r"\bonce (?:it hits|it'?s(?: past)?|it gets (?:to|past)|the clock hits)\b", "after"),
    (
        r"\bschedule (?:my )?([a-z ]+?) for (?:the )?(mornings?|afternoons?|evenings?|nights?)(?: only)?\b",
        r"\1 in the \2",
    ),
    (
        r"^ ?(?:night ?time|nights|late nights?) (?:is|are) for sleep(?:ing)?,? not ([a-z ]+?) ?$",
        r" no \1 in the"
        r" night ",
    ),
    # Days off, yet more ways.
    (rf"\b{DAY_WORDS},? (?:i'?m|i am) off the clock\b.*$", r"no work on \1"),
    (rf"\b{DAY_WORDS} (?:is|are) (?:my )?days? of rest\b", r"no work on \1"),
    (rf"^ ?work (?:six|6) days a week,? {DAY_WORDS} off\b.*$", r" no work on \1 "),
    (rf"\b{DAY_WORDS} (?:belong to me|are mine|is mine),? no ([a-z]+)\b", r"no \2 on \1"),
    (rf"\b{DAY_WORDS} (?:belong to me|are mine|is mine)\b", r"no work on \1"),
    (
        rf"^ ?every day except {DAY_WORDS} (?:is|are) (?:fine|ok|okay|good) for (?:work|studying)\b.*$",
        r" no work on"
        r" \1 ",
    ),
    (rf"^ ?{DAY_WORDS} only,? {DAY_WORDS} (?:are|is) (?:mine|off|free|for me)\b.*$", r" work only on \1 "),
    (
        rf"^ ?(?:save|keep|reserve) ([a-z0-9 ]+?) for (?:the )?{DAY_WORDS},? (?:never|not|no) (?:on )?{DAY_WORDS} ?$",
        r" \1 only on \2 ",
    ),
    # Limits, yet more ways.
    (
        rf"^ ?{SPAN_OF}( of [a-z ]+?)?( a day| per day| in a day| daily),? (?:that'?s|is) (?:my |the )?(?:ceiling|limit"
        r"|max(?:imum)?|cap)\b.*$",
        r" at most \1 \2\3 a day ",
    ),
    (
        rf"\b(?:anything|everything) (?:over|above|past|beyond|more than) {SPAN_OF}( a day| per day| daily)? (?:is|=) "
        r"too much\b",
        r"at most \1 \2 a day",
    ),
    (rf"\bceiling (?:of |is |:)?\s*{SPAN_OF}", r"at most \1 \2"),
    (r"\b(?:i )?max out at\b", "at most"),
    (rf"\bno (?:single |one )?day (?:should )?(?:have|get|go|be) (?:more than|over) {SPAN_OF}", r"at most \1 \2 a day"),
    (rf"^ ?{SPAN_OF} (?:a day|per day|daily) of ([a-z ]+?),? (?:max|tops|at most)\b", r" at most \1 \2 of \3 a day"),
    (
        rf"^ ?([a-z0-9 ]+?) for (?:no more than|at most|max(?:imum)?|up to|under) {SPAN_OF}( a day| per day| daily)",
        r" at most \2 \3 of \1 a day ",
    ),
    (
        rf"^ ?([a-z0-9 ]+?) (?:shouldn't|should not|can't|cannot|mustn't|won't) (?:go over|exceed|be more than"
        rf"|take more "
        rf"than|go past) {SPAN_OF}( a day| per day| daily)?",
        r" at most \2 \3 of \1 a day ",
    ),
    (
        rf"^ ?([a-z0-9 ]+?) gets {SPAN_OF}( a day| a night| per day| daily),? (?:max|tops|at most)\b",
        r" at most \2 \3"
        r" of \1 a day",
    ),
    (rf"^ ?([a-z ]+?),? (?:cap|limit) (?:it|them) (?:at|to) {SPAN_OF}", r" at most \2 \3 of \1"),
    (r"\bweekend days\b", "weekends"),
    (rf"\b(?:max|at most) {SPAN_OF} each\b", r"at most \1 \2 a day"),
    (r"\blimit me to\b", "at most"),
    (rf"\bkeep {DAY_WORDS} (?:under|below|to) {SPAN_OF}", r"at most \2 \3 a day on \1"),
    (r"\bkeep me (?:under|below|to)\b", "at most"),
    (r"\b(?:never more|not more)\s*$", " max"),
    # Finishing early, yet more ways.
    (r"\bwrapped\b(?= \d| a | one )", "done"),
    (
        r"\b(?:turn|hand) (?:stuff|things|everything|it all) in with (a|one|\d+) days? to spare\b",
        r"finish things \1"
        r" days early",
    ),
    (r"\ba full (week|day)\b", r"a \1"),
    (r"\bbuild in\b", "give myself"),
    (r"\bbeing done\b", "done"),
    (r"\bbefore (?:stuff|everything|things) is due\b", "before it's due"),
    (
        r"^ ?(?:i (?:like|want|need) )?(?:an? )?(\d+)[ -]?(?:hr|hour)s? (?:cushion|buffer|head start|margin) (?:on"
        r"|before|for) "
        r"(?:every |each |all |my )?(?:deadlines?|due dates?)\b.*$",
        r" finish things \1 hours early ",
    ),
    (
        r"^ ?(?:don't|do not|never) leave ([a-z ]+?) (?:till|until|to) the (?:due date|deadline"
        r"|last minute),? finish (?:them|it)"
        r" (\d+|a|one|two|three) days? (?:out|early|ahead|before)\b.*$",
        r" finish \1 \2 days early ",
    ),
    (
        r"^ ?([a-z0-9 ]+?) (?:finished|done|completed|submitted) the (?:day|night) before\b.*$",
        r" finish \1 1 day"
        r" early ",
    ),
    (r"^ ?(\d+) ?(hours?|hrs?|days?) (?:early|ahead) for ([a-z ]+?) ?$", r" finish \3 \1 \2 early "),
    # Deadlines first, yet more ways.
    (
        r"\bmissing (?:a |any )?(?:due date|deadline)s? (?:is not|isn't) (?:happening|an option|ok)\b"
        r"|\bon[- ]?time submissions? (?:above all(?: else)?|first|over everything)\b"
        r"|\b(?:i )?(?:have )?never turned in (?:late work|anything late)\b.*$"
        r"|\bdue dates? (?:are|is) (?:sacred|non[- ]?negotiable|everything|the priority)\b"
        r"|\bbefore letting (?:anything|work|things) go (?:overdue|late)\b",
        "don't let work be late",
    ),
    # Prep close to the exam, yet more ways.
    (
        r"^ ?([a-z ]+?),? (?:study|prep|review)(?: for (?:it|them))? (?:right|just) before\b.*$",
        r" prep for \1 as close to it as possible ",
    ),
    (
        r"\b(?:don't|do not|never) (?:start|begin) ([a-z ]*?(?:prep|studying|review)[a-z ]*?) (?:until|till) (?:right "
        r"|just )?"
        r"before (?:the |my )?([a-z ]+?) ?$",
        r"\1 as close to the \2 as possible",
    ),
    (r"\bleave ([a-z ]+?) (?:until|till|to) the last (?:possible )?(?:moment|minute)\b", r"\1 as late as possible"),
    (rf",? minus (?:a |an )?{SPAN_OF} (?:cushion|buffer)\b", r" leaving \1 \2"),
    # Time around events, yet more ways.
    (
        rf"^ ?(?:my )?([a-z ]+?) is an? {SPAN_OF} (?:bus |car |bike |train |subway |walking |walk |drive "
        rf"|ride )*(?:ride"
        rf"|walk"
        r"|drive|commute|trip) each way\b.*$",
        r" \2 \3 before and after \1 ",
    ),
    (rf"^ ?([a-z ]+?) (?:need|needs|take|takes) {SPAN_OF} (?:of [a-z]+ )?beforehand\b.*$", r" \2 \3 before \1 "),
    (
        rf"^ ?pad (?:my )?([a-z ]+?) with {SPAN_OF} before and {NUMBER}(?: ?({UNIT}))? after\b.*$",
        lambda m: f" {m[2]} {m[3]} before {m[1]} and {m[4]} {m[5] or m[3]} after ",
    ),
    (
        rf"^ ?{SPAN_OF} before (?:the |my )?([a-z ]+?)(?: to [a-z ]+)?,? {NUMBER}(?: ?({UNIT}))? after ?$",
        lambda m: f" {m[1]} {m[2]} before {m[3]} and {m[4]} {m[5] or m[2]} after ",
    ),
    (
        rf"\bit takes (?:me )?{SPAN_OF} to (?:get|walk|bike|drive|go)(?: over)? to (?:my |the )?([a-z0-9 ]+?) "
        rf"and {NUMBER}"
        rf"(?: ?({UNIT}))? back\b",
        lambda m: f"{m[1]} {m[2]} before {m[3]} and {m[4]} {m[5] or m[2]} after",
    ),
    # Work right after, events to skip and only when ahead, meals: yet more ways.
    (
        r"^ ?as soon as (?:my |the )?([a-z ]+?) (?:ends|is over|finishes|gets out),? (?:do|start|work on) (?:the "
        r"|my )?(.+?) ?$",
        r" \2 right after \1 ",
    ),
    (r"\b(?:isn't|is not|aren't|are not) (?:mandatory|required|necessary|compulsory)\b", "is optional"),
    (r"\b(?:is|are) (?:negotiable|expendable|droppable|cuttable)\b", "is optional"),
    (r"\bbail on\b", "skip"),
    (r"^ ?(.+?) is recorded so (?:i )?can (?:miss|skip) it\b.*$", r" \1 is optional "),
    (r"\bcan both be\b", "can be"),
    (r"^ ?unless (?:i'?m|i am) (ahead|caught up),? (?:skip|miss|drop) (.+?) ?$", r" skip \2 unless ahead "),
    (
        rf"\b(?:never|don't|do not) let (?:work|studying|school|anything) (?:bump|push|take|move|replace|cut|eat into"
        rf"|cut into) (?:my )?{MEALS}",
        r"never skip \1",
    ),
    (rf"\b(?:never|don't|do not) take away (?:my )?{MEALS}(?: for (?:work|studying))?", r"never skip \1"),
    (
        rf"^ ?(?:i )?always (?:eat|have) {MEALS},? (?:don't|do not|never) (?:schedule|plan|work) (?:through|over) "
        r"it\b.*$",
        r" never skip \1 ",
    ),
    (r"^ ?eating is (?:not optional|a must|mandatory),?\s*", " "),
    (
        rf"^ ?(?:i'?m |i am )?(?:inconsistent|unpredictable|all over the place) with {MEALS},? (?:let (?:friday|the app"
        r"|it) |just )?(?:work|figure) it out\b.*$",
        r" let friday decide \1 ",
    ),
    (rf"^ ?decide (?:if|whether) {MEALS} is a thing(?: for me)?\b.*$", r" let friday decide \1 "),
    (r"\blearn when\b", "learn when"),
    # Times kept out said other ways: "6 to 7:30pm is off limits for work", "afternoons are a no-study zone".
    (
        rf"^ ?(?:from )?{TIME} ?(?:to|-|–|until) ?{TIME} (?:is|are) (?:off limits|off the table|blocked|a no go|no go"
        r"|protected|sacred)\b.*$",
        r" no work between \1 and \2 ",
    ),
    (
        r"^ ?(mornings?|afternoons?|evenings?|nights?) (?:are|is) (?:an? )?(?:no (?:study|work|school) zone|off limits"
        r"|off the "
        r"table|work free|study free)\b.*$",
        r" no work in the \1 ",
    ),
    (
        rf"^ ?(?:mornings?|afternoons?|evenings?|nights?) (before|after) {TIME} (?:are|is) (?:off limits|off the table"
        r"|blocked|a no go|sacred|protected)\b.*$",
        r" no work \1 \2 ",
    ),
    (
        rf"\b(?:i )?(?:don't|do not|can't|cannot) (?:function|think|work|focus) (?:until|till|before) {TIME}\b.*$",
        lambda m: f"no work before {before_hour(m[1])}",
    ),
    (r"\b(?:the )?first (?:task|thing|block)(?: of the day)? (?=no earlier than|not before|after)", "work "),
    (
        r"\b(?:everything|all (?:my )?(?:work|studying)) (?:has to|needs to|should|must) (?:fit|happen|go|land|be) "
        r"(?=between|in|before|after)",
        "work ",
    ),
    (
        r"\ball (?:my )?(studying|work|homework) (?:should|has to|needs to|must)? ?(?:land|go|happen|be) "
        r"(?=in|between)",
        r"\1 ",
    ),
    (
        r"\b([a-z]+(?: [a-z]+)?) (?:goes|go|belongs?|lands?|happens?|should happen) (?=in the|between|before|after)",
        r"\1 ",
    ),
    (
        r"\b(breakfast|brunch|lunch|dinner|supper|workouts?|[a-z]+) (?:has|have) to (?:happen|be done|be|end|finish)"
        r"(?: by)? (?=before|by|after|between)",
        r"\1 ",
    ),
    (r"\b(dinner|lunch|breakfast|[a-z]+) (?:somewhere|sometime|anytime) (?=between)", r"\1 "),
    (
        r"\b(?:studying|work|homework|school) (?:has to|needs to|must|should) (?:end|stop|finish|be done) (?:by|at"
        r"|before) ",
        "no work after ",
    ),
    (r"\b(?:nightly |daily |my )?(?=cut ?-?off)", ""),
    (r"\b(?:don't|do not|never) book (?:any )?(?:work|anything|stuff)\b", "no work"),
    (
        r"\b(?:i )?(?:don't|do not|never) (?:open|touch|crack) (?:a |my |the )?(?:textbook|book|laptop|books)\b",
        "no work",
    ),
    (r"\bnada\b", "no work"),
    (r"\btotal work(?: per day| a day| each day)?\s*:?\s*", ""),
    (rf"^ ?past {SPAN_OF}( a day| per day| daily)?,? i (?:crash|burn out|die|fade)\b.*$", r" at most \1 \2 a day "),
    (
        rf"\b(?:keep it|keep things|keep work|keep my day) to {SPAN_OF}\b(?! ?(?:a |per |each )?week)",
        r"at most \1 \2"
        r" a day",
    ),
    (rf"^ ?{DAY_WORDS} (?:i'?(?:ll)? |i will )?do {SPAN_OF} (?:max|tops|at most)\b", r" at most \2 \3 a day on \1"),
    (rf"^ ?{DAY_WORDS}\s*:?\s*{SPAN_OF} (?:is|=) (?:the |my )?(?:most|max|limit)\b", r" at most \2 \3 a day on \1"),
    (
        r"\b(?:i'?d|i would) rather (?:pull a late night|stay up|work late|work longer) than (?:turn|hand|submit) "
        r"(?:something|anything|it|things|work) in late\b",
        "don't let work be late",
    ),
    (
        r"^ ?(?:when|if) (?:deadlines|work|things) (?:pile up|stack up|get heavy|get crazy),? (?:cut|drop|skip) (.+?)"
        r"(?: first)? ?$",
        r" skip \1 if there's too much work ",
    ),
    (r"\b(?:send|write|do|make|start) ([a-z ]+?) (?:right|straight|immediately) after\b", r"\1 right after"),
    (r"\bat least (?=\d+(?:\.\d+)? ?(?:hours?|hrs?|h)\b (?:early|before|ahead))", ""),
    (r"\b(?:fewer tasks|less on my plate|ease off)(?= on)", "less work"),
    (r"^ ?(?:lighter|light|lower) load in the (mornings?|afternoons?|evenings?|nights?) on ", r" keep \1 lighter on "),
    (
        rf"\b(?:hold|keep) {TIME} ?(?:to|-) ?{TIME} (open|free|clear) every (?:evening|night)\b",
        lambda m: f"keep from {pm(m[1])} to {pm(m[2])} {m[3]}",
    ),
    (r"^ ?([a-z0-9 ]+?):\s*(prep|studying|review)\b", r" \2 for \1"),
    (
        r"^ ?(?:after|past) {TIME} only (?:light|easy|mindless|low effort|brainless)\b.*$".replace("{TIME}", TIME),
        " only ",
    ),
    # The end of the day said other ways: "off the clock by 8pm", "I shut my laptop at 11", "my workday ends at 6:30pm".
    (r"\b(?:don't|do not|never) let me (?:work|study|do (?:any )?work|do anything)\b", "no work"),
    (r"\b(?:try )?not to (?:schedule|plan|work|study)(?: anything| stuff| work)?\b", "no work"),
    (r"\b(schedule|plan|book|put) me\b", r"\1"),
    (r"\bonce (?:it hits|it'?s|it gets to|the clock hits)\b", "after"),
    (r"\bno more (studying|work|homework|hw|school|schoolwork)\b", r"no \1"),
    (
        r"\b(?:be |get |i'?m |am )?(?:done|finished|through)(?: (?:with )?(?:work|working|studying|school|homework|hw"
        r"|everything|it all))?(?: for the (?:day|night))? (?:by|at|before) ",
        "no work after ",
    ),
    (
        r"\b(?:need to |i )?stop (?:all )?(?:work|working|studying|everything)?(?: for the (?:day|night))? ?(?:by|at"
        r"|around) "
        r"(?=\d|noon|midnight)",
        lambda m: m[0] if re.search(NIGHT_BEFORE_SAID, m.string) else "no work after ",
    ),
    (r"\b(?:be |get )?off the clock (?:by|at|before) ", "no work after "),
    (
        r"\b(?:i )?(?:shut|close) (?:my |the )?(?:laptop|books|computer|notebook)(?: down)? (?:at|by|around) "
        rf"{TIME}\b.*$",
        r"no work after \1",
    ),
    (
        rf"\b(?:shut it down|call it a (?:day|night)|log off|pack (?:it )?up) (?:at|by|around) {TIME}\b(?! (?:the )?"
        r"(?:night|evening|day) before)",
        r"no work after \1",
    ),
    (r"\b(?:finish up|wrap (?:everything |it all |things |stuff |work )?up) (?:by|before|at) ", "no work after "),
    (
        r"(?:\b(?:my |the )?(?:work ?day|work|day|studying|school day) )?\bends? (?:at|by) (?=\d|noon|midnight)",
        lambda m: m[0] if re.search(NIGHT_BEFORE_SAID, m.string) else " no work after ",
    ),
    (
        rf"\bmy brain (?:shuts? off|dies|quits|turns off|is done|stops working) (?:at|by|around|after) {TIME}\b.*$",
        r"no work after \1",
    ),
    (r"\b(?:i'?m|i am) (?:done|finished|off|out)(?: for the (?:day|night))? (?:at|by|after) ", "no work after "),
    (
        rf"^ ?{TIME} is the earliest (?:i'?(?:ll|d)? |i can |i will )?(?:work|study|start|do anything)\b.*$",
        r" no work before \1 ",
    ),
    (
        rf"^ ?{TIME} is the latest (?:i'?(?:ll|d)? |i can |i will )?(?:work|study|go|do anything)\b.*$",
        r" no work after \1 ",
    ),
    (r"\bmy (?:day|work ?day|workday|work|studying) (?:starts|begins) (?:at|around) ", "no work before "),
    (r"\bstart me (?:at|around) ", "no work before "),
    (
        r"^ ?(?:i'?m |mornings are |my mornings are )(?:slow|rough|bad|not great|not my thing"
        r"|a struggle)(?: for me)?,\s*",
        " ",
    ),
    (r",\s*(?:nothing|no work) (?:before|after)(?: that| then)?\s*$", " "),
    # Working hours said as a span: "my working hours are 10am-6pm", "work hours: 9 to 7", "work window is 7am to 3pm".
    (
        r"^ ?(?:my )?(?:working hours|work hours|work hrs|work window|study hours|study window"
        r"|studying hours)\s*(?:are|is"
        r"|:|=)\s*",
        " work ",
    ),
    (r"\bkeep (?:all )?(?:work|studying|everything) (?:inside|within|in|between)\b", "work"),
    (r"\bkeep (?:all )?(?:work|studying|everything|stuff) out of\b", "no work"),
    (r"^ ?only plan (work|studying|[a-z]+) from\b", r" \1 from"),
    (rf"^ ?(work|study|studying) {TIME} (?:thru|through|to|-|until) {TIME} only\b", r" work between \2 and \3"),
    (rf"\bwork (?:until|till) {TIME},? (?:then )?(?:stop|done|nothing after)\b", r"no work after \1"),
    # Kinds of work said other ways: "nothing that needs real focus", "the heavy brain stuff".
    (
        r"\b(anything|stuff|things|work|nothing)(?: that| which)? needs? (?:real |deep |a lot of |serious )?(?:focus"
        r"|concentration|brainpower|brain power|thinking)\b",
        lambda m: "no deep work" if m[1] == "nothing" else "deep work",
    ),
    (r"\b(?:the )?heavy brain stuff\b", "deep work"),
    (r"^ ?save ([a-z0-9 ]+?) for (?:the )?(mornings?|afternoons?|evenings?|nights?) ?$", r" \1 in the \2 "),
    (r"\bkeep ([a-z0-9 ]+?) to (?:the )?(mornings?|afternoons?|evenings?|nights?)\b", r"\1 in the \2"),
    (rf"^ ?([a-z0-9 ]+?) on {DAY_WORDS},? (after|before|by) {TIME} ?$", r" \1 \3 \4 on \2 "),
    # Both ends said apart: "nothing before 9:30am and nothing after 11pm" is work between them.
    (
        rf"\b(?:no work|nothing|no studying|no school) (?:before|until) {TIME},? (?:and|or|but|,) (?:no work |nothing "
        rf"|no studying |no school )?(?:after|past) {TIME}",
        lambda m: f"work between {before_hour(m[1])} and {after_hour(m[2])}",
    ),
    (
        rf"\b(?:no work|nothing|no studying|no school) (?:after|past) {TIME},? (?:and|or|but|,) (?:no work |nothing "
        rf"|no studying |no school )?(?:before|until) {TIME}",
        lambda m: f"work between {before_hour(m[2])} and {after_hour(m[1])}",
    ),
    # "DAYS: …", "DAYS - …": the days, put last where the readers look.
    (r"\bevery (?=(?:mon|tue|wed|thu|fri|sat|sun|week ?days?|week ?ends?)\w*\b)", ""),
    (rf"^ ?{DAY_WORDS}(?: {DAY_PART})?\s*[:\-–]\s*(.+?) ?$", r" \2 on \1 "),
    (
        rf"^ ?{DAY_WORDS} {TIME} ?(?:to|-|–|until|till) ?{TIME}\b(?! (?:stays?|is|are|should be|kept) (?:free|open"
        r"|clear|lighter))",
        r" work between \2 and \3 on \1",
    ),
    (
        rf"^ ?{DAY_WORDS} (?:i |i'll |i will )?(?=no work|nothing|stop|be done|done|finish|wrap up|end\b|don't|do not"
        rf"|never)",
        r" on \1, ",
    ),
    (
        rf"^ ?except (?:on |for )?{DAY_WORDS},? (?!(?:i'?m |i am )?(?:fine|ok|okay|happy|good) (?:working"
        rf"|to work))(.+?) ?$",
        r" \2 except \1 ",
    ),
    (rf"\bunless (?:it'?s|its|it is) (?:an? |the |on (?:an? |the )?)?{DAY_WORDS}", r"except \1"),
    (rf",? but (?:whenever|any ?time|whatever|anything goes|no rule|flexible) on {DAY_WORDS}", ""),
    # "X 9am to noon": a time to a time is between them (not "2 to 3 hours").
    (
        rf"(?<!from )(?<!between )(?<![\w:]){TIME} ?to ?{TIME}(?! ?(?:hours?|hrs?|h\b|minutes?|mins?|m\b|days?"
        rf"|pages?))",
        r"between \1 and \2",
    ),
    # Parts of the day said as a liking: "a morning thing", "afternoon is pset time".
    (
        r"^ ?([a-z0-9 ]+?) (?:is|are) (?:an? |my )?(morning|afternoon|evening|night) (?:thing|activity|task)s?\b",
        r" \1 in the \2",
    ),
    (
        r"^ ?(?:the )?(mornings?|afternoons?|evenings?|nights?) (?:is|are) (?:for )?(?:my )?([a-z0-9 ]+?)(?: time)? ?$",
        r" \2 in the \1 ",
    ),
    # Days kept free said other ways: "sundays are sacred", "calc stays off weekends", "save coding for the weekend".
    (
        rf"\b{DAY_WORDS} (?:are|is|=) (?:for )?(?:a |an |my |completely |totally |always )?(?:resting|rest|chilling"
        r"|relaxing|me|me time|myself|recovery|recharging|family|fun|friends|sacred|holy|off[- ]limits|untouchable"
        r"|protected|work[- ]?free|no ?work|no school|off|days? off|rest days?|off days?|free days?)(?: days?)?\b"
        r"(?:,? (?:not|no) (?:for )?(?:school|work|studying))?(?!.*\b(?:easy|easier|light|lighter|chill|slow)\b)",
        r"no work on \1",
    ),
    (rf"\b{DAY_WORDS} (?:are|is|=) no ([a-z]+)\b", r"no \2 on \1"),
    (rf"^ ?only do ([a-z0-9 ]+?) (?:on )?{DAY_WORDS} ?$", r" \1 only on \2 "),  # not "only light work on weekends"
    (rf"^ ?(?:keep|save|reserve) (?:the |my )?{DAY_WORDS} for ([a-z0-9 ]+?) ?$", r" \2 only on \1 "),
    (r"\b(?:don't|do not|never) make me (?:work|study|do (?:any )?work)\b", "no work"),
    (rf"\bi work on [^,]+?,? (?:but )?never (?:on )?{DAY_WORDS}", r"no work on \1"),
    (
        rf"^ ?except (?:on )?{DAY_WORDS},? (?:i'?m |i am )?(?:fine|ok|okay|happy|good) (?:working|to work|with work)"
        r"(?: (?:any ?day|whenever|every day))?\b.*$",
        r" no work on \1 ",
    ),
    (r"\bwork any ?day (?:but|except) ", "no work on "),
    (rf"(no work on {DAY_WORDS}),? (?:no|nothing) (?:school|work|studying|homework|hw|classes)\b", r"\1"),
    (
        rf"^ ?(no|never) ((?!(?:on|this|next|that|every)\b)[a-z]+(?: (?!(?:on|this|next|that|every)\b)[a-z]+)?)"
        rf" {DAY_WORDS} ?$",
        r" \1 \2 on \3 ",
    ),
    (rf"^ ?(?:keep )?([a-z0-9 ]+?) (?:stays? |is |are )?off (?:on )?{DAY_WORDS} ?$", r" no \1 on \2 "),
    (rf"^ ?(?:save|keep|reserve) ([a-z0-9 ]+?) for (?:the )?{DAY_WORDS} ?$", r" \1 only on \2 "),
    (
        r"^ ?(?:keep )?(weekdays) for (?:school|work|studying|classes|uni)(?:,? (?:and )?weekends? (?:for me|for fun"
        r"|free|off|for rest))?\b",
        r" work only on \1",
    ),
    # Words around a limit that say nothing of it: "dont give me more than", "only schedule up to".
    (
        r"\b(?:give me|schedule|plan|put|assign|let me do|have me do|make me do|book|do)\s+(?=(?:no |not )?"
        r"(?:more than|over \d|up to|at most|max|under \d|no more than)\b)",
        "",
    ),
    (rf"\bcap (?:my |the |each )?days? at\s*{SPAN_OF}", r"at most \1 \2 a day"),
    (
        r"\b(?:limit myself to|cap myself at|cap me at|cap (?:my |the )?(?:workload|work|load) at|max me at)\s*",
        "at most ",
    ),
    (
        rf"\bkeep (?:my days|each day|every day|the day|days|my day|my workload|the workload|it|things|work|stuff"
        rf"|everything) (?:to|under|below|at|at or "
        rf"under)\s*{SPAN_OF}(?: max(?:imum)?)?( of [a-z0-9 ]+?)?(?= |$)(?! ?(?:a |per |each )?week|weekly|total)",
        r"at most \1 \2\3 a day",
    ),
    (
        rf"\b(?:my )?(daily |upper )?(?:max(?:imum)?|limit|cap)( daily)?(?: (?:study|work|studying) (?:time|hours"
        rf"|load))?"
        rf"\s*(?:of|is|at|:|=)?\s*{SPAN_OF}(?=[ /])",
        lambda m: f"at most {m[3]} {m[4]}" + (" a day" if m[1] == "daily " or m[2] else ""),
    ),
    (
        rf"^ ?{SPAN_OF}( of [a-z0-9 ]+?)?(?: a day| per day| daily| each day|/day)? (?:is|=) (?:my |the |all )?"
        r"(?:absolute |hard |daily )?(?:limit|max(?:imum)?|cap|ceiling|most|all (?:i|you) can (?:do|handle|manage"
        r"|take))\b.*$",
        r" at most \1 \2\3 a day ",
    ),
    (rf"\b{SPAN_OF} (?:per|a|each) week\b", r"\1 \2 a week"),  # a week's limit is Claude's (weekly cap)
    (
        rf"\b(?:let )?(?:no|any|a|one) day (?:should )?(?:ever )?(?:go |be |get )?(?:over|above|past|beyond|more than) "
        rf"{SPAN_OF}",
        r"at most \1 \2 a day",
    ),
    (
        rf"\ba day'?s (?:work|load) (?:should )?(?:never )?(?:go |be |get )?(?:over|past|above|beyond|more than) "
        rf"{SPAN_OF}",
        r"at most \1 \2 a day",
    ),
    (
        rf"\b(?:i )?(?:burn out|crash|die|fade|fall apart|lose focus|get fried|am fried|i'm fried) (?:past|after"
        rf"|beyond|"
        rf"over) {SPAN_OF}( a day| per day| daily)?.*$",
        r"at most \1 \2 a day",
    ),
    (
        rf"^ ?([a-z0-9 ]+?) (?:capped|limited|maxed(?: out)?) (?:at|to) {SPAN_OF}( a day| per day| daily)?"
        r"(?! ?(?:a |per |each )?week)",
        lambda m: (
            f" at most {m[2]} {m[3]} a day on {m[1]}" if days_of(m[1]) else f" at most {m[2]} {m[3]} of {m[1]} a day"
        ),
    ),
    (rf"^ ?only {SPAN_OF}( of [a-z0-9 ]+?)?( a day| per day| daily)", r" at most \1 \2\3 a day"),
    # Finishing early said other ways: "lab reports done 2 days before the deadline", "papers done 1 week early".
    (
        r"^ ?(?!(?:start|begin|starting|beginning)\b)(?:i (?:like|want|need) )?(?:to )?(?:(?:get|have|wrap up|finish up"
        r"|be done with|knock out|turn in|hand in"
        r"|submit|complete|finish|do) )?(?:my )?([a-z0-9 ]+?):? (?:(?:should|must|need to|needs to|have to) be )?"
        r"(?:done |finished |completed |submitted |ready |in |wrapped up )?(?:at least )?"
        r"(a|one|\d+(?:\.\d+)?) (days?|d|weeks?|hours?|hrs?) (?:before (?:the |its |it's |their |they're |theyre "
        r"|things are |it is |they are )?(?:deadlines?|due dates?|due(?: day)?)|ahead of (?:the |its |their )?"
        r"(?:deadlines?|due dates?|time)|in advance|early|ahead)\b.*$",
        lambda m: (
            f" finish {m[1]} {m[2]} {'days' if m[3] == 'd' else 'hours' if m[3].startswith('hr') else m[3]} early "
        ),
    ),
    (
        r"\b(?:never|don't) (?:finish|submit|do|turn in) [a-z ]+? on the (?:due date|due day|deadline),? (?:always )?"
        r"(?:the )?day before\b.*$",
        "finish things 1 day early",
    ),
    (
        r"^ ?(?:i (?:like|want|need) )?(?:(?:having|to have|have|give myself|giving myself|keep|leave) )?(?:a |an )?"
        r"(a|one|two|three|\d+)[ -]?days?(?: of)? (?:cushion|buffer|slack|head start|margin|breathing room|leeway) "
        r"(?:on|before|for) (?:every |each |all |my )?(?:deadlines?|due dates?|things are due|assignments"
        r"|everything)\b.*$",
        lambda m: f" finish things {WORD_HOURS.get(m[1], 1 if m[1] == 'a' else m[1])} days early ",
    ),
    (
        r"^ ?(?:a )?(?:buffer|cushion|margin|head start) of (a|one|two|three|\d+) days? (?:on|before|for) (?:every "
        r"|each "
        r"|all |my )?(?:deadlines?|due dates?|assignments|everything)\b.*$",
        lambda m: f" finish things {WORD_HOURS.get(m[1], 1 if m[1] == 'a' else m[1])} days early ",
    ),
    (r"\bfinish ([a-z0-9 ]+?) with (a|one|\d+) days? to spare\b", r"finish \1 \2 days early"),
    (
        r"^ ?(?:i )?(?:never want to |don't want to |do not want to |never )?(?:submit|finish|turn in"
        r"|hand in)(?: things"
        r"| stuff| anything)? on the (?:due day|due date|deadline),? (?:give me|i want|i need|always)(?: a| one"
        r"| 1)? days?"
        r"(?: of (?:cushion|buffer|slack))?\b.*$",
        " finish things 1 day early ",
    ),
    # A day's limit said other ways: "6 hrs a day tops", "6 hour daily limit", "saturday cap: 4 hrs".
    (rf"\b(never|not|no) (?:over|above|beyond|past) (?=\d+(?:\.\d+)? ?{UNIT}\b)", r"\1 more than "),
    (
        rf"\b{SPAN_OF}( of [a-z0-9 ]+?)?( a day| per day| daily| each day| every day| in a day| in one day|/day)?"
        r",? ?(?:tops|max(?:imum)?|at most|at the most|or less|cap|limit|no more|and no more)\b(?: (?:a|per|each) day"
        r"| daily)?",
        lambda m: f"at most {m[1]} {m[2]}{m[3] or ''} a day",
    ),
    (
        rf"\b{NUMBER}[ -]?(hours?|hrs?|h)[ -](?:daily |a day |per day )?(?:limit|cap|max(?:imum)?)\b"
        r"(?: (?:per day|a day|daily))?",
        r"at most \1 \2 a day",
    ),
    (
        rf"^ ?{DAY_WORDS} (?:cap(?:ped)?(?: at)?|limit(?:ed)?(?: to)?|max(?:imum)?(?: of)?|at most|no more than|up to)"
        rf"\s*:?\s*{SPAN_OF}",
        r" at most \2 \3 a day on \1",
    ),
    (
        rf"\b(?:i )?(?:can )?only (?:handle|do|manage|work|study|focus|focus for|work for|study for|stand"
        rf"|get through) (?:about |around |maybe |up to )?{SPAN_OF}( of [a-z0-9 ]+?)?(?= (?:a|per|each) day| daily)",
        r"at most \1 \2\3",
    ),
    (
        rf"\b(?:let )?(?:any|a|one) day (?:go |be |get )?(?:over|above|past|beyond|more than) {SPAN_OF}",
        r"at most \1 \2 a day",
    ),
    (r"\bin (?:a|one|1|any) day\b|\bon any (?:one )?day\b", "a day"),
    (
        rf"\bkeep ([a-z0-9 ]+?) (?:under|below|to|at or under) {SPAN_OF}( a day| per day| daily| each day)",
        r"at most \2 \3 of \1 a day",
    ),
    (
        rf"^ ?([a-z0-9 ]+?) (?:max(?:imum)?|at most|tops|limit|cap)\s*:?\s*{SPAN_OF}( a day| per day| daily| each day)",
        lambda m: (
            f" at most {m[2]} {m[3]} a day on {m[1]}" if days_of(m[1]) else f" at most {m[2]} {m[3]} of {m[1]} a day"
        ),
    ),
    (r"\bat least (?=(?:a|one|\d+|two|three) (?:days?|weeks?)\b)", ""),
    (
        r"^ ?(?:submit|turn (?:things |stuff |everything |it all )?in|hand (?:things |stuff |everything |it all )?in)"
        r"(?: (?:things|stuff|everything|work|it all))? (a|one|\d+) (days?|weeks?) (?:early|ahead)\b",
        r" finish things \1 \2 early",
    ),
    # Time around events said other ways.
    (
        rf"\b(?:i )?need {SPAN_OF} to (?:bike|walk|drive|get|commute|travel|run|go|head|bus|ride|skate|scoot)"
        r"(?: over)? (?:to|for) (?:my |the )?([a-z0-9 ]+?) ?$",
        r"\1 \2 before \3",
    ),
    (
        rf"\b{SPAN_OF} before and {NUMBER} ?({UNIT})? after (?:my |the )?(.+?) ?$",
        lambda m: f"{m[1]} {m[2]} before {m[5]} and {m[3]} {m[4] or m[2]} after",
    ),
    (r"^ ?(?:shower|travel|commute|recovery|prep|change|changing|walking|driving) time\s*:?\s*(?=\d)", " "),
    (rf"({SPAN_OF} (?:after|before)) to [a-z ]+$", r"\1"),
    (rf"^ ?([a-z0-9 ]+?) (?:need|needs|take|takes|require|requires) {SPAN_OF} (after|before)\b.*$", r" \2 \3 \4 \1 "),
    (
        rf"\b{SPAN_OF} to (?:walk|bike|drive|get|go|commute|travel|run|bus|ride)(?: over)? (?:to|for) (?:my |the )?"
        rf"([a-z0-9 ]+?) and {NUMBER}(?: ?({UNIT}))? back\b",
        lambda m: f"{m[1]} {m[2]} before {m[3]} and {m[4]} {m[5] or m[2]} after",
    ),
    (
        rf"\b{SPAN_OF} to (?:walk|bike|drive|get|go|commute|travel|bus|ride)(?: over)? to (?:my |the )?([a-z0-9 ]+?) "
        r"and back\b",
        r"\1 \2 before and after \3",
    ),
    (
        rf"\bit takes (?:me )?{SPAN_OF} to (?:get|walk|bike|drive|go|commute|travel)(?: over)? to (?:my "
        rf"|the )?(.+?) ?$",
        r"\1 \2 before \3",
    ),
    (rf"^ ?before and after (?:my |the )?(.+?),? {SPAN_OF} each\b.*$", r" \2 \3 before and after \1 "),
    (rf"\b(?:buffer|pad|padding|cushion) {SPAN_OF} (around|before|after|before and after)\b", r"\1 \2 \3"),
    (rf"\bno work (?:for )?{SPAN_OF} (after|before|around)\b", r"\1 \2 \3"),
    (
        rf"\b(?:travel(?: time)?|commute|it'?s)\s*(?:is|:)?\s*{SPAN_OF} each way (?:to|for|from) (?:my |the )?(.+?) ?$",
        r"\1 \2 before and after \3",
    ),
    (
        rf"\b(?:travel(?: time)?\s*:?\s*)?{SPAN_OF} each way (?:to|for|from) (?:my |the )?(.+?) ?$",
        r"\1 \2 before and after \3",
    ),
    (
        rf"\b(?:padding|cushion|buffer|margin|room|gap) of {SPAN_OF} (around|before|after|before and after)\b",
        r"\1 \2 \3",
    ),
    (
        rf"^ ?after (?:my |the )?([a-z0-9 ]+?),? (?:i )?(?:need|want|like|take|give me) {SPAN_OF}\b.*$",
        r" \2 \3 after \1 ",
    ),
    # The night before said other ways.
    (
        r"\b(?:shut it down|call it|close the laptop|log off|stop|wrap up|wrap it up|end the day|be done|pack up)"
        rf" (?:at|by) {TIME} (?=(?:the )?(?:night|evening|day) before)",
        r"stop working at \1 ",
    ),
    (
        rf"^ ?(?:on )?the (?:night|evening|day) before (?:an? |my |the )?(.+?),? (?:no work|nothing|stop|stop working"
        rf"|wrap up|be done|done) (?:after|past|at|by) {TIME} ?$",
        r" stop working at \2 the night before \1 ",
    ),
    (
        rf"^ ?(?:when|whenever|if) (?:there'?s|there is|i'?ve got|i have|i've) (?:an? |my )?(.+?) (?:the )?(?:next "
        rf"(?:morning|day)|tomorrow),? (?:the (?:night|day|evening) before )?(?:ends?|stops?|stop working|wrap up"
        rf"|be done"
        rf"|done) (?:at|by) {TIME}",
        r" if have \1 the next day end at \2",
    ),
    # Finishing early said other ways.
    (
        r"\b(?:wrap up|finish up|be done with|have done|get done|knock out|turn in|hand in|submit|complete) "
        r"([a-z0-9 ]+?) (?:at least )?(a|one|\d+) (days?|d) (?:before|ahead of|prior to) (?:the |its |it's |their "
        r"|they're )?(?:deadline|due date|due|deadlines|due dates)\b",
        r"finish \1 \2 \3 early",
    ),
    (
        r"^ ?(everything|all work|all my work|it all|stuff) (?:done |finished |submitted |in )?(a|one|\d+) (days?|d) "
        r"(?:before|ahead of|prior to) (?:the |its |it's |their |they're )?(?:deadline|due date|due)\w*\b",
        r" finish things \2 \3 early",
    ),
    (
        r"^ ?(?:i (?:like|want|need|prefer|aim for|go for) )?(?:to (?:have|keep) )?(?:a |an )?(\d+|one|two|three)[ -]"
        r"days?(?: of)? (?:cushion|buffer|head start|margin) (?:on|before|for) (?:deadlines|due dates|everything"
        r"|my deadlines|assignments)\b.*$",
        lambda m: f" finish things {WORD_HOURS.get(m[1], m[1])} days early ",
    ),
    (
        r"^ ?no (?:submitting|turning (?:things |stuff |anything )?in"
        r"|last[- ]?minute submissions?)(?: at [0-9:]+(?:am|pm)?)?"
        r"\s*[,;]\s*",
        " ",
    ),
    (
        r"\bfinish (?:it |things |everything |work )?the (?:day|night) before\b(?! (?:an?|my|the) )",
        "finish things 1 day early",
    ),
    # Deadlines first said other ways.
    (
        r"\bno (?:late|overdue) (?:work|assignments?|tasks?|submissions?|stuff|things)\b(?: ever)?"
        r"|\bdeadlines (?:are|come) (?:non[- ]?negotiable|sacred|the top priority|priority one|everything|first)\b"
        r"|\b(?:meeting|hitting|making) (?:my )?deadlines (?:is|are) (?:the )?(?:top |number one |#1 )?priority\b"
        r"|\bprioritize not missing (?:due dates|deadlines)\b|\b(?:can't|cannot) (?:afford to )?miss (?:a |any )?"
        r"deadlines?\b|\blate is not an option\b|\b(?:everything|all (?:my )?work) on time\b",
        "don't let work be late",
    ),
    (r"\b(?:nothing|no work) (?:goes|is|gets|ends up|should go) (?:overdue|late)\b", "don't let work be late"),
    (
        r"\b(?:nothing|no work|no assignment|no assignments) (?:can|should|may|is allowed to) (?:ever )?be late\b"
        r"|\b(?:never|don't) miss (?:a |any )?deadlines?\b|\blate (?:submissions?|work|assignments?) (?:is|are) not an "
        r"option\b|\b(?:never|don't) (?:submit|turn in|hand in) anything late\b",
        "don't let work be late",
    ),
    # Prep as close as it can be, said other ways.
    (
        r"^ ?cram(?:ming)? for (?:the |my )?(.+?) (?:the night before|last minute|at the last minute"
        r"|right before)\b.*$",
        r" prep for \1 as close to it as possible",
    ),
    (
        r"\b(?:don't|do not|never|no) (?:study|studying|prep|prepping|review|reviewing)(?: for)? (?:the "
        r"|my )?(.+?) too "
        r"(?:early|soon|far (?:in )?advance|far ahead|long before)\b.*$",
        r"prep for \1 as close to it as possible",
    ),
    (r"\b(exam prep|prep|studying for exams) (?:at the )?last ?-?minute\b", r"\1 as late as possible"),
    (r"\bbut (?:leave|keep) the (?:final|last) day (?:before )?(?:free|clear|open|empty)\b", "leaving 1 day"),
    # Meals said other ways.
    (
        rf"\b(?:don't|never|do not) let (?:work|anything|studying|school) (?:eat into|cut into|take|interfere with|cut"
        rf"|steal|replace) (?:my )?{MEALS}",
        r"never skip \1",
    ),
    (
        rf"\bonly plan {MEALS} (?:if|when) (?:i )?(?:actually |usually |really )?(?:have|eat) (it|them)",
        r"plan \1 only if usually eat \2",
    ),
    (
        rf"^ ?(?:let )?friday (figures? out|decides?|learns?|works? out) (?:when|whether|if) (?:i )?(?:have "
        rf"|eat )?{MEALS}",
        r" let friday \1 \2",
    ),
    (
        r"^ ?sacrifice (?:the |my )?(.+?) (?:before|rather than) (?:letting|let) (?:work|anything|things|stuff)"
        r" (?:be|go|get|run) late\b.*$",
        r" \1 is optional ",
    ),
    (r"^ ?(.+?) (?:is|are) (optional|skippable)(?:,)? and so (?:is|are) (.+?) ?$", r" \1 and \3 are \2 "),
    # Time kept free said other ways: "leave saturday afternoons open", "protect my friday afternoons".
    (
        r"\b(?:leave|hold|block off|block out)\b(?= (?:my |the )?(?:mon|tue|wed|thu|fri|sat|sun|week|morning|afternoon"
        r"|evening|night))",
        "keep",
    ),
    (rf"\bprotect (?:my )?((?:{DAY_WORDS} )?{DAY_PART})\b", r"keep \1 free"),
    (
        rf"^ ?(?:my )?((?:{DAY_WORDS} )?{DAY_PART}) stays? (free|clear|open)\b",
        lambda m: f" keep {m[1]} {m.groups()[-1]}",
    ),
    (
        rf"^ ?i need (?:my )?((?:{DAY_WORDS} )?{DAY_PART}) (free|clear|open)\b.*$",
        lambda m: f" keep {m[1]} {m.groups()[-1]} ",
    ),
    (rf"\bkeep {TIME} ?(?:-|–|to) ?{TIME} on {DAY_WORDS} (free|clear|open|lighter)\b", r"keep \3 from \1 to \2 \4"),
    (
        rf"\b(keep (?:my )?(?:{DAY_WORDS} )?{DAY_PART}) for (?:me|myself|church|my job|family|friends|[a-z ]+?) ?$",
        r"\1 free",
    ),
    (r"\b(free|open|clear|empty) for (?:me|myself|church|my job|family|friends|my [a-z]+|[a-z]+) ?$", r"\1"),
    (r"\b(keep [a-z ]+?) empty\b", r"\1 free"),
    (r"\bon the lighter side\b", "lighter"),
    (
        rf"\bkeep (?:the hour |the time )?from {TIME} to {TIME} (open|free|clear) every (?:evening|night)\b",
        lambda m: f"keep from {pm(m[1])} to {pm(m[2])} {m[3]}",
    ),
    (
        rf"\b(?:don't|do not|never) (?:book|schedule|plan|put) (?:anything|stuff"
        rf"|work) on {DAY_WORDS} ({DAY_PART})\b.*$",
        r"keep \1 \2 free",
    ),
    # A weekly pace said other ways: "saturdays are for grinding", "make friday a light day", "take saturdays slow".
    (
        rf"\b{DAY_WORDS} (?:are|is) for (?:grinding|grind|pushing|hard work|getting stuff done|locking in)\b",
        r"push on \1",
    ),
    (rf"\bmake {DAY_WORDS} (?:an? )?{PACE} days?\b", r"\2 on \1"),
    (rf"^ ?keep {DAY_WORDS} {PACE}(?: days?)? ?$", r" \1 are \2 "),
    (rf"\btake {DAY_WORDS} (slow|easy|light|easier)\b", r"\2 on \1"),
    (rf"\b(?:grind|beast|push|lock ?in) mode (?:on )?{DAY_WORDS}", r"push on \1"),
    # Prep close to the exam said other ways: "exam prep right before the exam", "I like doing hw last minute".
    (r"\bright up (?:until|till)\b", "right up to"),
    (r"\b(?:right|just|immediately) before (?:they'?re|it'?s|its|theyre) due\b", "as late as possible"),
    (r"\b(?:right|just|immediately) before (?:them|it)\b", "as close to it as possible"),
    (r"\b(?:right|just|immediately) before (?:the |my |a |an )?([a-z0-9 ]+?) ?$", r"as close to the \1 as possible"),
    (r"^ ?save ([a-z0-9 ]+?) for right before (?:the |my )?([a-z0-9 ]+?) ?$", r" \1 as close to the \2 as possible "),
    (
        r"^ ?last[- ]?minute (studying|prep|review|cramming|reviewing) for (?:the |my )?([a-z0-9 ]+?)(?: works best"
        r"| is best"
        r"| is my thing)?\b.*$",
        r" \1 for \2 as close to it as possible ",
    ),
    (
        r"^ ?(?:i (?:like|prefer) )?(?:doing |do )?([a-z0-9 ]+?) (?:at the )?last[- ]?minute\b(?! but)",
        r" \1 as late as possible",
    ),
    (
        r"^ ?((?!\s*(?:no|never|nothing)\b)[a-z ]*?(?:prep|studying|study|review|reviewing|cramming|cram)[a-z ]*?) the "
        r"(?:day|night) before "
        r"(?:the |my |an? )?([a-z0-9 ]+?) ?$",
        r" \1 as close to the \2 as possible ",
    ),
    (r"\btoo far (?:in )?advance\b|\btoo far ahead\b|\btoo long before\b", "too early"),
    (
        r"\bbut (?:leave|keep) (?:a|one|the (?:final|last)|the last (?:\d+|two"
        r"|three)) (?:full )?days? (?:before )?(?:free"
        r"|clear|open|empty)\b",
        lambda m: (
            "leaving "
            + (
                "2 days"
                if re.search(r"\b(?:2|two)\b", m[0])
                else "3 days"
                if re.search(r"\b(?:3|three)\b", m[0])
                else "1 day"
            )
        ),
    ),
    (rf"\bbut (?:leave|keep) {SPAN_OF} (?:free|clear|open)(?: before)?\b", r"leaving \1 \2"),
    # Work right after an event said other ways: "orgo hw immediately after orgo lecture", "after lecture I review".
    (r"\b(?:immediately|directly|straight away) after\b", "right after"),
    (r"\bas soon as (?:i )?(?:get back|get home|am back|i'?m back|leave|get out) (?:from|of)\b", "right after"),
    (
        r"^ ?(?:right |straight |just )?after (?:my |the )?((?![0-9])[a-z0-9 ]+?),? (?:do|start|work on|knock out) "
        r"(?:the |my )?(.+?) ?$",
        r" \2 right after \1 ",
    ),
    (
        r"^ ?after (?:my |the )?((?![0-9])[a-z0-9 ]+?),? (?:i )?((?!no\b|nothing\b|never\b|don't\b)[a-z ]+?)"
        r"(?: right away| immediately| straight away)? ?$",
        r" \2 right after \1 ",
    ),
    (r"^ ?start ([a-z0-9 ]+?) right after\b", r" \1 right after"),
    # Events that give way to work, said other ways.
    (r"^ ?(?:it'?s |its )?(?:fine|ok|okay|alright) (?:to|if i) (skip|miss|drop)\b", r" \1"),
    (r"^ ?ok to (skip|miss|drop)\b", r" \1"),
    (
        r"^ ?(?:the |my )?((?:(?!as late as|as close)[a-z0-9' ])+?) can (?:go|be bumped|give way|be cut|be sacrificed"
        r"|wait)\b(?! as)[a-z' ]*$",
        r" \1 can be skipped ",
    ),
    (
        r"^ ?(?:the |my )?((?!\s*(?:readings?|assignments?|essays?|psets?|problem sets?|homework|hw|projects?|papers?"
        r"|discussion posts?|lab reports?|quizzes|exams?) (?:is|are)\b).+?) (?:is|are) the first (?:thing|things|to go"
        r"|to be cut)[a-z' ]*$",
        r" \1 can be skipped ",
    ),
    (r"^ ?(?:don't|do not) protect (?:my |the )?(.+?)(?: time)? (?:if|when)\b.*$", r" \1 can be skipped "),
    # Events only when ahead, said other ways.
    (r"\b(?:rarely|seldom|hardly ever|almost never|barely ever) (?:go to|attend|make it to)\b", "usually skip"),
    (
        r"^ ?(?:the |my )?(.+?) (?:are|is) (?:a |my )?reward for (?:being )?(?:ahead|caught up|on top of[a-z ]*)\b.*$",
        r" \1 only if ahead ",
    ),
    (
        r"^ ?(?:the |my )?(.+?) (?:is|are) only for (?:weeks|days|times) (?:when )?(?:i'?m |i am )?(ahead"
        r"|caught up)\b.*$",
        r" \1 only if ahead ",
    ),
    # Meals kept and learned, said other ways.
    (
        rf"^ ?(?:always )?(?:eat|have) {MEALS},? (?:no matter (?:how|what)[a-z' ]*|even (?:when|if) [a-z' ]+)$",
        r" never skip \1 ",
    ),
    (
        rf"\b(?:never|don't|do not) (?:cut into|eat into|schedule over|work through|skip|sacrifice) (?:my |a "
        rf"|an )?{MEALS}"
        r"(?: for (?:work|studying|anything|school))?\b",
        r"never skip \1",
    ),
    (
        rf"\b(?:work|studying|anything|school) (?:can't|cannot|shouldn't|won't) (?:take|eat into|cut into"
        rf"|replace) (?:my )?"
        rf"{MEALS}",
        r"never skip \1",
    ),
    (
        r"\b(?:i need to |always )?eat (?:three|3|all (?:my|three)) meals(?: a day)?,? (?:don't|never) (?:cut"
        r"|skip) (?:any|them)\b",
        "never skip meals",
    ),
    (rf"\bmake sure (?:i )?(?:always )?(?:have|eat|get) {MEALS}", r"never skip \1"),
    (rf"^ ?{MEALS} (?:stay|stays|are kept|are protected|stay put)\b.*$", r" never skip \1 "),
    (rf"\bno skipping {MEALS}(?: to (?:study|work))?", r"never skip \1"),
    (
        rf"\b(?:let )?(?:the app|friday|it|you) (?:learn|decide|figure out|work out|track)s? (?:my "
        rf"|when i (?:usually )?"
        rf"(?:have|eat) )?{MEALS}(?: times?)?\b",
        r"let friday decide \1",
    ),
    (rf"^ ?track (?:whether|if|when) (?:i )?(?:eat|have) {MEALS}\b.*$", r" let friday decide \1 "),
    (
        rf"\bonly (?:plan|schedule) {MEALS} (?:if|when) (?:i )?(?:actually |usually |really )?(?:have|eat) (it|them)",
        r"plan \1 only if usually eat \2",
    ),
    (
        rf"\b(?:don't|do not|never) (?:plan|schedule) {MEALS} unless (?:i'?m |i am |i )?(?:actually "
        rf"|really )?(?:eating|having"
        r"|eat|have) (it|them)\b",
        r"plan \1 only if usually eat \2",
    ),
    (r"\bfigure out when (?:i )?(?:eat|have meals)\b", "figure out when have meals"),
    (
        rf"\b(?:idk|i don't know) when (?:i )?(?:eat|have) {MEALS},? (?:just )?(?:learn|figure out|track) it\b",
        r"let friday decide \1",
    ),
    # Things that run by themselves: "…while I'm working, never overnight": where they mustn't run, said again.
    (
        r"(\b(?:while|when|during) [a-z' ]+?),? (?:but )?(?:never|not) (?:during|in|at|while i'?m|when i'?m"
        r"|overnight)\b[a-z' ]*$",
        lambda m: m[1] if re.search(rf"{RUNNING_NAMED}|{RUNNING}|\bruns?\b|\bstart\b", m.string) else m[0],
    ),
    (r"\bi need my (\d+(?:\.\d+)?) (?:hours|hrs)\b", r"\1 hours of sleep"),
    # A busy week said as "when": "when I'm swamped, miss swim".
    (r"^ ?(?:when|whenever) (i'?m|i am|it'?s|things are|work is|the week is) ", r" if \1 "),
    # Things that run by themselves, said by name: "laundry only runs while I'm home working, never during class".
    (
        r"^ ?([a-z]+) (?:only )?runs? (?:only )?(?:while|when) (?:i'?m |i am )?(?:home |at home |here )?(working"
        r"|at my desk)"
        r"(?:,? (?:and )?(?:never|not) (?:during|in|at) [a-z ]+)?",
        r" things that run by themselves only while \2",
    ),
    # A first clause that only sets up the rule: "i don't do mornings, nothing before 10", "no all day grinding, …".
    (r"^ ?(?:i )?(?:don't do|do not do|hate|can't do|no) (?:early )?mornings,? (?:so )?", " "),
    (r"^ ?(?:please )?no (?:all[- ]day|marathon) (?:grinding|work|studying|sessions?)\s*[,;]\s*(?=\S)", " "),
    (r"\s*[,;:–-]+\s*$", " "),  # what a removed reason left behind
)


DETERMINERS = r"(?:(?:an?|my|the|big|any|important)\s+)*(?:\d{1,2} ?(?:am|pm) )?"
STOPS_AT = (
    rf"\b(?:no work|nothing|no studying|no late work|stop(?: working| work| studying)?|end(?: work| the night"
    rf"| the day)?"
    rf"|work ends|ends?|done|be done|cut ?off(?: is)?|wrap(?: it)? up|shut it down|lights out)(?: (?:after|past|at|by"
    rf"|is))? {TIME}"
)


def night_before_said(t: str) -> str:
    """The night before an event said any way ("night before a midterm: no work after 9:30", "if I have a race the
    next morning, nothing after 9", "eve of a big exam: nothing past 10:30"), put the way `read_night_before` reads
    it: "stop working at 9:30 the night before midterm"."""
    event = (
        re.search(
            rf"\b(?:the )?(?:nights?|days?|evening|eve) (?:before|of) {DETERMINERS}([a-z][a-z ]*?)(?=\s*[:,]"
            r"|\s+(?:no|nothing|stop|end|ends|done|be done|work|cut ?off|wrap|shut)\b)",
            t,
        )
        or re.search(
            rf"\b(?:if|when|whenever) (?:i'?ve got|i have|i've|there'?s|there is|i'?m going to|i got) "
            rf"{DETERMINERS}([a-z][a-z ]*?) (?:the )?(?:next (?:day|morning)|following (?:day|morning)"
            r"|in the morning)\b",
            t,
        )
        or re.search(
            rf"\b(?:if|when) {DETERMINERS}([a-z][a-z ]*?) (?:is|'s) (?:the )?(?:next (?:day|morning)"
            r"|following (?:day|morning)|in the morning)\b",
            t,
        )
        or re.search(rf"^ ?{DETERMINERS}([a-z][a-z ]*?) (?:in the morning|the next (?:day|morning)|early) means\b", t)
        or re.search(r"\bbefore (?:an? |my )?([a-z]+) day\b", t)
    )
    at = event and re.search(STOPS_AT, t[event.end() :]) or (event and re.search(STOPS_AT, t[: event.start()]))
    if not event or not at:
        return t
    return f" stop working at {at[1]} the night before {event[1].strip()} "


# Compiled once: the tables hold more patterns than `re` caches (512), and a sentence read in halves runs them all
# again, so left as text each would be compiled over and over (27 Oct: 70 ms a sentence).
PLAIN = tuple((re.compile(p), put) for p, put in PLAIN)
WIDER = tuple((re.compile(p), put) for p, put in WIDER)
EARLY_SAID = tuple((re.compile(p), put) for p, put in EARLY_SAID)
SAID_AS = tuple((re.compile(p), put) for p, put in SAID_AS)
LATE_SAID = tuple((re.compile(p), put) for p, put in LATE_SAID)
