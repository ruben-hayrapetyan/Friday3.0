"""A repeat keeps its real moment when you move timezone (10 Nov, your choice: "keep the real moment"). Before, the
times already made stayed (a 2pm New York lecture was 11am in Los Angeles) and those made later took the new zone's
clock (2pm), so a weekly lecture jumped three hours partway through the term."""

from datetime import date
from pathlib import Path

import pytest

from friday.core.series import Series, occurrence_timing
from friday.core.time import parse_utc, to_local
from tests.commands.helpers import TZ, App, new_app

LA = "America/Los_Angeles"
PLAIN = dict(when="fixed", color=None, notes="", location=None)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, New York


def move(app: App, zone: str) -> None:
    app.do("settings_set", key="time", value={"timezone": zone, "horizon_days": 7})


def times(app: App, title: str, zone: str) -> list[str]:
    return [to_local(parse_utc(r["start_utc"]), zone).strftime("%Y-%m-%d %H:%M")
            for r in sorted(app.table("items"), key=lambda r: r["start_utc"] or "")
            if r["title"] == title and r["start_utc"]]  # fmt: skip


# Black box: a weekly lecture through a move, its later weeks made after it.


def test_every_week_keeps_the_real_moment_after_a_move(app: App) -> None:
    app.do("add", title="Lecture", start="2026-10-20T14:00", end="2026-10-20T15:15", every="week", **PLAIN)
    move(app, LA)
    app.at("2027-01-20T09:00").do("materialize")
    hours = {t[-5:] for t in times(app, "Lecture", LA)}
    assert hours == {"11:00"}, hours  # never 2pm Los Angeles time


def test_a_yearly_birthday_keeps_its_date(app: App) -> None:
    app.do("add", title="Remy's Birthday", start="2026-10-22T00:00", end="2026-10-23T00:00", every="rrule:FREQ=YEARLY",
           **PLAIN)  # fmt: skip
    move(app, LA)
    app.at("2027-10-01T09:00").do("materialize")
    assert all(t.endswith("00:00") for t in times(app, "Remy's Birthday", LA))


def test_a_repeat_made_after_the_move_is_in_the_new_zone(app: App) -> None:
    move(app, LA)
    app.do("add", title="Gym", start="2026-10-20T07:00", end="2026-10-20T08:00", every="week", **PLAIN)
    assert {t[-5:] for t in times(app, "Gym", LA)} == {"07:00"}


# Glass box: occurrence_timing reads the repeat's zone, and a whole day the zone you're in.


def series(zone: str | None, length: int = 60, at: str = "2026-10-20T14:00") -> Series:
    return Series(1, {"when": "fixed", "length_min": length}, "FREQ=WEEKLY", at, "2026-10-19T13:00Z", zone=zone)


def test_a_timed_repeat_uses_its_own_zone() -> None:
    from datetime import datetime

    timing = occurrence_timing(series(TZ), datetime(2026, 11, 3, 14, 0), LA)
    assert to_local(parse_utc(timing["start_utc"]), LA).strftime("%H:%M") == "11:00"


def test_a_whole_day_repeat_uses_the_zone_you_are_in() -> None:
    from datetime import datetime

    timing = occurrence_timing(series(TZ, 1440, "2026-10-22T00:00"), datetime(2027, 10, 22, 0, 0), LA)
    assert to_local(parse_utc(timing["start_utc"]), LA).strftime("%Y-%m-%d %H:%M") == "2027-10-22 00:00"


def test_a_repeat_without_a_zone_uses_the_zone_you_are_in() -> None:
    from datetime import datetime

    timing = occurrence_timing(series(None), datetime(2026, 11, 3, 14, 0), LA)
    assert to_local(parse_utc(timing["start_utc"]), LA).strftime("%H:%M") == "14:00"


def test_repeats_made_before_get_the_zone_you_have(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Lecture", start="2026-10-20T14:00", end="2026-10-20T15:15", every="week", **PLAIN)
    (row,) = app.table("series")
    assert row["zone"] == TZ and date.fromisoformat(row["dtstart_local"][:10]) == date(2026, 10, 20)


def test_the_migration_gives_earlier_repeats_the_zone_you_have(tmp_path: Path) -> None:
    from friday.core.db import MIGRATIONS

    app = new_app(tmp_path)
    app.do("add", title="Lecture", start="2026-10-20T14:00", end="2026-10-20T15:15", every="week", **PLAIN)
    app.conn.execute("UPDATE series SET zone = NULL")  # as a repeat saved before 029
    sql = (MIGRATIONS / "029_series_zone.sql").read_text()
    app.conn.execute(sql.split(";")[1])  # the UPDATE after the ALTER
    assert [r["zone"] for r in app.table("series")] == [TZ]
