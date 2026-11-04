"""A birthday the Mac gives as 12:00 AM to 11:59 PM (3 Nov: "don't make full day events actually look like they take
the full day"), the whole system: a real `fridayd serve`, the Mac app's post over HTTP, the sync job reading it, and
the plan read back as the app reads it: a whole-day event, with work still planned on that day."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("whole_day"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def test_a_birthday_timed_over_its_day_is_shown_whole_day_and_leaves_the_day_free(friday: Friday) -> None:
    zone = ZoneInfo(TZ)
    day = (datetime.now(zone) + timedelta(days=2)).date()
    midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
    calendar = {"id": "home", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}
    birthday = {"id": "b", "calendar": "home", "title": "Jasper's Birthday", "start": midnight.isoformat(),
                "end": (midnight + timedelta(hours=23, minutes=59)).isoformat()}  # fmt: skip
    since, until = midnight - timedelta(days=7), midnight + timedelta(days=30)
    answer = friday.http.post("/api/c/mac_sync", headers={"X-Friday-Client": "mac"},
                              json={"calendars": [calendar], "events": [birthday], "since": since.isoformat(),
                                    "until": until.isoformat()})  # fmt: skip
    assert answer.status_code == 200, answer.text
    friday.c("add", title="Essay", preset="Assignment", duration_min=240, due=f"{day}T22:00",
             release=f"{day}T00:00")  # fmt: skip
    window = {"start": f"{day - timedelta(days=3)}T00:00", "end": f"{day + timedelta(days=1)}T00:00"}

    def read() -> dict | None:
        plan = friday.q("plan", **window)
        fixed = [f for f in plan["fixed"] if f["title"] == "Jasper's Birthday"]
        return plan if fixed and any(b["title"] == "Essay" for b in plan["blocks"]) else None

    plan = friday.until(read)
    (shown,) = [f for f in plan["fixed"] if f["title"] == "Jasper's Birthday"]
    assert shown["start"] == f"{day}T00:00" and shown["end"] == f"{day + timedelta(days=1)}T00:00"
    # not busy: the essay, which can only be done that day, is planned in it
    assert all(b["start"].startswith(str(day)) for b in plan["blocks"] if b["title"] == "Essay")


def test_the_week_header_reads_the_days_deadlines_and_its_whole_day_events(friday: Friday) -> None:
    # 3 Nov: the header holds whole-day events; a day's deadlines are a red count there (web/src/plan/DueCount.tsx)
    zone = ZoneInfo(TZ)
    day = (datetime.now(zone) + timedelta(days=4)).date()
    friday.c("add", title="Lab report", preset="Assignment", duration_min=60, due=f"{day}T17:00")
    friday.c("add", title="Problem set", preset="Assignment", duration_min=60, due=f"{day}T23:59")
    week = friday.q("calendar", start=str(day), days=1)
    assert [(d["title"], d["due"]) for d in week["dues"]] == [
        ("Lab report", f"{day}T17:00"),
        ("Problem set", f"{day}T23:59"),
    ]


def test_a_day_with_sixty_deadlines_and_a_pile_of_whole_day_events_comes_back_whole(friday: Friday) -> None:
    # 3 Nov stress test: the header and the month keep them to a count and three rows; nothing may be lost on the way
    zone = ZoneInfo(TZ)
    day = (datetime.now(zone) + timedelta(days=5)).date()
    after = day + timedelta(days=1)
    for n in range(60):
        friday.c("add", title=f"Problem {n} " + "of a very long reading " * (n % 3), preset="Assignment",
                 duration_min=15, due=f"{day}T{8 + n % 14:02d}:{n % 60:02d}")  # fmt: skip
    for n in range(8):
        friday.c("add", title=f"Whole day {n}", when="fixed", start=f"{day}T00:00", end=f"{after}T00:00",
                 blocks_time=False)  # fmt: skip
    dues = friday.q("calendar", start=str(day), days=1)["dues"]
    assert len([d for d in dues if d["title"].startswith("Problem ")]) == 60
    assert [d["due"] for d in dues] == sorted(d["due"] for d in dues)
    fixed = friday.q("plan", start=f"{day}T00:00", end=f"{after}T00:00")["fixed"]
    assert sorted(f["title"] for f in fixed if f["title"].startswith("Whole day")) == [
        f"Whole day {n}" for n in range(8)
    ]


def test_the_brief_gives_todays_whole_day_events_as_whole_days_for_all_day(friday: Friday) -> None:
    # C36's leftover: the brief listed them at "12am"; web/src/dialogs/fixedToday.ts reads midnight-to-midnight as
    # "All day", so the brief has to hand them over as whole days, beside today's timed events
    today = datetime.now(ZoneInfo(TZ)).date()
    after = today + timedelta(days=1)
    friday.c("add", title="Reading Day", when="fixed", start=f"{today}T00:00", end=f"{after}T00:00",
             blocks_time=False)  # fmt: skip
    friday.c("add", title="Since yesterday", when="fixed", start=f"{today - timedelta(days=1)}T00:00",
             end=f"{after}T00:00", blocks_time=False)  # fmt: skip
    friday.c("add", title="Lecture", when="fixed", start=f"{today}T23:00", end=f"{today}T23:50")
    fixed = {f["title"]: (f["start"], f["end"]) for f in friday.q("brief")["fixed"]}
    assert fixed["Reading Day"] == (f"{today}T00:00", f"{after}T00:00")
    assert fixed["Since yesterday"] == (f"{today - timedelta(days=1)}T00:00", f"{after}T00:00")
    assert fixed["Lecture"] == (f"{today}T23:00", f"{today}T23:50")
