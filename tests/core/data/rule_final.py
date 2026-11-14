"""A final held-out set of rule sentences a college student might type into Friday's Rules box, written 28 Oct after
the grammar was tuned on rule_sentences.py, rule_wordings.py and rule_heldout.py, and never used to tune it: it measures
honestly how the reader does on new wording. Nobody tunes on it. Each is labeled with what the writer means, judged by
hand and never by running Friday's reader. None repeat, or are a word swap of, any of the three earlier sets.

Labels follow the module docstrings of rule_sentences.py, rule_wordings.py and rule_heldout.py exactly (the same `want`
forms, the same conventions, including `sleep_min`), and where those are silent:
  - "brain-intensive", "mentally heavy" work is "deep work"; "busywork" and "brainless stuff" are "light work";
    "test studying", "cramming for exams" and study guides done for an exam are "exam prep".
  - "study for <course code>" is the course ("chem 1210").
  - "X is the only night I'll work past T" is the rule on the other days; "X's the exception" / "X excluded" too.
  - "the walk to X is N minutes" is before X only, like "to get to X".
  - "start at A, end at B" on some days is one window between A and B.
  - "less packed", "a bit lighter", "shouldn't be stacked", "only a little work" on a part of a day are `free` with
    amount 0.5.
  - "I skip most of X", "I don't usually go to X" are `ahead`, like "I usually skip X".
"""

