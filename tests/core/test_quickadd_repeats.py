"""Repeats typed without the editor (8 Nov, a user: "when creating new events manually, they don't repeat as they
should"). Glass box: the days read and the rule. Black box through `add`: the times made, on their weekdays, the first
on the first of its days. A single day stays one day."""

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from friday.core.quickadd import days_said, parse
from friday.core.time import parse_utc, to_local
from tests.commands.helpers import TZ, new_app

SUNDAY = datetime(2026, 11, 8, 15, 0)


@pytest.mark.parametrize(
    ("text", "rule", "title"),
    [
        ("gym mon wed fri 7am 1h", "FREQ=WEEKLY;BYDAY=MO,WE,FR", "gym"),
        ("standup every weekday 9am 15m", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "standup"),
        ("piano lessons mondays 4pm", "FREQ=WEEKLY;BYDAY=MO", "piano lessons"),
        ("club weekly on tuesdays at 6pm", "FREQ=WEEKLY;BYDAY=TU", "club"),
        ("tutoring tuesdays and thursdays 5pm", "FREQ=WEEKLY;BYDAY=TU,TH", "tutoring"),
        ("team meeting every other thursday 3pm", "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH", "team meeting"),
    ],
)
def test_a_repeat_said_without_the_editor(text: str, rule: str, title: str) -> None:
    fields = parse(text, SUNDAY).fields
    assert fields.get("rrule") == rule and fields["title"] == title


@pytest.mark.parametrize(
    "text", ["salsa friday 8pm", "groceries sat", "call mom sat 3pm 30m", "dinner with sam fri 7pm"]
)
def test_one_day_stays_one_day(text: str) -> None:
    assert "rrule" not in parse(text, SUNDAY).fields


def test_the_days_read() -> None:
    assert days_said(["mon", "wed", "fri", "7am"], 0) == (["MO", "WE", "FR"], 3, False)
    assert days_said(["tuesdays", "and", "thursdays", "5pm"], 0) == (["TU", "TH"], 3, True)
    assert days_said(["mon", "and", "then"], 0) == (["MO"], 1, False)  # the "and" isn't a day's


@pytest.mark.parametrize(
    ("text", "weekdays", "first"),
    [
        ("gym mon wed fri 7am 1h", {0, 2, 4}, date(2026, 11, 9)),
        ("standup every weekday 9am 15m", {0, 1, 2, 3, 4}, date(2026, 11, 9)),
        ("piano lessons mondays 4pm", {0}, date(2026, 11, 9)),
        ("club weekly on tuesdays at 6pm", {1}, date(2026, 11, 10)),
        ("team meeting every other thursday 3pm", {3}, date(2026, 11, 12)),  # this Thursday, then every other
    ],
)
def test_added_it_repeats_on_its_days_from_the_first(text: str, weekdays: set[int], first: date) -> None:
    app = new_app(Path(tempfile.mkdtemp()), now="2026-11-08T15:00")
    app.do("add", text=text)
    days = sorted(to_local(parse_utc(i["start_utc"]), TZ).date() for i in app.table("items"))
    assert len(days) > 5 and days[0] == first and {d.weekday() for d in days} == weekdays
    if "other" in text:
        assert (days[1] - days[0]).days == 14
