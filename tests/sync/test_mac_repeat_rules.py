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