C = [
    # ---- windows: when work ends ----
    (
        "window",
        "my brain clocks out around 10:15 so dont schedule past that",
        {"kind": "window", "subject": "work", "rel": "before", "at": "22:15"},
    ),
    (
        "window",
        "nothing on the calendar after 9:40pm thx",
        {"kind": "window", "subject": "work", "rel": "before", "at": "21:40"},
    ),
    (
        "window",
        "Absolutely no studying once it's 11:30 or later!!",
        {"kind": "window", "subject": "work", "rel": "before", "at": "23:30"},
    ),
    ("window", "I refuse to do school after 10", {"kind": "window", "subject": "work", "rel": "before", "at": "22:00"}),
    (
        "window",
        "last task of the day has to end by 8:45 pm",
        {"kind": "window", "subject": "work", "rel": "before", "at": "20:45"},
    ),
    ("window", "work ends at 2130 sharp", {"kind": "window", "subject": "work", "rel": "before", "at": "21:30"}),
    (
        "window",
        "pls nothing past a quarter to ten, i'm a grandpa",
        {"kind": "window", "subject": "work", "rel": "before", "at": "21:45"},
    ),
    (
        "window",
        "I don't do anything productive after 12:15am so stop there",
        {"kind": "window", "subject": "work", "rel": "before", "at": "00:15"},
    ),
    ("window", "Done-zo by 10:00 PM every day", {"kind": "window", "subject": "work", "rel": "before", "at": "22:00"}),
    (
        "window",
        "dont book me any studying later than half past 11",
        {"kind": "window", "subject": "work", "rel": "before", "at": "23:30"},
    ),
    ("window", "11pm and later = NOTHING. ok?", {"kind": "window", "subject": "work", "rel": "before", "at": "23:00"}),
    (
        "window",
        "nite cutoff is 10, dont scheduel past it",
        {"kind": "window", "subject": "work", "rel": "before", "at": "22:00"},
    ),
    (
        "window",
        "anything after 21:15 is too late for me",
        {"kind": "window", "subject": "work", "rel": "before", "at": "21:15"},
    ),
    # ---- windows: when work may start ----
    (
        "window",
        "I'm not human until 9:30, so nothing earlier",
        {"kind": "window", "subject": "work", "rel": "after", "at": "09:30"},
    ),
    (
        "window",
        "don't put anything on my plate before 7:45am",
        {"kind": "window", "subject": "work", "rel": "after", "at": "07:45"},
    ),
    ("window", "no tasks prior to 10 a.m.", {"kind": "window", "subject": "work", "rel": "after", "at": "10:00"}),
    (
        "window",
        "earliest I'm willing to crack a book is 8",
        {"kind": "window", "subject": "work", "rel": "after", "at": "08:00"},
    ),
    (
        "window",
        "my mornings start late, keep work after 11:30am",
        {"kind": "window", "subject": "work", "rel": "after", "at": "11:30"},
    ),
    ("window", "dont gimme anything til 1030", {"kind": "window", "subject": "work", "rel": "after", "at": "10:30"}),
    ("window", "no studdying b4 quarter past 9", {"kind": "window", "subject": "work", "rel": "after", "at": "09:15"}),
    (
        "window",
        "work can start from 7:30am, no earlier",
        {"kind": "window", "subject": "work", "rel": "after", "at": "07:30"},
    ),
    # ---- windows: a range ----
    (
        "window",
        "i'm productive from 10am to 6pm, keep work in there",
        {"kind": "window", "subject": "work", "rel": "between", "at": "10:00", "until": "18:00"},
    ),
    (
        "window",
        "studying happens 0830-1630 and not outside it",
        {"kind": "window", "subject": "work", "rel": "between", "at": "08:30", "until": "16:30"},
    ),
    (
        "window",
        "only between eight in the morning and eight at night",
        {"kind": "window", "subject": "work", "rel": "between", "at": "08:00", "until": "20:00"},
    ),
    (
        "window",
        "1pm–9pm is when I get stuff done",
        {"kind": "window", "subject": "work", "rel": "between", "at": "13:00", "until": "21:00"},
    ),
    (
        "window",
        "noon to 8pm, those are my hours",
        {"kind": "window", "subject": "work", "rel": "between", "at": "12:00", "until": "20:00"},
    ),
    (
        "window",
        "8:30am start, 9:30pm finish",
        {"kind": "window", "subject": "work", "rel": "between", "at": "08:30", "until": "21:30"},
    ),
    (
        "window",
        "I'm a morning person: work 6am-2pm",
        {"kind": "window", "subject": "work", "rel": "between", "at": "06:00", "until": "14:00"},
    ),
    # ---- windows: a stretch kept out of work ----
    (
        "window",
        "between 1:15 and 2 pm, no tasks please",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "13:15", "until": "14:00"},
    ),
    (
        "window",
        "no work 4:30 to 5:30, i walk my dog",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "16:30", "until": "17:30"},
    ),
    (
        "window",
        "7–8pm is family call time, leave work out of it",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "19:00", "until": "20:00"},
    ),
    (
        "window",
        "between midnight and 9am, no studying, ever",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "00:00", "until": "09:00"},
    ),
    # ---- windows: a part of the day ----
    (
        "window",
        "afternoon = crash time, so no studying then",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "12:00", "until": "17:00"},
    ),
    (
        "window",
        "school stays out of my evenings",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "17:00", "until": "22:00"},
    ),
    (
        "window",
        "nighttime work is a no for me",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "22:00", "until": "02:00"},
    ),
    (
        "window",
        "get all my studying done in the AM",
        {"kind": "window", "subject": "work", "rel": "between", "at": "08:00", "until": "12:00"},
    ),
    # ---- windows with days ----
    (
        "window_days",
        "sun-thurs cut off at 10:30",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "22:30",
            "days": ["mon", "tue", "wed", "thu", "sun"],
        },
    ),
    (
        "window_days",
        "11:15 is the latest on weeknights",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "23:15",
            "days": ["mon", "tue", "wed", "thu", "sun"],
        },
    ),
    (
        "window_days",
        "I head home early on fridays, so wrap up by 2pm",
        {"kind": "window", "subject": "work", "rel": "before", "at": "14:00", "days": ["fri"]},
    ),
    (
        "window_days",
        "on saturdays I sleep in, nothing until 11:30",
        {"kind": "window", "subject": "work", "rel": "after", "at": "11:30", "days": ["sat"]},
    ),
    (
        "window_days",
        "MWF evenings, I stop studying at 8:30",
        {"kind": "window", "subject": "work", "rel": "before", "at": "20:30", "days": ["mon", "wed", "fri"]},
    ),
    (
        "window_days",
        "on tue/thu I keep work inside 8am–3pm",
        {
            "kind": "window",
            "subject": "work",
            "rel": "between",
            "at": "08:00",
            "until": "15:00",
            "days": ["tue", "thu"],
        },
    ),
    (
        "window_days",
        "sat+sun I'm only available 2 to 6pm for school",
        {
            "kind": "window",
            "subject": "work",
            "rel": "between",
            "at": "14:00",
            "until": "18:00",
            "days": ["sat", "sun"],
        },
    ),
    (
        "window_days",
        "I bartend thursday nights so no work after 6pm on thursdays",
        {"kind": "window", "subject": "work", "rel": "before", "at": "18:00", "days": ["thu"]},
    ),
    (
        "window_days",
        "weekends I'm lazy in the morning, so not a thing till 12:30",
        {"kind": "window", "subject": "work", "rel": "after", "at": "12:30", "days": ["sat", "sun"]},
    ),
    (
        "window_days",
        "M–F: studying ends at 9:45pm",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "21:45",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        },
    ),
    (
        "window_days",
        "wednesdays 1pm-5pm no work, I have lab",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "13:00", "until": "17:00", "days": ["wed"]},
    ),
    (
        "window_days",
        "on tuesdays don't schedule anything between 3 and 4:30",
        {"kind": "window", "subject": "work", "rel": "not_between", "at": "15:00", "until": "16:30", "days": ["tue"]},
    ),
    (
        "window_days",
        "mon thru thurs I study 7pm to midnight",
        {
            "kind": "window",
            "subject": "work",
            "rel": "between",
            "at": "19:00",
            "until": "00:00",
            "days": ["mon", "tue", "wed", "thu"],
        },
    ),
    (
        "window_days",
        "weekends: start at 11, end at 6",
        {
            "kind": "window",
            "subject": "work",
            "rel": "between",
            "at": "11:00",
            "until": "18:00",
            "days": ["sat", "sun"],
        },
    ),
    (
        "window_days",
        "eleven pm is my school-night cutoff",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "23:00",
            "days": ["mon", "tue", "wed", "thu", "sun"],
        },
    ),
    # ---- windows with days, said as exceptions ----
    (
        "window_except",
        "friday night is the only night I'll work past 10:30",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "22:30",
            "days": ["mon", "tue", "wed", "thu", "sat", "sun"],
        },
    ),
    (
        "window_except",
        "don't start before 9:30 unless it's a monday",
        {
            "kind": "window",
            "subject": "work",
            "rel": "after",
            "at": "09:30",
            "days": ["tue", "wed", "thu", "fri", "sat", "sun"],
        },
    ),
    (
        "window_except",
        "I'm done by 11 every night, saturday's the exception",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "23:00",
            "days": ["mon", "tue", "wed", "thu", "fri", "sun"],
        },
    ),
    (
        "window_except",
        "nothing after 9pm, sundays excluded",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "21:00",
            "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        },
    ),
    (
        "window_except",
        "weekends aside, stop at 9:30pm",
        {
            "kind": "window",
            "subject": "work",
            "rel": "before",
            "at": "21:30",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        },
    ),
    # ---- windows for a kind, course or title ----
    (
        "window_subject",
        "problem sets: afternoons only",
        {"kind": "window", "subject": "problem sets", "rel": "between", "at": "12:00", "until": "17:00"},
    ),
    (
        "window_subject",
        "essay writing waits until 10am, my brain needs to boot up",
        {"kind": "window", "subject": "essay writing", "rel": "after", "at": "10:00"},
    ),
    (
        "window_subject",
        "1 to 4pm is lab report time",
        {"kind": "window", "subject": "lab reports", "rel": "between", "at": "13:00", "until": "16:00"},
    ),
    (
        "window_subject",
        "I want my brain-intensive work done before 1pm",
        {"kind": "window", "subject": "deep work", "rel": "before", "at": "13:00"},
    ),
    (
        "window_subject",
        "mentally heavy stuff stops at 8pm",
        {"kind": "window", "subject": "deep work", "rel": "before", "at": "20:00"},
    ),
    (
        "window_subject",
        "save brainless stuff for after 9:30pm",
        {"kind": "window", "subject": "light work", "rel": "after", "at": "21:30"},
    ),
    (
        "window_subject",
        "busywork goes in the evening, when I'm fried",
        {"kind": "window", "subject": "light work", "rel": "between", "at": "17:00", "until": "22:00"},
    ),
    (
        "window_subject",
        "I study for CHEM 1210 between 9 and 11 in the morning",
        {"kind": "window", "subject": "chem 1210", "rel": "between", "at": "09:00", "until": "11:00"},
    ),
    (
        "window_subject",
        "past 9pm I can't do MATH 2220 anymore",
        {"kind": "window", "subject": "math 2220", "rel": "before", "at": "21:00"},
    ),
    (
        "window_subject",
        "test studying goes before 3pm",
        {"kind": "window", "subject": "exam prep", "rel": "before", "at": "15:00"},
    ),
    (
        "window_subject",
        "I can't start homework until 4:30, class goes all day",
        {"kind": "window", "subject": "homework", "rel": "after", "at": "16:30"},
    ),
    (
        "window_subject",
        "violin practice has to be between 3 and 6pm",
        {"kind": "window", "subject": "violin practice", "rel": "between", "at": "15:00", "until": "18:00"},
    ),
    (
        "window_subject",
        "no debugging past 1am, I write garbage then",
        {"kind": "window", "subject": "debugging", "rel": "before", "at": "01:00"},
    ),
    (
        "window_subject",
        "on saturdays and sundays, essays get written in the morning",
        {
            "kind": "window",
            "subject": "essays",
            "rel": "between",
            "at": "08:00",
            "until": "12:00",
            "days": ["sat", "sun"],
        },
    ),
    (
        "window_subject",
        "tues/thurs evenings 6-9 are for physics hw",
        {
            "kind": "window",
            "subject": "physics hw",
            "rel": "between",
            "at": "18:00",
            "until": "21:00",
            "days": ["tue", "thu"],
        },
    ),
    (
        "window_subject",
        "orgo reading cuts off at 10pm on school nights",
        {
            "kind": "window",
            "subject": "orgo reading",
            "rel": "before",
            "at": "22:00",
            "days": ["mon", "tue", "wed", "thu", "sun"],
        },
    ),
    (
        "window_subject",
        "weekday mornings 7-10am are reserved for deep work",
        {
            "kind": "window",
            "subject": "deep work",
            "rel": "between",
            "at": "07:00",
            "until": "10:00",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        },
    ),
    (
        "window_subject",
        "psych reading: anytime except the evening",
        {"kind": "window", "subject": "psych reading", "rel": "not_between", "at": "17:00", "until": "22:00"},
    ),
    (
        "window_subject",
        "cramming for exams stops at midnight",
        {"kind": "window", "subject": "exam prep", "rel": "before", "at": "00:00"},
    ),
    (
        "window_subject",
        "I like my run finished before 8am",
        {"kind": "window", "subject": "run", "rel": "before", "at": "08:00"},
    ),
    # ---- meals by the clock ----
    ("meals", "lunch should happen by 1pm", {"kind": "window", "subject": "lunch", "rel": "before", "at": "13:00"}),
    (
        "meals",
        "I don't want dinner before 6:30",
        {"kind": "window", "subject": "dinner", "rel": "after", "at": "18:30"},
    ),
    (
        "meals",
        "weekday breakfast somewhere in 8–9:30",
        {
            "kind": "window",
            "subject": "breakfast",
            "rel": "between",
            "at": "08:00",
            "until": "09:30",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        },
    ),
    (
        "meals",
        "make sure I eat dinner before 7:45pm",
        {"kind": "window", "subject": "dinner", "rel": "before", "at": "19:45"},
    ),
    # ---- keep a stretch free ----
    (
        "free",
        "thursday evenings stay clear for bible study",
        {"kind": "free", "subject": "work", "rel": "between", "at": "17:00", "until": "22:00", "days": ["thu"]},
    ),
    (
        "free",
        "monday nights are intramural nights, keep them open",
        {"kind": "free", "subject": "work", "rel": "between", "at": "22:00", "until": "02:00", "days": ["mon"]},
    ),
    (
        "free",
        "friday afternoons need to be empty, it's when I travel home",
        {"kind": "free", "subject": "work", "rel": "between", "at": "12:00", "until": "17:00", "days": ["fri"]},
    ),
    ("free", "block out sundays entirely", {"kind": "free", "subject": "work", "days": ["sun"]}),
    ("free", "saturdays should be wide open, no exceptions", {"kind": "free", "subject": "work", "days": ["sat"]}),
    (
        "free",
        "every day, 6 to 7:30pm stays open for the gym",
        {"kind": "free", "subject": "work", "rel": "between", "at": "18:00", "until": "19:30"},
    ),
    (
        "free",
        "leave 11am to 1pm open on tuesdays and thursdays",
        {"kind": "free", "subject": "work", "rel": "between", "at": "11:00", "until": "13:00", "days": ["tue", "thu"]},
    ),
    (
        "free",
        "protect sunday mornings at all costs",
        {"kind": "free", "subject": "work", "rel": "between", "at": "08:00", "until": "12:00", "days": ["sun"]},
    ),
    (
        "free",
        "on weeknights I need 8-9pm open to call home",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "20:00",
            "until": "21:00",
            "days": ["mon", "tue", "wed", "thu", "sun"],
        },
    ),
    ("free", "wednesdays stay clear all day", {"kind": "free", "subject": "work", "days": ["wed"]}),
    (
        "free",
        "leave monday and wednesday mornings open, I lift then",
        {"kind": "free", "subject": "work", "rel": "between", "at": "08:00", "until": "12:00", "days": ["mon", "wed"]},
    ),
    (
        "free",
        "my lunch hour, 12 to 1, stays clear",
        {"kind": "free", "subject": "work", "rel": "between", "at": "12:00", "until": "13:00"},
    ),
    (
        "free",
        "saturday 10am-2pm stays free, farmers market",
        {"kind": "free", "subject": "work", "rel": "between", "at": "10:00", "until": "14:00", "days": ["sat"]},
    ),
    # ---- keep a stretch lighter ----
    (
        "free",
        "thursday afternoons could be a bit lighter",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "12:00",
            "until": "17:00",
            "days": ["thu"],
            "amount": 0.5,
        },
    ),
    (
        "free",
        "go easier on me saturday and sunday nights",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "22:00",
            "until": "02:00",
            "days": ["sat", "sun"],
            "amount": 0.5,
        },
    ),
    (
        "free",
        "make tuesday mornings less packed",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "08:00",
            "until": "12:00",
            "days": ["tue"],
            "amount": 0.5,
        },
    ),
    (
        "free",
        "only a little work friday evenings",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "17:00",
            "until": "22:00",
            "days": ["fri"],
            "amount": 0.5,
        },
    ),
    (
        "free",
        "mon-thu evenings shouldn't be stacked, keep them lighter",
        {
            "kind": "free",
            "subject": "work",
            "rel": "between",
            "at": "17:00",
            "until": "22:00",
            "days": ["mon", "tue", "wed", "thu"],
            "amount": 0.5,
        },
    ),
    # ---- days ----
    ("days", "sundays I'm in no-school mode", {"kind": "days", "subject": "work", "rel": "not_on", "days": ["sun"]}),
    ("days", "I dont work saturdays. period.", {"kind": "days", "subject": "work", "rel": "not_on", "days": ["sat"]}),
    (
        "days",
        "thursdays and sundays: zero studying",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["thu", "sun"]},
    ),
    (
        "days",
        "study days are mon to fri",
        {"kind": "days", "subject": "work", "rel": "on", "days": ["mon", "tue", "wed", "thu", "fri"]},
    ),
    (
        "days",
        "only do schoolwork tuesday through saturday",
        {"kind": "days", "subject": "work", "rel": "on", "days": ["tue", "wed", "thu", "fri", "sat"]},
    ),
    (
        "days",
        "no homework fridays, that's my sanity day",
        {"kind": "days", "subject": "homework", "rel": "not_on", "days": ["fri"]},
    ),
    (
        "days",
        "physics problems go on M, W and F",
        {"kind": "days", "subject": "physics problems", "rel": "on", "days": ["mon", "wed", "fri"]},
    ),
    ("days", "orgo is a no-go on sundays", {"kind": "days", "subject": "orgo", "rel": "not_on", "days": ["sun"]}),
    (
        "days",
        "bio gets done on weekends and nowhere else",
        {"kind": "days", "subject": "bio", "rel": "on", "days": ["sat", "sun"]},
    ),
    ("days", "Sat: off. Sun: off.", {"kind": "days", "subject": "work", "rel": "not_on", "days": ["sat", "sun"]}),
    (
        "days",
        "mondays I don't touch school, it's my reset",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["mon"]},
    ),
    (
        "days",
        "wed and sat are school-free days",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["wed", "sat"]},
    ),
    (
        "days",
        "don't make me study on the weekends, I work retail",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["sat", "sun"]},
    ),
    (
        "days",
        "CS 2112 assignments only on sundays",
        {"kind": "days", "subject": "cs 2112 assignments", "rel": "on", "days": ["sun"]},
    ),
    (
        "days",
        "I won't do lab reports on weekends",
        {"kind": "days", "subject": "lab reports", "rel": "not_on", "days": ["sat", "sun"]},
    ),
    (
        "days",
        "deep focus work only mon thru thurs",
        {"kind": "days", "subject": "deep work", "rel": "on", "days": ["mon", "tue", "wed", "thu"]},
    ),
    (
        "days",
        "I can work whenever except fridays",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["fri"]},
    ),
    (
        "days",
        "the only days I'll study are monday, wednesday, and saturday",
        {"kind": "days", "subject": "work", "rel": "on", "days": ["mon", "wed", "sat"]},
    ),
    (
        "days",
        "spanish essays: thursdays only",
        {"kind": "days", "subject": "spanish essays", "rel": "on", "days": ["thu"]},
    ),
    (
        "days",
        "no math tue or thu, those are my lab days",
        {"kind": "days", "subject": "math", "rel": "not_on", "days": ["tue", "thu"]},
    ),
    (
        "days",
        "problem sets never go on a weekend",
        {"kind": "days", "subject": "problem sets", "rel": "not_on", "days": ["sat", "sun"]},
    ),
    (
        "days",
        "I take one day off a week and it's always sunday",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["sun"]},
    ),
    (
        "days",
        "tues is a no-work day, I'm at my internship",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["tue"]},
    ),
    (
        "days",
        "I study every day except tues and sat",
        {"kind": "days", "subject": "work", "rel": "not_on", "days": ["tue", "sat"]},
    ),
    # ---- pace on weekdays ----
    ("pace", "mondays I want to take it slow", {"kind": "pace", "paces": [["mon", "Easy"]]}),
    ("pace", "thursdays = beast mode", {"kind": "pace", "paces": [["thu", "Push"]]}),
    ("pace", "fri: easy. sat: normal pace.", {"kind": "pace", "paces": [["fri", "Easy"], ["sat", "Normal"]]}),
    ("pace", "sunday should be a big work day", {"kind": "pace", "paces": [["sun", "Push"]]}),
    ("pace", "go gentle on tues and weds", {"kind": "pace", "paces": [["tue", "Easy"], ["wed", "Easy"]]}),
    ("pace", "I go full send on saturdays", {"kind": "pace", "paces": [["sat", "Push"]]}),
    ("pace", "wednesday: regular pace, nothing special", {"kind": "pace", "paces": [["wed", "Normal"]]}),
    (
        "pace",
        "keep mon-wed light and thu-fri intense",
        {
            "kind": "pace",
            "paces": [["mon", "Easy"], ["tue", "Easy"], ["wed", "Easy"], ["thu", "Push"], ["fri", "Push"]],
        },
    ),
    ("pace", "sunday's a relaxed day for me", {"kind": "pace", "paces": [["sun", "Easy"]]}),
    # ---- caps on all work ----
    ("cap", "I tap out after five and a half hours a day", {"kind": "cap", "subject": "work", "amount": 5.5}),
    ("cap", "I can do six hours a day, not a minute more", {"kind": "cap", "subject": "work", "amount": 6.0}),
    ("cap", "daily workload shouldn't exceed 7 hrs", {"kind": "cap", "subject": "work", "amount": 7.0}),
    ("cap", "under 4 hours a day pls, I have a job", {"kind": "cap", "subject": "work", "amount": 4.0}),
    ("cap", "8hrs/day is plenty, never more", {"kind": "cap", "subject": "work", "amount": 8.0}),
    ("cap", "don't stack more than 3.5 hrs of work into one day", {"kind": "cap", "subject": "work", "amount": 3.5}),
    ("cap", "limit my days to 300 minutes of work", {"kind": "cap", "subject": "work", "amount": 5.0}),
    ("cap", "nine hrs of schoolwork is my absolute daily ceiling", {"kind": "cap", "subject": "work", "amount": 9.0}),
    ("cap", "cap every day at four hours, I'm burnt out", {"kind": "cap", "subject": "work", "amount": 4.0}),
    ("cap", "most I can handle per day is 6 and a half hours", {"kind": "cap", "subject": "work", "amount": 6.5}),
    ("cap", "keep daily study time at or below 7 hours", {"kind": "cap", "subject": "work", "amount": 7.0}),
    # ---- caps for a kind, course or title ----
    ("cap", "45 minutes of reading per day, no more", {"kind": "cap", "subject": "reading", "amount": 0.75}),
    ("cap", "I'll do anki for up to an hour a day, never longer", {"kind": "cap", "subject": "anki", "amount": 1.0}),
    (
        "cap",
        "I can't do more than 2 hours of orgo problems in a day",
        {"kind": "cap", "subject": "orgo problems", "amount": 2.0},
    ),
    (
        "cap",
        "lab report writing shouldn't go over 1.5h a day",
        {"kind": "cap", "subject": "lab report writing", "amount": 1.5},
    ),
    ("cap", "CS 2110 gets 3 hours a day at most", {"kind": "cap", "subject": "cs 2110", "amount": 3.0}),
    ("cap", "deep work maxes out at 4 hrs per day for me", {"kind": "cap", "subject": "deep work", "amount": 4.0}),
    ("cap", "cap test prep at five hrs/day", {"kind": "cap", "subject": "exam prep", "amount": 5.0}),
    (
        "cap",
        "only an hour of busywork per day, I procrastinate with it",
        {"kind": "cap", "subject": "light work", "amount": 1.0},
    ),
    ("cap", "40 min of violin a day or my wrist hurts", {"kind": "cap", "subject": "violin", "amount": 0.67}),
    ("cap", "homework shouldn't take more than 3 hrs a night", {"kind": "cap", "subject": "homework", "amount": 3.0}),
    # ---- caps on some days ----
    (
        "cap",
        "on fridays I'm only good for about 2 hours",
        {"kind": "cap", "subject": "work", "amount": 2.0, "days": ["fri"]},
    ),
    (
        "cap",
        "sat & sun, nothing beyond 3 hours of work",
        {"kind": "cap", "subject": "work", "amount": 3.0, "days": ["sat", "sun"]},
    ),
    (
        "cap",
        "mondays and wednesdays I can only do 3 hours total",
        {"kind": "cap", "subject": "work", "amount": 3.0, "days": ["mon", "wed"]},
    ),
    (
        "cap",
        "tuesdays I work a shift so 5 hours of school, max",
        {"kind": "cap", "subject": "work", "amount": 5.0, "days": ["tue"]},
    ),
    (
        "cap",
        "6h ceiling every day other than saturday",
        {"kind": "cap", "subject": "work", "amount": 6.0, "days": ["mon", "tue", "wed", "thu", "fri", "sun"]},
    ),
    (
        "cap",
        "monday to friday, keep each day to 8 hrs",
        {"kind": "cap", "subject": "work", "amount": 8.0, "days": ["mon", "tue", "wed", "thu", "fri"]},
    ),
    # ---- finish early ----
    ("early", "I want a day of wiggle room on every deadline", {"kind": "early", "subject": "work", "amount": 1.0}),
    (
        "early",
        "lab reports: aim to have them ready 48 hours ahead",
        {"kind": "early", "subject": "lab reports", "amount": 2.0},
    ),
    (
        "early",
        "get my problem sets wrapped up 36 hrs early",
        {"kind": "early", "subject": "problem sets", "amount": 1.5},
    ),
    (
        "early",
        "wrap up papers four days before they're due so I can edit",
        {"kind": "early", "subject": "papers", "amount": 4.0},
    ),
    (
        "early",
        "presentations finished at least a day before I present",
        {"kind": "early", "subject": "presentations", "amount": 1.0},
    ),
    (
        "early",
        "submit applications a week before they close",
        {"kind": "early", "subject": "applications", "amount": 7.0},
    ),
    (
        "early",
        "always aim to finish stuff 2 days out from the deadline",
        {"kind": "early", "subject": "work", "amount": 2.0},
    ),
    (
        "early",
        "software projects need to be done 3 days ahead because something always breaks",
        {"kind": "early", "subject": "software projects", "amount": 3.0},
    ),
    (
        "early",
        "orgo pre-labs need to be in the bag 24 hours ahead",
        {"kind": "early", "subject": "orgo pre-labs", "amount": 1.0},
    ),
    (
        "early",
        "have reading responses ready 12 hours before they're due",
        {"kind": "early", "subject": "reading responses", "amount": 0.5},
    ),
    (
        "early",
        "complete everything at least 48 hrs before the deadline",
        {"kind": "early", "subject": "work", "amount": 2.0},
    ),
    (
        "early",
        "for group presentations, have everything finished four days before we present",
        {"kind": "early", "subject": "group presentations", "amount": 4.0},
    ),
    (
        "early",
        "grad school apps done two weeks early",
        {"kind": "early", "subject": "grad school apps", "amount": 14.0},
    ),
    (
        "early",
        "I want all my homework finished by the day before",
        {"kind": "early", "subject": "homework", "amount": 1.0},
    ),
    # ---- deadlines and lateness ----
    ("deadlines", "under no circumstances should I submit something late", {"kind": "deadlines"}),
    ("deadlines", "being late on an assignment is my nightmare, prevent it at all costs", {"kind": "deadlines"}),
    ("deadlines", "Never hand anything in after it's due, whatever it costs", {"kind": "deadlines"}),
    ("deadlines", "I'd give up free time before turning in anything past the deadline", {"kind": "deadlines"}),
    ("deadlines", "Lateness is unacceptable.", {"kind": "deadlines"}),
    ("deadlines", "make sure every assignment goes in on time", {"kind": "deadlines"}),
    # ---- as close to the due as possible ----
    (
        "close",
        "cram quizzes right before they happen",
        {"kind": "close", "subject": "exam prep", "events": ["quizzes"]},
    ),
    (
        "close",
        "exam review should be squeezed in as close to exam day as possible",
        {"kind": "close", "subject": "exam prep"},
    ),
    (
        "close",
        "prep for my econ final right before it, with a 1 day buffer",
        {"kind": "close", "subject": "exam prep", "events": ["econ final"], "before_min": 1440},
    ),
    (
        "close",
        "studying for vocab tests: last minute",
        {"kind": "close", "subject": "exam prep", "events": ["vocab tests"]},
    ),
    (
        "close",
        "I do best cramming for midterms the day of",
        {"kind": "close", "subject": "exam prep", "events": ["midterms"]},
    ),
    (
        "close",
        "cram for exams, but stop 3 hours before it starts",
        {"kind": "close", "subject": "exam prep", "before_min": 180},
    ),
    ("close", "I retain more if I study for tests close to the test", {"kind": "close", "subject": "exam prep"}),
    (
        "close",
        "online quiz prep right up to the quiz, half an hour buffer",
        {"kind": "close", "subject": "exam prep", "events": ["online quiz"], "before_min": 30},
    ),
    (
        "close",
        "MCAT studying should run right up to test day, minus a 2-day breather",
        {"kind": "close", "subject": "exam prep", "events": ["mcat"], "before_min": 2880},
    ),
    (
        "close",
        "lab practicals I cram for at the last possible moment",
        {"kind": "close", "subject": "exam prep", "events": ["lab practicals"]},
    ),
    (
        "close",
        "reading summaries as close to the deadline as I can get",
        {"kind": "close", "subject": "reading summaries"},
    ),
    (
        "close",
        "response memos as late as they can go, with a 2 hr buffer",
        {"kind": "close", "subject": "response memos", "before_min": 120},
    ),
    (
        "close",
        "save study guides for the last stretch before the exam",
        {"kind": "close", "subject": "exam prep"},
    ),
    # ---- time kept around events ----
    (
        "around",
        "before barista shifts I need 20 min to get there",
        {"kind": "around", "events": ["barista shifts"], "before_min": 20, "after_min": 0},
    ),
    (
        "around",
        "hot yoga leaves me gross, 30 min after it to shower",
        {"kind": "around", "events": ["hot yoga"], "before_min": 0, "after_min": 30},
    ),
    (
        "around",
        "research job needs a 15-minute cushion before and after",
        {"kind": "around", "events": ["research job"], "before_min": 15, "after_min": 15},
    ),
    (
        "around",
        "internship: 40 min on the train each direction",
        {"kind": "around", "events": ["internship"], "before_min": 40, "after_min": 40},
    ),
    (
        "around",
        "football practice: I need 60 min afterwards for ice baths and food",
        {"kind": "around", "events": ["football practice"], "before_min": 0, "after_min": 60},
    ),
    (
        "around",
        "mock trial: show up 20 minutes early to prep, so keep that free",
        {"kind": "around", "events": ["mock trial"], "before_min": 20, "after_min": 0},
    ),
    (
        "around",
        "pad orchestra rehearsal by 10 min on both sides",
        {"kind": "around", "events": ["orchestra rehearsal"], "before_min": 10, "after_min": 10},
    ),
    (
        "around",
        "after fencing I'm drenched, 45 min to clean up",
        {"kind": "around", "events": ["fencing"], "before_min": 0, "after_min": 45},
    ),
    (
        "around",
        "I bike 30 min to babysitting and 30 min home",
        {"kind": "around", "events": ["babysitting"], "before_min": 30, "after_min": 30},
    ),
    (
        "around",
        "leave 1 hour before away matches for the bus and 30 min after",
        {"kind": "around", "events": ["away matches"], "before_min": 60, "after_min": 30},
    ),
    (
        "around",
        "the walk to ROTC is 25 minutes",
        {"kind": "around", "events": ["rotc"], "before_min": 25, "after_min": 0},
    ),
    (
        "around",
        "long marathon training runs wipe me out, block 90 minutes after",
        {"kind": "around", "events": ["marathon training runs"], "before_min": 0, "after_min": 90},
    ),
    (
        "around",
        "doctor appointments need 5 minutes of lead time and 15 minutes after",
        {"kind": "around", "events": ["doctor appointments"], "before_min": 5, "after_min": 15},
    ),
    (
        "around",
        "clinic is a 35 min drive there and 35 back",
        {"kind": "around", "events": ["clinic"], "before_min": 35, "after_min": 35},
    ),
    # ---- work right after an event ----
    (
        "after",
        "once spanish class lets out, do vocab",
        {"kind": "after", "subject": "vocab", "event": "spanish class"},
    ),
    (
        "after",
        "write the lab report the minute I'm done with chem lab",
        {"kind": "after", "subject": "lab report", "event": "chem lab"},
    ),
    (
        "after",
        "do my theory homework right away after piano lesson",
        {"kind": "after", "subject": "theory homework", "event": "piano lesson"},
    ),
    (
        "after",
        "do lecture review directly after lecture",
        {"kind": "after", "subject": "lecture review", "event": "lecture"},
    ),
    (
        "after",
        "the moment standup ends, do code review",
        {"kind": "after", "subject": "code review", "event": "standup"},
    ),
    (
        "after",
        "head to the gym directly after my 2pm seminar",
        {"kind": "after", "subject": "gym", "event": "seminar"},
    ),
    # ---- events that give way to work ----
    ("optional", "if I'm drowning, ditch the gym", {"kind": "optional", "events": ["gym"]}),
    (
        "optional",
        "ultimate practice is the first to go when work stacks up",
        {"kind": "optional", "events": ["ultimate practice"]},
    ),
    (
        "optional",
        "bouldering is a nice-to-have, skip it if I'm behind",
        {"kind": "optional", "events": ["bouldering"]},
    ),
    (
        "optional",
        "my weekly run club can be sacrificed for deadlines",
        {"kind": "optional", "events": ["weekly run club"]},
    ),
    (
        "optional",
        "it's fine to blow off zumba if there's too much due",
        {"kind": "optional", "events": ["zumba"]},
    ),
    ("optional", "sorority socials? optional, honestly", {"kind": "optional", "events": ["sorority socials"]}),
    (
        "optional",
        "PSYC 1101 lecture can be skipped, the slides are online",
        {"kind": "optional", "events": ["psyc 1101 lecture"]},
    ),
    (
        "optional",
        "volleyball and swim can both go if I'm swamped",
        {"kind": "optional", "events": ["volleyball", "swim"]},
    ),
    ("optional", "treat cycling class as optional", {"kind": "optional", "events": ["cycling class"]}),
    # ---- events only when ahead ----
    ("ahead", "open mic? only if I'm way ahead", {"kind": "ahead", "events": ["open mic"]}),
    (
        "ahead",
        "honestly I skip most of the tutoring sessions",
        {"kind": "ahead", "events": ["tutoring sessions"]},
    ),
    ("ahead", "bar nights only if every assignment is done", {"kind": "ahead", "events": ["bar nights"]}),
    (
        "ahead",
        "I'll go on the ski club trips if I'm caught up, otherwise no",
        {"kind": "ahead", "events": ["ski club trips"]},
    ),
    (
        "ahead",
        "improv jam only when I'm not behind on anything",
        {"kind": "ahead", "events": ["improv jam"]},
    ),
    ("ahead", "I don't usually go to bible study", {"kind": "ahead", "events": ["bible study"]}),
    (
        "ahead",
        "skip the weekly mixers unless I've finished my work",
        {"kind": "ahead", "events": ["weekly mixers"]},
    ),
    (
        "ahead",
        "tailgates are only for when I'm ahead on everything",
        {"kind": "ahead", "events": ["tailgates"]},
    ),
    # ---- the night before an event ----
    (
        "night_before",
        "Got a quiz the next day? Then I'm finished at 10:15.",
        {"kind": "night_before", "at": "22:15", "events": ["quiz"]},
    ),
    (
        "night_before",
        "evening before my driving test: stop by 8",
        {"kind": "night_before", "at": "20:00", "events": ["driving test"]},
    ),
    (
        "night_before",
        "soccer game in the morning means I'm done by 9:45 the night before",
        {"kind": "night_before", "at": "21:45", "events": ["soccer game"]},
    ),
    (
        "night_before",
        "whenever there's a final the following morning, wrap up at 10pm",
        {"kind": "night_before", "at": "22:00", "events": ["final"]},
    ),
    (
        "night_before",
        "when an exam is the next day I shut it down at 9pm",
        {"kind": "night_before", "at": "21:00", "events": ["exam"]},
    ),
    (
        "night_before",
        "day before the LSAT, nothing past 8pm",
        {"kind": "night_before", "at": "20:00", "events": ["lsat"]},
    ),
    (
        "night_before",
        "recital the next day? then nothing after 9:30",
        {"kind": "night_before", "at": "21:30", "events": ["recital"]},
    ),
    ("night_before", "hackathon eve, I wrap up by 9", {"kind": "night_before", "at": "21:00", "events": ["hackathon"]}),
    (
        "night_before",
        "if a presentation is first thing tomorrow, no work past 10:30",
        {"kind": "night_before", "at": "22:30", "events": ["presentation"]},
    ),
    (
        "night_before",
        "I stop at 9:15 on nights before a meet",
        {"kind": "night_before", "at": "21:15", "events": ["meet"]},
    ),
    # ---- meals kept ----
    ("meals", "even when I'm behind, I eat breakfast", {"kind": "meals_kept", "events": ["breakfast"]}),
    ("meals", "skipping dinner is never ok", {"kind": "meals_kept", "events": ["dinner"]}),
    (
        "meals",
        "my meals are off limits for work",
        {"kind": "meals_kept", "events": ["breakfast", "lunch", "dinner"]},
    ),
    ("meals", "never steal my lunch break for deadlines", {"kind": "meals_kept", "events": ["lunch"]}),
    (
        "meals",
        "breakfast + dinner always happen, whatever is due",
        {"kind": "meals_kept", "events": ["breakfast", "dinner"]},
    ),
    # ---- meals learned ----
    (
        "meals",
        "not sure if I eat breakfast tbh, figure it out",
        {"kind": "meals_learned", "events": ["breakfast"]},
    ),
    (
        "meals",
        "watch when I actually have dinner and plan it from that",
        {"kind": "meals_learned", "events": ["dinner"]},
    ),
    (
        "meals",
        "learn my eating schedule from my logs",
        {"kind": "meals_learned", "events": ["breakfast", "lunch", "dinner"]},
    ),
    ("meals", "lunch timing: just learn it from what I do", {"kind": "meals_learned", "events": ["lunch"]}),
    # ---- fit tasks to gaps ----
    ("gaps", "if I've got 15 free minutes, give me a 15 minute task", {"kind": "fit_gaps"}),
    ("gaps", "line tasks up with free slots of a similar length", {"kind": "fit_gaps"}),
    ("gaps", "the quick things go in the little pockets of time", {"kind": "fit_gaps"}),
    ("gaps", "reserve my longest free blocks for my longest tasks", {"kind": "fit_gaps"}),
    ("gaps", "tiny chores in the odd half hours, essays in the big open stretches", {"kind": "fit_gaps"}),
    # ---- things that run by themselves ----
    ("running", "bread machine runs need me home and working, not out", {"kind": "runs_while_working"}),
    (
        "running",
        "start long model runs only when I'm at my laptop, never during class",
        {"kind": "runs_while_working"},
    ),
    ("running", "don't have the washing machine going while I'm off at my job", {"kind": "runs_while_working"}),
    ("running", "hands-off tasks like the 3D printer only while I'm around studying", {"kind": "runs_while_working"}),
    (
        "running",
        "set-and-forget tasks should only go while I'm working, not while I'm out at practice",
        {"kind": "runs_while_working"},
    ),
    # ---- a minimum of sleep ----
    ("sleep_min", "I gotta sleep 7+ hrs a night, don't eat into that", {"kind": "sleep_min", "amount": 7.0}),
    ("sleep_min", "I'm useless on under 6 hours of sleep, never go below", {"kind": "sleep_min", "amount": 6.0}),
    (
        "sleep_min",
        "eight and a half hours of sleep minimum on weeknights",
        {"kind": "sleep_min", "amount": 8.5, "days": ["mon", "tue", "wed", "thu", "sun"]},
    ),
    ("sleep_min", "sleep can never drop below 6 and a half hrs", {"kind": "sleep_min", "amount": 6.5}),
    (
        "sleep_min",
        "on friday and saturday nights let me get 9 hours of sleep at least",
        {"kind": "sleep_min", "amount": 9.0, "days": ["fri", "sat"]},
    ),
    ("sleep_min", "sleep >= 7 hours", {"kind": "sleep_min", "amount": 7.0}),
    # ---- sleep said other ways ----
    ("sleep", "sleep schedule: ~1am to ~9am", "set:sleep"),
    ("sleep", "I roll out of bed at 7:20 most mornings", "set:sleep"),
    ("sleep", "I hit the hay around 11:45", "set:sleep"),
    ("sleep", "weekends I'm asleep from 2 till 10", "set:sleep"),
    # ---- settings worded like rules ----
    ("priority", "essays matter more than readings", "set:kind_order"),
    ("priority", "if there's a clash, psets beat flashcards", "set:kind_order"),
    ("priority", "when time's short, cut flashcards before problem sets", "set:kind_order"),
    ("priority", "stuff due this week before stuff due next month", "set:short_term_first"),
    ("priority", "for the 3 days leading up to a final, only study that subject", "set:exam_focus"),
    ("deadlines", "once a reading quiz closes there's no point studying for it", "set:pointless_late"),
    ("deadlines", "if the deadline passes on a discussion post, just drop it", "set:pointless_late"),
    ("sitting", "chunk big assignments across several sessions", "set:sittings"),
    ("busy", "my 'maybe' events shouldn't block study time", "set:busy"),
    ("busy", "ignore the sports schedule calendar, it's just for reference", "set:busy"),
    ("cap", "weekday limit 6h except friday 3h; weekends just 1h", "set:daily_cap"),
    ("cap", "tuesdays I can do 2 hours, thursdays 3", "set:daily_cap"),
    ("around", "I need 10 min after each class to get across campus", "set:event_kinds"),
    ("around", "pad all my calendar events with 5 minutes", "set:event_kinds"),
    ("around", "before every lecture, 15 min to grab coffee and walk over", "set:event_kinds"),
    # ---- what nothing says yet, worded like rules ----
    ("cap", "my weekly limit is 30 hrs total", "new:weekly cap"),
    ("cap", "make sure I study at least 2 hrs every single day", "new:daily minimum"),
    ("cap", "three assignments a day is the max", "new:count cap"),
    ("sitting", "don't schedule anything longer than 2 hours at a stretch", "new:max session length"),
    ("sitting", "work blocks should be 45 minutes minimum", "new:min session length"),
    ("cond_new", "late nights are ok only when a deadline is tomorrow", "new:condition on due soon"),
    ("cond_new", "on my long lab days, nothing after 8pm", "new:condition on day load"),
    ("cond_new", "in exam weeks I can push to 10 hours a day", "new:condition on exam period"),
    ("window_new", "don't put studying right after my shift at the cafe", "new:not after event"),
    ("window_new", "review my notes before every seminar", "new:before event"),
    ("optional", "my lab section can never be skipped", "new:mark event required"),
    ("sleep", "no work in the 45 min before I go to bed", "new:wind-down before bed"),
    ("energy", "once it's past 9:30, only give me low-effort stuff", "new:only light work in a window"),
    ("except", "weekends are off, except I'll still do lab writeups", "new:exception for a kind"),
    ("deadlines", "don't start a paper more than 10 days before it's due", "new:start window before due"),
    ("deadlines", "readings can slide a day or two, they're not graded", "new:soft deadline for kind"),
    # ---- compounds ----
    ("compound", "max 5h a day + nothing before 9", "multi"),
    ("compound", "skip the gym if I'm behind, but never skip dinner", "multi"),
    ("compound", "lab reports a day early; essays three days early", "multi"),
    ("compound", "I need 8 hours of sleep and I want to be in bed by midnight", "multi"),
    ("compound", "no studying on fridays and keep sunday mornings open", "multi"),
    ("compound", "anki in the morning and coding after 8pm", "multi"),
    ("compound", "keep thursday nights free for trivia and go hard on wednesdays", "multi"),
    ("compound", "30 min to get to my shift and 15 min after choir", "multi"),
    ("compound", "study for tests as late as possible and keep weekends work-free", "multi"),
    ("compound", "fit short tasks into gaps and never let anything be late", "multi"),
    ("compound", "climbing only if I'm ahead, and an hour after it to eat", "multi"),
    ("compound", "monday to thursday stop at 11pm, friday stop at 5pm", "multi"),
    ("compound", "orgo only in the mornings and never on fridays", "multi"),
    # ---- really items, though they sound like rules ----
    ("item", "TA office hours thursdays 4-5:30", "item"),
    ("item", "6:30am spin on tuesdays", "item"),
    ("item", "15 pages of my novel before sleep, nightly", "item"),
    ("item", "lunch with my advisor every other friday at noon", "item"),
    ("item", "guitar for half an hour every evening", "item"),
    ("item", "intramural basketball games are sundays 8-9pm", "item"),
    ("item", "dinner at 7 sharp every night with my host family", "item"),
    ("item", "work-study at the gym front desk mon/wed 6-9am", "item"),
    ("item", "every morning, 10 min of stretching at 7:30", "item"),
    ("item", "animal shelter shift, saturdays 1-4pm", "item"),
    ("item", "need about 6 hours to finish the CS project", "item"),
    ("item", "orchestra rehearsal monday & wednesday 7-9:30pm", "item"),
    # ---- not rules at all ----
    ("offtopic", "why is everything on tuesday", "new:not a rule"),
    ("offtopic", "this semester is killing me", "new:not a rule"),
    ("offtopic", "can friday sync with canvas?", "new:not a rule"),
    ("offtopic", "I'm behind on everything lol", "new:not a rule"),
]
