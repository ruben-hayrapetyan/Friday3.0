"""A Mac calendar's repeating event, said as it repeats (27 Nov, a user's notes, "Friday Notes-3": every birthday
read "Repeats every Tuesday, all day": the Mac app sent no rule, and Friday took a yearly event seen once in the six
weeks it sends for a weekly one). The Mac app sends Calendar's own rule now, as Google's come; without one (an older
Mac app), the times seen say it."""

from pathlib import Path

import pytest

from friday.commands.series import weekdays_rule
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import HOME, mac_event, post


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def birthday(rule: str | None) -> dict:
    extra = {"rule": rule} if rule else {}
    return {"id": "bday@1", "calendar": "home", "title": "Sam's Birthday", "start": "2026-11-24", "end": "2026-11-25",
            "all_day": True, "series": "bday", **extra}  # fmt: skip


def pattern(app: App, title: str) -> str:
    [row] = [r for r in app.do("series_list") if r["title"] == title]
    return row["pattern"]


def test_a_birthday_with_the_calendars_rule_repeats_yearly(app: App) -> None:
    post(app, [HOME], [birthday("FREQ=YEARLY")])
    assert pattern(app, "Sam's Birthday").startswith("Yearly")


def test_a_birthday_from_an_older_mac_app_seen_once_is_yearly_not_weekly(app: App) -> None:
    post(app, [HOME], [birthday(None)])
    said = pattern(app, "Sam's Birthday")
    assert said.startswith("Yearly") and "Tue" not in said, said


def test_a_weekly_class_with_its_rule_says_its_days(app: App) -> None:
    lec = [mac_event(f"lec@{d}", "home", "Chem lecture", f"2026-10-{d}T10:00", f"2026-10-{d}T11:00", series="lec",
                     rule="FREQ=WEEKLY;BYDAY=TU,TH") for d in (20, 22, 27, 29)]  # fmt: skip
    post(app, [HOME], lec)
    said = pattern(app, "Chem lecture")
    assert "Tue" in said and "Thu" in said and not said.startswith("Yearly"), said


def test_a_weekly_class_from_an_older_mac_app_is_weekly_on_the_days_seen(app: App) -> None:
    lec = [mac_event(f"lec@{d}", "home", "Chem lecture", f"2026-10-{d}T10:00", f"2026-10-{d}T11:00", series="lec")
           for d in (20, 22, 27, 29)]  # fmt: skip
    post(app, [HOME], lec)
    said = pattern(app, "Chem lecture")
    assert "Tue" in said and "Thu" in said, said


