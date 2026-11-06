"""Two dinners in a day, from what you see (5 Nov: "add functionality for multiple of the same meals - like sometimes i
have 4 meals (2 dinners)"): logged or tapped, each kept and named for its place, another offered, the plan keeping
the time clear while you eat it, and the first's routine staying done."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local, to_utc
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    app = new_app(tmp_path)
    app.do("settings_set", key="meal_tracking", value={"on": True})
    app.do(
        "series_add",
        title="Dinner",
        preset="Routine",
        every="day",
        release_offset_min=17 * 60 - 240,
        due_offset_min=21 * 60 - 240,
        min_min=30,
        ideal_min=45,
        max_min=60,
    )  # 5 to 9pm (the day starts at 4am)
    return app


def at(app: App, local: str) -> None:
    app.now_utc = to_utc(parse_local(f"2026-10-19T{local}"), TZ)


def today(app: App) -> list[dict]:
    (day,) = [d for d in app.do("meals")["days"] if d["date"] == "2026-10-19"]
    return sorted(day["meals"], key=lambda m: m["start"])


def dinner_routine(app: App) -> dict:
    (row,) = [r for r in app.table("items") if r["title"] == "Dinner" and r["occurrence_date"] == "2026-10-19"]
    return row


def test_a_second_dinner_logged_after_the_first_is_kept_and_named_second(app: App) -> None:
    at(app, "23:00")
    app.do("meal_log", kind="dinner", start="2026-10-19T18:00", end="2026-10-19T18:45")
    out = app.full("meal_log", payload={"kind": "dinner", "start": "2026-10-19T22:00", "end": "2026-10-19T22:30"})
    assert out.result["message"] == "Logged second dinner, 10pm to 10:30pm"
    assert [(m["kind"], m["nth"], m["start"][11:]) for m in today(app)] == [
        ("dinner", 1, "18:00"),
        ("dinner", 2, "22:00"),
    ]
    assert dinner_routine(app)["status"] == "done"


def test_after_dinner_another_dinner_is_offered_and_tapping_it_holds_the_time(app: App) -> None:
    at(app, "19:00")
    app.do("meal_start", kind="dinner")
    at(app, "19:40")
    app.do("meal_end")
    assert app.do("meals")["again"] == "dinner"
    at(app, "22:00")
    out = app.full("meal_start", payload={"kind": "dinner"})
    assert out.result["message"] == "Eating your second dinner since 10pm"
    meals = app.do("meals")
    assert (meals["eating"]["kind"], meals["eating"]["nth"], meals["again"]) == ("dinner", 2, None)
    away = take_snapshot(app.conn, app.now_utc).away  # what the plan keeps clear while you eat it
    assert away is not None and away[0] == "Dinner"
    at(app, "22:25")
    app.do("meal_end")
    assert [m["nth"] for m in today(app)] == [1, 2] and dinner_routine(app)["status"] == "done"


def test_taking_the_first_dinner_back_leaves_the_routine_done_by_the_second(app: App) -> None:
    at(app, "23:00")
    app.do("meal_log", kind="dinner", start="2026-10-19T18:00", end="2026-10-19T18:45")
    app.do("meal_log", kind="dinner", start="2026-10-19T22:00", end="2026-10-19T22:30")
    first = today(app)[0]
    app.do("meal_remove", id=first["id"])
    (left,) = today(app)
    assert (left["start"][11:], left["nth"]) == ("22:00", 1)  # now the only one, so the first
    assert dinner_routine(app)["status"] == "done"


def test_a_dinner_had_is_not_one_to_skip(app: App) -> None:
    at(app, "20:00")
    app.do("meal_log", kind="dinner", start="2026-10-19T18:00", end="2026-10-19T18:45")
    with pytest.raises(FieldError, match="already recorded"):
        app.do("meal_skip", kind="dinner")


def test_nothing_is_offered_again_before_a_meal_or_while_eating(app: App) -> None:
    at(app, "12:00")
    assert app.do("meals")["again"] is None
    app.do("meal_start", kind="snack")
    at(app, "12:10")
    app.do("meal_end")
    assert app.do("meals")["again"] is None  # a snack is no meal to have another of
