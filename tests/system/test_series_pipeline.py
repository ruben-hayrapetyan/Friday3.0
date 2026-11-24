"""Repeats, the whole pipeline (tests/features.toml: series; 24 Nov, the user: "go through every single functionality of
the app and build an extensive test suite"): a real `fridayd serve` in its own folder, `repeat`, `skip` and
`materialize` sent over HTTP as the app sends them, and what they did read back through the items, the events,
Settings → Repeating's list, the timer and the plan."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("series"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def today() -> date:
    """Friday's day (it starts at 4am), as the server counts it."""
    return (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date()


def refused(friday: Friday, verb: str, **body: Any) -> str:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"]


def titled(friday: Friday, title: str, status: str = "all") -> list[dict]:
    return [i for i in friday.q("items", status=status) if i["title"] == title]


def day_of(item: dict) -> str:
    """The day a repeat's time is on: its due's, else when it opens, else its start's."""
    return (item["due"] or item["release"] or item["start"])[:10]


def row_of(friday: Friday, series_id: int) -> dict:
    (row,) = [r for r in friday.q("series_list") if r["id"] == series_id]
    return row


def planned(friday: Friday) -> None:
    """Until the plan has seen every change made so far."""

    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, timeout=180)


def blocks_of(friday: Friday, item_id: int, days: int = 10) -> list[dict]:
    start = today()
    plan = friday.q("plan", start=f"{start}T04:00", end=f"{start + timedelta(days=days)}T04:00")
    return [b for b in plan["blocks"] if b["item_id"] == item_id]


# ---- repeat ----------------------------------------------------------------------------------------------------------


def test_repeat_makes_a_task_the_first_of_a_daily_series_due_each_day_at_its_time(friday: Friday) -> None:
    first = today() + timedelta(days=2)
    task = friday.c("add", title="Water plants", duration_min=15, due=f"{first}T18:00")["item"]
    out = friday.c("repeat", id=task["id"], every="day")
    assert out["rule"] == "FREQ=DAILY" and out["occurrences"] > 5
    item = friday.q("item", id=task["id"])["item"]
    assert item["series_id"] == out["id"]  # the one you had is the first time, not a copy beside it
    times = sorted(titled(friday, "Water plants", "todo"), key=lambda i: i["due"])
    assert times[0]["id"] == task["id"]
    assert [i["due"] for i in times[:4]] == [f"{first + timedelta(days=n)}T18:00" for n in range(4)]
    assert {i["series_id"] for i in times} == {out["id"]} and len(times) == out["occurrences"]
    row = row_of(friday, out["id"])
    assert (row["title"], row["source"], row["active"], row["fixed"]) == ("Water plants", "you", True, False)
    assert row["next_id"] == task["id"]


def test_repeat_makes_an_event_weekly_on_its_own_day_and_time(friday: Friday) -> None:
    on = today() + timedelta(days=3)
    event = friday.c("add", title="Salsa night", when="fixed", start=f"{on}T20:00", end=f"{on}T21:30")["item"]
    out = friday.c("repeat", id=event["id"], every="week")
    assert out["rule"].startswith("FREQ=WEEKLY")
    plan = friday.q("plan", start=f"{on}T04:00", end=f"{on + timedelta(days=15)}T04:00")
    salsa = sorted((f["start"], f["end"]) for f in plan["fixed"] if f["title"] == "Salsa night")
    assert salsa == [(f"{on + timedelta(days=n)}T20:00", f"{on + timedelta(days=n)}T21:30") for n in (0, 7, 14)]
    assert row_of(friday, out["id"])["fixed"] is True


def test_repeat_on_days_its_own_day_isnt_keeps_it_beside_the_repeat(friday: Friday) -> None:
    # a Saturday's event made to repeat "every weekday": it stays, and the repeat starts on the weekdays (8 Nov)
    on = today() + timedelta(days=(5 - today().weekday()) % 7 or 7)  # the next Saturday
    event = friday.c("add", title="Lab shift", when="fixed", start=f"{on}T10:00", end=f"{on}T12:00")["item"]
    out = friday.c("repeat", id=event["id"], every="weekday")
    plan = friday.q("plan", start=f"{on}T04:00", end=f"{on + timedelta(days=7)}T04:00")
    days = sorted(f["start"][:10] for f in plan["fixed"] if f["title"] == "Lab shift")
    assert days[0] == str(on)  # still there
    assert days[1:] == [str(on + timedelta(days=n)) for n in (2, 3, 4, 5, 6)]  # Mon–Fri after it, not Sunday
    assert friday.q("item", id=event["id"])["item"]["series_id"] == out["id"]


def test_repeat_refuses_what_repeats_already_or_an_unreadable_repeat(friday: Friday) -> None:
    task = friday.c("add", title="Stretch", duration_min=10, due=f"{today() + timedelta(days=1)}T09:00")["item"]
    assert "isn't a repeat" in refused(friday, "repeat", id=task["id"], every="whenever I feel like it")
    assert "say how it repeats" in refused(friday, "repeat", id=task["id"], every="every")
    assert friday.q("item", id=task["id"])["item"]["series_id"] is None  # nothing half made
    friday.c("repeat", id=task["id"], every="mon,wed")
    assert "repeats already" in refused(friday, "repeat", id=task["id"], every="day")
    assert refused(friday, "repeat", id=999_999, every="day")  # no such item