def test_a_rule_without_a_series_is_left_out(app: App) -> None:
    """Only a repeating event's occurrences carry a rule: a one-off sent with one (it can't be) isn't a repeat."""
    post(app, [HOME], [mac_event("one", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00", rule="FREQ=YEARLY")])
    assert [r for r in app.do("series_list") if r["title"] == "Dentist"] == []


@pytest.mark.parametrize(
    ("starts", "rule"),
    [
        (["2026-11-24T00:00"], "FREQ=YEARLY"),  # a whole day seen once: a birthday, a holiday
        (["2026-10-20T19:00"], "FREQ=WEEKLY;BYDAY=TU"),  # a timed one seen once: a club, read over a short window
        ([], "FREQ=YEARLY"),
        ([f"2026-10-{d}T07:00" for d in range(19, 26)], "FREQ=DAILY"),  # every day of a week
        ([f"2026-10-{d}T07:00" for d in (19, 20, 21, 22, 23, 26, 27)], "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),  # weekdays
        (["2026-10-20T10:00", "2026-10-22T10:00", "2026-10-27T10:00"], "FREQ=WEEKLY;BYDAY=TU,TH"),
        (["2026-10-20T10:00", "2026-10-27T10:00", "2026-11-03T10:00"], "FREQ=WEEKLY;BYDAY=TU"),
        (
            ["2026-10-20T10:00", "2026-11-03T10:00", "2026-11-17T10:00"],
            "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU",
        ),  # every other
        (["2026-10-20T10:00", "2026-11-20T10:00"], "FREQ=MONTHLY"),
        (["2026-10-01T10:00", "2026-10-31T10:00"], "FREQ=MONTHLY"),
        (["2025-11-24T00:00", "2026-11-24T00:00"], "FREQ=YEARLY"),
        (["2026-10-20T10:00", "2026-10-20T15:00", "2026-10-27T10:00"], "FREQ=WEEKLY;BYDAY=TU"),  # twice one day
    ],
)
def test_a_repeat_without_its_rule_is_read_from_the_times_seen(starts: list[str], rule: str) -> None:
    assert weekdays_rule(starts) == rule


# 27 Nov, the user: "the birthdays issue from the user shouldn't only apply to birthdays tho - it should apply for all
# repeated events". Every kind of repeat, imported before its calendar's rule came (kept "every Tuesday", as an older
# Friday kept a birthday), says its calendar's rule from the next read that brings it.
KINDS = [
    ("Sam's Birthday", True, "FREQ=YEARLY", "Yearly"),
    ("Rent", False, "FREQ=MONTHLY", "Monthly"),
    ("Stand-up", False, "FREQ=DAILY", "Every day"),
    ("Book club", False, "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU", "Every other Tuesday"),
    ("Chem lecture", False, "FREQ=WEEKLY;BYDAY=TU,TH", "Tue"),
    ("Practice", False, "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261215T000000Z", "until Dec 15"),
]


def occurrence(title: str, whole: bool, rule: str | None, n: int = 0) -> dict:
    day = f"2026-10-{20 + 7 * n}"
    extra = {"rule": rule} if rule else {}
    if whole:
        nxt = f"2026-10-{21 + 7 * n}"
        return {"id": f"{title}@{n}", "calendar": "home", "title": title, "start": day, "end": nxt, "all_day": True,
                "series": title, **extra}  # fmt: skip
    return mac_event(f"{title}@{n}", "home", title, f"{day}T10:00", f"{day}T11:00", series=title, **extra)


@pytest.mark.parametrize(("title", "whole", "rule", "said"), KINDS)
def test_any_repeat_kept_with_a_wrong_rule_says_its_calendars_rule_once_sent(
    app: App, title: str, whole: bool, rule: str, said: str
) -> None:
    post(app, [HOME], [occurrence(title, whole, None)])  # an older Mac app: no rule
    app.conn.execute("UPDATE series SET rrule = 'FREQ=WEEKLY;BYDAY=TU' WHERE external_id = ?", [f"gcal:{title}"])
    assert "Tue" in pattern(app, title)  # what an older Friday kept
    post(app, [HOME], [occurrence(title, whole, rule)], minutes_later=1)  # the new Mac app sends its rule
    assert said in pattern(app, title), pattern(app, title)
    assert next(r["rrule"] for r in app.table("series") if r["external_id"] == f"gcal:{title}") == rule


def test_a_repeat_whose_rule_changes_in_the_calendar_follows_it(app: App) -> None:
    post(app, [HOME], [occurrence("Book club", False, "FREQ=WEEKLY;BYDAY=TU")])
    assert pattern(app, "Book club").startswith("Every Tuesday")
    post(app, [HOME], [occurrence("Book club", False, "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU")], minutes_later=1)
    assert pattern(app, "Book club").startswith("Every other Tuesday"), pattern(app, "Book club")


def test_a_rule_for_one_repeat_leaves_the_others_as_they_are(app: App) -> None:
    post(app, [HOME], [occurrence("Rent", False, "FREQ=MONTHLY"), occurrence("Gym", False, "FREQ=WEEKLY;BYDAY=TU")])
    post(app, [HOME], [occurrence("Rent", False, "FREQ=YEARLY"), occurrence("Gym", False, "FREQ=WEEKLY;BYDAY=TU")],
         minutes_later=1)  # fmt: skip
    assert pattern(app, "Rent").startswith("Yearly") and pattern(app, "Gym").startswith("Every Tuesday")
