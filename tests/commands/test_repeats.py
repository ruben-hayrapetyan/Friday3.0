"""Making something you have repeat: an event or a task, from its own date and time, kept as the first time."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import new_app


def test_an_event_you_have_can_be_made_to_repeat_and_stays_the_first_time(tmp_path: Path) -> None:
    # 26 Oct: Salsa added on Friday couldn't be made to repeat, by Claude or in its drawer.
    app = new_app(tmp_path)
    salsa = app.do("add", title="Salsa", when="fixed", start="2026-10-23T18:15", end="2026-10-23T19:30")["item"]["id"]
    out = app.do("repeat", id=salsa, every="week")
    fridays = sorted((i["start_utc"], i["id"]) for i in app.table("items") if i["title"] == "Salsa")
    assert fridays[0] == ("2026-10-23T22:15Z", salsa)  # this Friday is still the one you made
    assert [s for s, _ in fridays[1:4]] == ["2026-10-30T22:15Z", "2026-11-06T23:15Z", "2026-11-13T23:15Z"]  # 6:15pm
    assert len({s for s, _ in fridays}) == len(fridays) and out["occurrences"] >= 10
    with pytest.raises(FieldError, match="repeats already"):
        app.do("repeat", id=salsa, every="week")


def test_a_task_made_to_repeat_keeps_its_due_each_week(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    task = app.do("add", title="Weekly reflection", duration_min=30, due="2026-10-23T17:00")["item"]["id"]
    app.do("log", id=task, start="2026-10-19T08:00", end="2026-10-19T08:15")
    app.do("repeat", id=task, every="week")
    dues = sorted((i["due_utc"], i["id"]) for i in app.table("items") if i["title"] == "Weekly reflection")
    assert dues[0] == ("2026-10-23T21:00Z", task) and dues[1][0] == "2026-10-30T21:00Z"
    assert next(i for i in app.do("items") if i["id"] == task)["done_min"] == 15  # what you'd done stays with it