def test_repeat_on_given_weekdays_lands_only_on_them(friday: Friday) -> None:
    task = friday.c("add", title="Gym", duration_min=60, due=f"{today() + timedelta(days=1)}T21:00")["item"]
    out = friday.c("repeat", id=task["id"], every="tue,thu")
    assert "BYDAY=TU,TH" in out["rule"]
    later = [i for i in titled(friday, "Gym", "todo") if i["id"] != task["id"]]
    assert later and {date.fromisoformat(i["due"][:10]).weekday() for i in later} == {1, 3}


# ---- skip ------------------------------------------------------------------------------------------------------------


def test_skip_takes_one_time_out_and_the_plan_and_repeating_list_follow(friday: Friday) -> None:
    out = friday.c(
        "series_add", title="Read news", every="day", duration_min=30, start_date=str(today() + timedelta(days=1))
    )
    times = sorted(titled(friday, "Read news", "todo"), key=day_of)
    first, second = times[0], times[1]
    assert row_of(friday, out["id"])["next_id"] == first["id"]
    planned(friday)
    assert blocks_of(friday, first["id"])  # planned before it's skipped
    skipped = friday.c("skip", id=first["id"])["item"]
    assert skipped["status"] == "skipped"
    assert [i["id"] for i in titled(friday, "Read news", "skipped")] == [first["id"]]
    assert second["id"] in {i["id"] for i in titled(friday, "Read news", "todo")}  # the others stay as they are
    assert row_of(friday, out["id"])["next_id"] == second["id"]
    planned(friday)
    assert blocks_of(friday, first["id"]) == []  # no longer planned
    assert blocks_of(friday, second["id"])


def test_skip_refuses_a_one_off_and_a_time_already_done(friday: Friday) -> None:
    one_off = friday.c("add", title="Return library book", duration_min=15, due=f"{today() + timedelta(days=2)}T17:00")
    said = refused(friday, "skip", id=one_off["item"]["id"])
    assert "doesn't repeat; drop it instead" in said
    assert friday.q("item", id=one_off["item"]["id"])["item"]["status"] == "todo"
    friday.c("series_add", title="Floss", every="day", duration_min=5, start_date=str(today() + timedelta(days=1)))
    first = sorted(titled(friday, "Floss", "todo"), key=lambda i: i["id"])[0]
    friday.c("done", id=first["id"])
    assert "is done that day" in refused(friday, "skip", id=first["id"])
    assert friday.q("item", id=first["id"])["item"]["status"] == "done"  # still done, not quietly skipped
    assert refused(friday, "skip", id=999_999)


def test_skip_stops_the_timer_running_on_that_time(friday: Friday) -> None:
    friday.c("series_add", title="Practice piano", every="day", duration_min=45, start_date=str(today()))
    first = sorted(titled(friday, "Practice piano", "todo"), key=lambda i: i["id"])[0]
    friday.c("start", id=first["id"])
    assert friday.q("status")["timer"]["item_id"] == first["id"]
    friday.c("skip", id=first["id"])
    assert friday.q("status")["timer"] is None  # not left counting on a skipped time
    assert friday.q("item", id=first["id"])["item"]["status"] == "skipped"


# ---- materialize -----------------------------------------------------------------------------------------------------


def test_materialize_makes_the_times_a_longer_reach_needs_and_only_once(friday: Friday) -> None:
    time = friday.q("settings")["time"]
    friday.c("settings_set", key="time", value={**time, "materialize_days": 5})
    out = friday.c("series_add", title="Journal", every="day", duration_min=10, start_date=str(today()))
    short = len(titled(friday, "Journal", "todo"))
    assert 4 <= short <= 7  # about five days' worth
    friday.c("settings_set", key="time", value={**time, "materialize_days": 20})
    made = friday.c("materialize")["message"]
    longer = titled(friday, "Journal", "todo")
    assert 19 <= len(longer) <= 22
    n = int(made.split()[0])
    assert n >= len(longer) - short  # this series' new times among them (others' too)
    assert made.endswith("new occurrences")
    days = sorted(day_of(i) for i in longer)
    assert len(set(days)) == len(days)  # one a day, none twice
    assert friday.c("materialize")["message"] == "0 new occurrences"  # everything's there already
    assert len(titled(friday, "Journal", "todo")) == len(longer)
    assert row_of(friday, out["id"])["next"] is not None
    friday.c("settings_set", key="time", value=time)


def test_materialize_leaves_a_stopped_repeat_stopped(friday: Friday) -> None:
    out = friday.c("series_add", title="Call grandma", every="sat", duration_min=30, start_date=str(today()))
    assert titled(friday, "Call grandma", "todo")
    friday.c("series_stop", id=out["id"])
    assert titled(friday, "Call grandma", "todo") == []
    friday.c("materialize")
    assert titled(friday, "Call grandma", "todo") == []  # the nightly job doesn't bring it back
    assert row_of(friday, out["id"])["active"] is False


def test_materialize_doesnt_make_again_a_time_you_dropped(friday: Friday) -> None:
    # a time dropped stays dropped: materialize counts it as made, so it isn't made again
    out = friday.c("series_add", title="Take vitamins", every="day", duration_min=5, start_date=str(today()))
    times = sorted(titled(friday, "Take vitamins", "todo"), key=day_of)
    friday.c("drop", id=times[2]["id"])
    friday.c("materialize")
    after = titled(friday, "Take vitamins", "all")
    on_that_day = [i for i in after if day_of(i) == day_of(times[2])]
    assert [(i["id"], i["status"]) for i in on_that_day] == [(times[2]["id"], "dropped")]
    assert row_of(friday, out["id"])["active"] is True
