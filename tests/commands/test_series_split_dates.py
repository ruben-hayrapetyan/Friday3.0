"""A repeat changed from a date on keeps its dates (7 Nov: twenty-two yearly birthdays, each edited from today so
their time was free, all started again today, as a plain yearly rule takes its date from the start). Black box through
`series_edit`, then the inside. Monday 2026-10-19 in New York."""

from datetime import date, datetime
from pathlib import Path

import pytest

from friday.commands.series import continued_from
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def days(app: App, title: str) -> list[str]:
    found = [i for i in app.table("items") if i["title"] == title and i["status"] == "todo"]
    return sorted(app.do("item", id=i["id"])["item"]["start"][:10] for i in found)


def made(app: App, title: str, start: str, end: str, every: str) -> int:
    return app.do("series_add", title=title, when="fixed", start=start, end=end, every=every)["id"]


class TestBlackBox:
    def test_a_yearly_birthday_stays_on_its_day(self, app: App) -> None:
        bday = made(app, "Remy's Birthday", "2026-10-22T00:00", "2026-10-23T00:00", "rrule:FREQ=YEARLY")
        app.do("series_edit", id=bday, blocks_time=False)
        assert days(app, "Remy's Birthday") == ["2026-10-22"]

    def test_a_weekly_one_from_its_first_day_keeps_its_weekday(self, app: App) -> None:
        club = made(app, "club", "2026-10-22T18:00", "2026-10-22T19:00", "rrule:FREQ=WEEKLY")  # a Thursday
        app.do("series_edit", id=club, title="book club")
        assert [date.fromisoformat(d).weekday() for d in days(app, "book club")] == [3] * len(days(app, "book club"))
        assert days(app, "book club")[0] == "2026-10-22"

    def test_from_a_later_date_too(self, app: App) -> None:
        bday = made(app, "Remy's Birthday", "2026-10-22T00:00", "2026-10-23T00:00", "rrule:FREQ=YEARLY")
        app.do("series_edit", id=bday, from_date="2026-12-01", title="Remy's bday")
        assert days(app, "Remy's Birthday") == ["2026-10-22"]  # this year's stays as it was

    def test_named_days_are_as_before(self, app: App) -> None:
        gym = made(app, "gym", "2026-10-19T07:00", "2026-10-19T08:00", "rrule:FREQ=WEEKLY;BYDAY=MO,WE")
        app.do("series_edit", id=gym, from_date="2026-10-20", title="lift")
        assert days(app, "lift")[0] == "2026-10-21"


class TestInside:
    def series(self, rule: str, start: str) -> dict:
        return {"rrule": rule, "dtstart_local": start}

    def test_the_next_time_on_or_after_the_day(self) -> None:
        yearly = self.series("FREQ=YEARLY", "2026-11-10T00:00")
        assert continued_from(yearly, date(2026, 11, 7)) == datetime(2026, 11, 10)
        assert continued_from(yearly, date(2026, 11, 10)) == datetime(2026, 11, 10)
        assert continued_from(yearly, date(2026, 11, 11)) == datetime(2027, 11, 10)

    def test_monthly_keeps_its_day_of_the_month(self) -> None:
        assert continued_from(self.series("FREQ=MONTHLY", "2026-10-05T09:30"), date(2026, 10, 19)) == datetime(
            2026, 11, 5, 9, 30
        )

    def test_one_with_nothing_left_starts_on_the_day(self) -> None:
        over = self.series("FREQ=WEEKLY;UNTIL=20261020T235959", "2026-10-01T09:00")
        assert continued_from(over, date(2026, 11, 2)) == datetime(2026, 11, 2, 9, 0)
