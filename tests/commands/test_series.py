"""Repeating items as the Repeating settings list them."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_series_list_shows_each_repeat_and_a_stopped_one_can_start_again(app: App) -> None:
    made = app.do("series_add", title="gym", every="mon,wed", duration_min=60)
    (row,) = app.do("series_list")
    assert (row["title"], row["pattern"], row["source"], row["active"]) == ("gym", "Every Mon and Wed", "you", True)
    app.do("series_stop", id=made["id"])
    assert app.do("series_list")[0]["active"] is False
    app.do("series_resume", id=made["id"])
    assert app.do("series_list")[0]["next"] is not None


def test_deleting_a_repeat_removes_whats_undone_keeps_whats_done_and_can_be_undone(app: App) -> None:
    made = app.do("series_add", title="lunch", every="every day", duration_min=30)
    first, *rest = sorted((i for i in app.table("items") if i["title"] == "lunch"), key=lambda i: i["occurrence_date"])
    app.do("done", id=first["id"])
    deleted = app.full("series_delete", payload={"id": made["id"]})
    assert app.do("series_list") == []
    left = [i for i in app.table("items") if i["title"] == "lunch"]
    assert [(i["status"], i["series_id"]) for i in left] == [("done", None)]
    app.do("undo", command_id=deleted.command_id)
    assert len(app.do("series_list")) == 1
    assert len([i for i in app.table("items") if i["title"] == "lunch"]) == 1 + len(rest)


def test_a_meal_whose_window_has_passed_is_skipped_at_night_not_owed(app: App) -> None:
    app.do("add", text="lunch every day 11:30am-2pm 30-45m")
    app.now_utc += 2 * 1440  # two days on, nothing eaten
    app.do("close_day")
    lunches = sorted((i for i in app.table("items") if i["title"] == "lunch"), key=lambda i: i["occurrence_date"])
    assert [i["status"] for i in lunches[:2]] == ["skipped", "skipped"] and lunches[2]["status"] == "todo"


def test_a_daily_break_keeps_its_window_and_one_length_is_exact(app: App) -> None:
    app.do("add", text="Lunch every day 11:30am-2:30pm 15m")
    lunches = sorted((i for i in app.table("items") if i["title"] == "Lunch"), key=lambda i: i["occurrence_date"])
    assert [(i["release_utc"], i["due_utc"]) for i in lunches[:2]] == [
        ("2026-10-19T15:30Z", "2026-10-19T18:30Z"),
        ("2026-10-20T15:30Z", "2026-10-20T18:30Z"),
    ]  # 11:30am–2:30pm New York, every day
    assert {(i["amount"], i["min_units"], i["ideal_units"], i["max_units"]) for i in lunches} == {("elastic", 1, 1, 1)}
