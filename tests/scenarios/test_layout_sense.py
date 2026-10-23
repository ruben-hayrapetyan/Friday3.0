"""Does the plan look sensible to a student? A week of classes and the default rules, through the commands the app
uses, judged as a person would: work in real sittings rather than half-hour scraps, done before it is due, nothing
in class or after bedtime, and a plan that doesn't fall apart when something is added.

Monday 2026-10-19 09:00 in New York; sleep 23:30–07:30 on weekdays (tests/commands/helpers.py).
"""

from datetime import datetime
from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app

CLASSES = [  # (title, days, start, end)
    ("CHEM lecture", "mon,wed,fri", "12:20", "13:10"),
    ("MATH lecture", "mon,wed,fri", "10:10", "11:00"),
    ("CS lecture", "tue,thu", "11:15", "12:05"),
    ("PHYS lab", "tue", "14:30", "16:25"),
    ("CHEM lab", "mon", "13:25", "16:25"),
]


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=7)
    app.do(
        "settings_set",
        key="engine",
        value={"chains": 2, "step_budgets": [{"max_items": 1000, "cold": 150_000, "warm": 80_000}]},
    )
    for title, days, start, end in CLASSES:
        app.do("series_add", title=title, preset="Class", every=days, start=f"2026-10-19T{start}",
               end=f"2026-10-19T{end}")  # fmt: skip
    return app


def assignment(app: App, title: str, due: str, hours: float) -> int:
    found = app.do("add", title=title, preset="Assignment", due=due, duration_min=round(hours * 60))
    return int(found["item"]["id"])


def sittings(app: App, item_id: int) -> list[tuple[datetime, datetime]]:
    """The item's blocks, back-to-back ones joined, in order."""
    out: list[tuple[datetime, datetime]] = []
    for b in sorted(app.do("plan")["blocks"], key=lambda b: b["start"]):
        if b["item_id"] != item_id:
            continue
        start, end = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
        if out and out[-1][1] == start:
            out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def minutes(found: list[tuple[datetime, datetime]]) -> int:
    return sum(int((b - a).total_seconds() // 60) for a, b in found)


def classes(app: App) -> list[tuple[datetime, datetime]]:
    return [
        (datetime.fromisoformat(f["start"]), datetime.fromisoformat(f["end"]))
        for f in app.do("plan")["fixed"]
        if f.get("start") and f.get("preset") == "Class"
    ]


def assert_lived_in(app: App, item_id: int, due: str) -> None:
    """All of it planned, before it is due, never in class, never after bedtime or before waking."""
    found = sittings(app, item_id)
    item = app.do("item", id=item_id)["item"]
    assert minutes(found) >= item["duration_min"], f"{item['title']} isn't all planned: {found}"
    assert all(b <= datetime.fromisoformat(due) for _, b in found), f"{item['title']} ends after its due: {found}"
    for a, b in found:
        assert not any(a < ce and cs < b for cs, ce in classes(app)), f"{item['title']} is in class: {(a, b)}"
        assert a.time() >= datetime(2000, 1, 1, 7, 30).time() or a.hour >= 12, f"before waking: {(a, b)}"
        assert b.time() <= datetime(2000, 1, 1, 23, 30).time() or b.hour < 4, f"after bedtime: {(a, b)}"


def test_a_light_week_puts_each_two_hour_assignment_in_one_sitting(app: App) -> None:
    hw8 = assignment(app, "Math HW8", "2026-10-21T23:59", 2)
    hw9 = assignment(app, "Math HW9", "2026-10-24T23:59", 2)
    app.do("replan")
    for item_id, due in ((hw8, "2026-10-21T23:59"), (hw9, "2026-10-24T23:59")):
        assert_lived_in(app, item_id, due)
        assert len(sittings(app, item_id)) == 1, sittings(app, item_id)


def test_work_due_tomorrow_is_done_first_and_in_real_sittings(app: App) -> None:
    essay = assignment(app, "Essay", "2026-10-20T09:00", 3)
    pset = assignment(app, "Problem set", "2026-10-23T23:59", 3)
    app.do("replan")
    assert_lived_in(app, essay, "2026-10-20T09:00")
    assert_lived_in(app, pset, "2026-10-23T23:59")
    for item_id in (essay, pset):
        assert all((b - a).total_seconds() >= 3600 for a, b in sittings(app, item_id)), sittings(app, item_id)


def test_a_heavy_week_is_on_time_without_overfull_days_or_scraps(app: App) -> None:
    due = ["2026-10-20T23:59", "2026-10-21T23:59", "2026-10-21T23:59", "2026-10-22T23:59", "2026-10-22T23:59",
           "2026-10-23T23:59", "2026-10-23T23:59"]  # fmt: skip
    work = {assignment(app, f"Assignment {n}", d, 3): d for n, d in enumerate(due, 1)}
    app.do("replan")
    by_day: dict[str, int] = {}
    scraps = 0
    for item_id, d in work.items():
        assert_lived_in(app, item_id, d)
        found = sittings(app, item_id)
        assert len(found) <= 3, f"3 hours in {len(found)} pieces: {found}"
        scraps += sum((b - a).total_seconds() < 3600 for a, b in found)
        for a, b in found:
            by_day[a.date().isoformat()] = by_day.get(a.date().isoformat(), 0) + int((b - a).total_seconds() // 60)
    assert max(by_day.values()) <= 8 * 60, by_day
    assert scraps <= 2, "pieces under an hour"


def test_exam_prep_comes_before_the_exam_over_more_than_one_day(app: App) -> None:
    app.do("add", title="CHEM Prelim", preset="Exam", start="2026-10-22T19:30", end="2026-10-22T21:00")
    prep = int(app.do("add", title="Prep: CHEM Prelim", preset="Exam prep", due="2026-10-22T19:30")["item"]["id"])
    app.do("replan")
    assert_lived_in(app, prep, "2026-10-22T19:30")
    assert len({a.date() for a, _ in sittings(app, prep)}) >= 2


def test_adding_an_errand_leaves_planned_homework_in_one_sitting(app: App) -> None:
    hw = assignment(app, "Math HW8", "2026-10-22T23:59", 2)
    app.do("replan")
    before = sittings(app, hw)
    app.do("add", title="Call the bank", preset="Errand")
    app.do("replan")
    assert len(sittings(app, hw)) == 1 and sittings(app, hw) == before
