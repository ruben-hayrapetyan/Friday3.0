"""Late work's last chance for work due at midnight (audit, 12 Nov: "late_cutoff at midnight"). Due at 12am, work
belongs to the day that ends then, as everywhere else in Friday (`allocator.day_due`), but the cutoff read it as the
next day's: "before sunday" for homework due as Saturday ended was a week on, where one due a minute earlier, at
11:59pm, had no time at all. Glass box: the cutoff day from a due at midnight. Black box through the commands: due at
midnight Saturday, overdue math homework isn't planned on Sunday or later, as for 11:59pm. The whole system is
tests/system/test_late_cutoff_midnight_system.py."""

from pathlib import Path

import pytest

from friday.core.time import parse_local, parse_utc, to_utc
from friday.planner.late_cutoff import cutoff_after
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app
from tests.commands.test_late_cutoff import SAID


def utc(local: str) -> int:
    return to_utc(parse_local(local), TZ)


SATURDAY_NIGHT = "2026-11-08T00:00"  # 12am Sunday 8 Nov: the end of Saturday the 7th
NEXT_SUNDAY = utc("2026-11-15T00:00")


class TestCutoffDay:
    @pytest.mark.parametrize("due", ["2026-11-07T23:59", SATURDAY_NIGHT])
    def test_due_as_saturday_ends_before_sunday_is_that_sunday(self, due: str) -> None:
        assert cutoff_after(utc(due), "sun", True, TZ) == utc("2026-11-08T00:00")  # no time to do it late

    @pytest.mark.parametrize("due", ["2026-11-07T23:59", SATURDAY_NIGHT])
    def test_due_as_saturday_ends_by_saturday_is_its_end(self, due: str) -> None:
        assert cutoff_after(utc(due), "sat", False, TZ) == utc("2026-11-08T00:00")

    def test_due_as_thursday_ends_before_sunday_is_three_days_on(self) -> None:
        assert cutoff_after(utc("2026-11-06T00:00"), "sun", True, TZ) == utc("2026-11-08T00:00")

    def test_a_minute_after_midnight_is_the_new_day(self) -> None:
        assert cutoff_after(utc("2026-11-08T00:01"), "sun", True, TZ) == NEXT_SUNDAY
        assert cutoff_after(utc("2026-11-08T00:01"), "sun", False, TZ) == utc("2026-11-09T00:00")

    def test_midnight_on_the_night_the_clocks_go_back(self) -> None:
        # 1 Nov 2026: Saturday 31 Oct ends at 12am EDT; "by saturday" is that midnight, not the next Saturday's
        assert cutoff_after(utc("2026-11-01T00:00"), "sat", False, TZ) == utc("2026-11-01T00:00")


def overdue_at_midnight(tmp_path: Path) -> App:
    """Sunday 8 Nov, 9am: Math 1920 HW10 (1 h) was due at 12am, as Saturday ended."""
    app = new_app(tmp_path, now="2026-11-08T09:00", horizon_days=7)
    app.do("add", title="Math 1920 HW10", preset="Assignment", duration_min=60, due=SATURDAY_NIGHT)
    return app


def planned(app: App) -> list[tuple[int, int]]:
    ids = {r["id"] for r in app.table("items") if r["title"].startswith("Math")}
    return sorted(
        (parse_utc(b["start_utc"]), parse_utc(b["end_utc"])) for b in app.table("blocks") if b["item_id"] in ids
    )


def test_due_at_midnight_saturday_it_isnt_planned_the_week_after(tmp_path: Path) -> None:
    app = overdue_at_midnight(tmp_path)
    app.do("rule_add", text=SAID)
    replan(app.conn, app.now_utc)
    assert planned(app) == []  # its last chance, before Sunday, has passed: as for 11:59pm


def test_without_the_rule_it_is_planned_late_as_before(tmp_path: Path) -> None:
    app = overdue_at_midnight(tmp_path)
    replan(app.conn, app.now_utc)
    assert planned(app) and planned(app)[0][0] < NEXT_SUNDAY
