from datetime import datetime

import pytest

from friday.core.presets import DEFAULT_PRESETS
from friday.core.quickadd import parse

NOW = datetime(2026, 10, 18, 10, 0)  # Sunday
AREAS = ["CS 1110", "Psych", "Health"]
ITEMS = {"ps4 draft": 12, "lab report": 30}


def quick(text: str) -> dict:
    return parse(text, NOW, areas=AREAS, presets=DEFAULT_PRESETS, find_item=lambda t: ITEMS.get(t.lower())).fields


CASES = [
    (
        "PS5 #cs1110 due tue 5pm ~3h",
        {
            "title": "PS5",
            "area": "CS 1110",
            "due_local": "2026-10-20T17:00",
            "duration_units": 12,
            "preset": "Assignment",
        },
    ),
    (
        "reading ch 4 #psych due fri ~1h",
        {"title": "reading ch 4", "area": "Psych", "due_local": "2026-10-23T23:59", "duration_units": 4},
    ),
    ("laundry", {"title": "laundry", "preset": "Errand"}),
    ("laundry /chore", {"title": "laundry", "preset": "Chore"}),
    ("call mom /Errand ~20m", {"title": "call mom", "preset": "Errand", "duration_units": 2}),
    ("essay draft by mon", {"title": "essay draft", "due_local": "2026-10-19T23:59"}),
    ("stand by me", {"title": "stand by me", "preset": "Errand"}),
    (
        "dentist at fri 3pm for 1h",
        {
            "title": "dentist",
            "preset": "Event",
            "start_local": "2026-10-23T15:00",
            "end_local": "2026-10-23T16:00",
        },
    ),
    ("dentist at fri@3pm for 40m", {"start_local": "2026-10-23T15:00", "end_local": "2026-10-23T15:40"}),
    ("meet at 3pm for 1h30m", {"start_local": "2026-10-18T15:00", "end_local": "2026-10-18T16:30"}),
    ("look at the stars", {"title": "look at the stars"}),
    ("call mom sat 3pm 30m", {"title": "call mom", "start_local": "2026-10-24T15:00", "end_local": "2026-10-24T15:30"}),
    ("dentist tomorrow 9:30am", {"start_local": "2026-10-19T09:30", "end_local": "2026-10-19T10:30"}),
    ("essay 2h due fri", {"title": "essay", "duration_units": 8, "due_local": "2026-10-23T23:59"}),
    ("read dune open", {"title": "read dune", "amount": "open", "preset": "Side project"}),
    ("open bank account", {"title": "open bank account", "preset": "Errand"}),
    ("reading ch 4", {"title": "reading ch 4"}),
    (
        "lunch ~20m-45m /routine",
        {"amount": "elastic", "min_units": 2, "ideal_units": 3, "max_units": 3, "preset": "Routine"},
    ),
    (
        "gym every week 3x",
        {"title": "gym", "rrule": "FREQ=WEEKLY", "per_window": 3, "dtstart_local": "2026-10-18T04:00"},
    ),
    ("shower every day ~15m", {"title": "shower", "rrule": "FREQ=DAILY", "duration_units": 1}),
    (
        "CS 1110 every mon,wed,fri at 10:10 for 50m",
        {
            "title": "CS 1110",
            "preset": "Class",
            "rrule": "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "dtstart_local": "2026-10-19T10:10",  # its first Monday, not the Sunday it was said on (8 Nov)
        },
    ),
    (
        "standup every weekdays at 9am for 15m",
        {"rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "preset": "Event"},
    ),
    ("rent every month 1", {"rrule": "FREQ=MONTHLY;BYMONTHDAY=1"}),
    ("review every 2w thu", {"rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH"}),
    ("lab every tue until 12-11", {"rrule": "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261211T235959"}),
    (
        "water plants every day from wed",
        {"dtstart_local": "2026-10-21T04:00", "release_local": "2026-10-21T04:00"},
    ),
    ("PS6 !4", {"title": "PS6", "importance": 4}),
    ("PS6 !high", {"importance": 5}),
    ("PS6 !low", {"importance": 1}),
    ("run @physical", {"title": "run", "energy": "physical"}),
    ("write @deep ~2h", {"energy": "deep", "duration_units": 8}),
    ('final draft after:"PS4 draft" due fri', {"title": "final draft", "after": [12]}),
    ("final draft after:T12", {"after": [12]}),
    ("study before:t40", {"before": [40]}),
    ("write up after:lab-report", {"after": ["lab-report"]}),
    (
        "store run maybe sat-sun ~2h",
        {
            "title": "store run",
            "certainty": "tentative",
            "preset": "Maybe",
            "release_local": "2026-10-24T04:00",
            "due_local": "2026-10-25T23:59",
            "duration_units": 8,
        },
    ),
    ("clean garage one-sitting ~3h", {"shape": "one_sitting", "duration_units": 12}),
    ("thesis notes split", {"shape": "split", "title": "thesis notes"}),
    ("read +reading +fun", {"tags": ["reading", "fun"], "title": "read"}),
    ("tax forms due 2026-11-02", {"due_local": "2026-11-02T23:59"}),
    ("tax forms due oct 30 9:30am", {"due_local": "2026-10-30T09:30"}),
    ("tax forms due in 3d", {"due_local": "2026-10-21T23:59"}),
    ("tax forms due +3d", {"due_local": "2026-10-21T23:59"}),
    ("pack due tomorrow", {"due_local": "2026-10-19T23:59"}),
    ("pack due today 9pm", {"due_local": "2026-10-18T21:00"}),
    ("plan trip due next week", {"due_local": "2026-10-19T23:59"}),
    ("expense report due eom", {"due_local": "2026-10-31T23:59"}),
    ("weekly wrap due eow", {"due_local": "2026-10-18T23:59"}),
    ("PS7 due 10-14", {"due_local": "2027-10-14T23:59"}),
    ("PS7 from mon due fri", {"release_local": "2026-10-19T04:00", "due_local": "2026-10-23T23:59"}),
    ("~1.5h essay due wed #CS1110", {"title": "essay", "duration_units": 6, "area": "CS 1110"}),
    ("doctor #health at tue 8:15am for 45m", {"area": "Health", "start_local": "2026-10-20T08:15"}),
    ("book club #books", {"area": "books"}),
    ("#psych reading /reading", {"title": "reading", "preset": "Reading", "area": "Psych"}),
    ("side thing /side-project", {"preset": "Side project", "title": "side thing"}),
    ("finish due", {"title": "finish due"}),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_quick_add_lines(text: str, expected: dict) -> None:
    fields = quick(text)
    assert {k: fields.get(k) for k in expected} == expected


def test_there_are_at_least_forty_cases() -> None:
    assert len(CASES) >= 40


def test_spans_cover_each_recognized_token() -> None:
    result = parse("PS5 #cs1110 due tue 5pm ~3h", NOW, areas=AREAS)
    assert [(s.kind, "PS5 #cs1110 due tue 5pm ~3h"[s.start : s.end]) for s in result.spans] == [
        ("area", "#cs1110"),
        ("due_local", "due tue 5pm"),
        ("length", "~3h"),
    ]


@pytest.mark.parametrize(
    ("text", "warning"),
    [
        ("book club #books", "new area books"),
        ("x due 10-11", "10-11 read as Oct 11"),
        ("x /nosuch", "unknown preset /nosuch"),
        ('x after:"nothing here"', "unknown dependency nothing here"),
        ("meet at fri 3pm", "no length given; 1 h assumed"),
        ("due fri", "no title"),
    ],
)
def test_warnings(text: str, warning: str) -> None:
    result = parse(text, NOW, areas=AREAS, presets=DEFAULT_PRESETS, find_item=lambda t: None)
    assert warning in result.warnings


def test_early_morning_counts_as_the_previous_planning_day() -> None:
    fields = parse("x due tomorrow", datetime(2026, 10, 19, 1, 30)).fields
    assert fields["due_local"] == "2026-10-19T23:59"


from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from friday.core.quickadd import format_line  # noqa: E402

TITLE_WORDS = st.sampled_from(["read", "essay", "gym", "lab", "report", "notes", "PS5", "call", "plan"])
OPTIONAL_TOKENS = st.sampled_from(
    [
        "#cs1110",
        "#psych",
        "+reading",
        "/errand",
        "/goal",
        "due fri 5pm",
        "due tomorrow",
        "from mon",
        "~2h",
        "~20m-45m",
        "!4",
        "@deep",
        "maybe",
        "one-sitting",
        "split",
        "after:T12",
        'before:"lab report"',
        "every day",
        "every mon,wed 3x",
        "every week until 12-11",
        "at sat 9am for 90m",
        "due 11-02",
        "sat 3pm 45m",
        "1.5h",
    ]
)


@given(st.lists(TITLE_WORDS, min_size=1, max_size=3), st.lists(OPTIONAL_TOKENS, max_size=5, unique=True))
def test_parse_format_parse_is_stable(title: list[str], tokens: list[str]) -> None:
    first = parse(" ".join(title + tokens), NOW, areas=AREAS, presets=DEFAULT_PRESETS).fields
    again = parse(format_line(first), NOW, areas=AREAS, presets=DEFAULT_PRESETS).fields
    assert again == first


# How students type (M15): Sunday Oct 18, 10:00.
STUDENT_LINES = [
    ("CHEM prelim oct 27 7:30pm-9pm", {"title": "CHEM prelim", "start_local": "2026-10-27T19:30",
                                       "end_local": "2026-10-27T21:00", "preset": "Event"}),
    ("office hours wed 3-4pm", {"title": "office hours", "start_local": "2026-10-21T15:00",
                                "end_local": "2026-10-21T16:00"}),
    # The day after the times is still the times' day (it was left in the title, and the times put on today).
    ("review 11-1pm sat", {"title": "review", "start_local": "2026-10-24T11:00", "end_local": "2026-10-24T13:00"}),
    ("groceries sat", {"title": "groceries", "due_local": "2026-10-24T23:59", "preset": "Errand"}),
    ("email prof about extension today", {"title": "email prof about extension", "due_local": "2026-10-18T23:59"}),
    ("pay bursar bill by 11/15", {"title": "pay bursar bill", "due_local": "2026-11-15T23:59"}),
    # On a Sunday, "next friday" is the coming week's.
    ("essay draft due next friday 5pm ~4h", {"title": "essay draft", "due_local": "2026-10-23T17:00",
                                             "duration_units": 16, "preset": "Assignment"}),
    ("dentist 10/30 at 9am", {"title": "dentist", "start_local": "2026-10-30T09:00"}),
    ("lab report due wed noon", {"title": "lab report", "due_local": "2026-10-21T12:00"}),
    ("reading by tues 1:25pm ~5h", {"title": "reading", "due_local": "2026-10-20T13:25", "duration_units": 20}),
    ("study session tmrw 4pm 2h", {"title": "study session", "start_local": "2026-10-19T16:00",
                                   "end_local": "2026-10-19T18:00"}),
    ("gym every mon wed fri 7am 1h", {"title": "gym", "rrule": "FREQ=WEEKLY;BYDAY=MO,WE,FR"}),
    ("lab every tue and thu", {"title": "lab", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH"}),
    ("gym 3x a week", {"title": "gym", "rrule": "FREQ=WEEKLY", "per_window": 3}),
    ("run twice a week ~30m", {"title": "run", "rrule": "FREQ=WEEKLY", "per_window": 2, "duration_units": 2}),
    ("read 3 chapters", {"title": "read 3 chapters", "preset": "Reading"}),  # the title says what it is (audit, 8 Nov)
    ("club meeting every tue 7pm 1h", {"title": "club meeting", "preset": "Event"}),
    ("chem lab every mon 1:25pm 3h", {"title": "chem lab", "preset": "Class"}),
]  # fmt: skip


@pytest.mark.parametrize(("text", "expected"), STUDENT_LINES)
def test_lines_as_students_type_them(text: str, expected: dict) -> None:
    found = quick(text)
    assert {k: found.get(k) for k in expected} == expected


@pytest.mark.parametrize(
    ("text", "rule", "preset"),
    [
        ("groceries every week due sunday ~1h", "FREQ=WEEKLY", "Errand"),
        ("pay rent every month ~15m", "FREQ=MONTHLY", "Errand"),
        ("haircut every 4 weeks ~1h", "FREQ=WEEKLY;INTERVAL=4", "Errand"),
        ("call grandma biweekly ~30m", "FREQ=WEEKLY;INTERVAL=2", "Errand"),
        ("problem set every week due fri 5pm ~3h", "FREQ=WEEKLY", "Assignment"),
    ],
)
def test_repeating_errands_stay_errands_with_a_due(text: str, rule: str, preset: str) -> None:
    fields = quick(text)
    assert (fields["rrule"], fields["preset"]) == (rule, preset)


@pytest.mark.parametrize(
    ("text", "preset"),
    [
        ("dinner with Sam thu 6pm-9pm", "Event"),  # a plan with someone, at a time
        ("lunch w/ mom sat 12-2pm", "Event"),
        ("dinner out fri 7-9pm", "Event"),
        ("lunch every day 11:30am-2pm 30-45m", "Routine"),  # your meal: a window it may go in
        ("dinner 5:30-8:30pm", "Routine"),
    ],
)
def test_a_meal_with_someone_is_an_event_and_your_own_is_a_routine(text: str, preset: str) -> None:
    fields = quick(text)
    assert fields["preset"] == preset
    assert ("start_local" in fields) == (preset == "Event")


@pytest.mark.parametrize(
    "text", ["laundry every week ~2h runs by itself", "laundry ~2h in the background", "download dataset background"]
)
def test_a_task_that_runs_by_itself_says_so(text: str) -> None:
    fields = quick(text)
    assert fields["background"] is True and "itself" not in fields["title"] and "background" not in fields["title"]


def test_by_a_time_is_still_a_due() -> None:
    assert quick("essay by fri")["due_local"] == "2026-10-23T23:59"


# 27 Oct: "salsa on friday from 6:15 to 7:30 every friday" made a weekly "salsa on to" at 7:30 in the morning, and
# "...from 6:15-7:30pm every week" a flexible errand. Each is now Salsa, Friday 6:15 to 7:30pm.
@pytest.mark.parametrize(
    ("text", "rrule"),
    [
        ("salsa on friday from 6:15 to 7:30 every friday", "FREQ=WEEKLY;BYDAY=FR"),
        ("salsa on friday from 6:15-7:30pm every week", "FREQ=WEEKLY"),
        ("salsa every friday from 6:15pm to 7:30pm", "FREQ=WEEKLY;BYDAY=FR"),
        ("salsa friday from 6:15 to 7:30", None),
        ("salsa 6:15-7:30 friday", None),
        ("salsa friday 6:15-7:30", None),
    ],
)
def test_an_evening_event_said_many_ways(text: str, rrule: str | None) -> None:
    fields = quick(text)
    assert (fields["title"], fields["preset"], fields.get("rrule")) == ("salsa", "Event", rrule)
    assert fields["start_local"][11:] == "18:15" and fields["end_local"][11:] == "19:30"
    assert "due_local" not in fields
    if rrule is None:
        assert fields["start_local"][:10] == "2026-10-23"  # the Friday after NOW (Sunday the 18th)


def test_morning_hours_written_so_stay_morning() -> None:
    assert quick("gym 06:30-07:30 tue")["start_local"].endswith("06:30")
    assert quick("gym 7:30am-9am tue")["start_local"].endswith("07:30")
    assert quick("lecture 10:10-11:25 mon")["start_local"].endswith("10:10")
