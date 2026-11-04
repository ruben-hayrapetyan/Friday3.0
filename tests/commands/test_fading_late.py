"""Work that matters less the longer it's overdue (3 Nov: "have the importance of doing a reading on time deteriorate
as time goes on, make readings pointless once late" was what the AI made of it; chosen: "Half every 3 days", and once
faded it stays, planned only in spare time). By default the later work is, the more urgent it gets: a reading a week
late took 9am ahead of a problem set due that afternoon. Fading, the problem set goes first."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from friday.core.items import Item
from friday.core.settings import FadingLate, PointlessLate
from friday.core.time import parse_utc
from friday.planner.build import fading
from tests.commands.helpers import App, new_app

READINGS = {"kinds": ["Reading"], "titles": [], "half_life_days": 3}
NOW = parse_utc("2026-10-19T13:00Z")  # the helpers' clock: 09:00 in New York


def item(preset: str | None = "Reading", due: str | None = "2026-10-12T13:00Z", **more) -> Item:  # type: ignore[no-untyped-def]
    return Item(id=1, title="Chapter 4", preset=preset, due_utc=due, **more)


def settings(fade: dict | None = None, pointless: tuple[str, ...] = ()) -> dict:
    return {"fading_late": FadingLate(**(fade or READINGS)), "pointless_late": PointlessLate(kinds=pointless)}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def first(app: App, title: str) -> str | None:
    blocks = app.do("plan", start="2026-10-19T00:00", end="2026-10-26T00:00")["blocks"]
    return min((b["start"] for b in blocks if b["title"] == title), default=None)


class TestGlassBox:
    def test_halves_every_half_life(self) -> None:
        fade = FadingLate(**READINGS)
        assert fade.factor(0) == 1
        assert fade.factor(3 * 1440) == pytest.approx(0.5)
        assert fade.factor(7 * 1440) == pytest.approx(0.198, abs=0.001)  # a week late: about a fifth

    def test_a_week_late_reading_keeps_a_fifth_of_its_importance(self) -> None:
        assert fading(item(), settings(), NOW) == pytest.approx(0.198, abs=0.001)

    def test_on_time_or_without_a_due_it_is_whole(self) -> None:
        assert fading(item(due="2026-10-25T13:00Z"), settings(), NOW) == 1
        assert fading(item(due=None), settings(), NOW) == 1

    def test_other_kinds_don_t_fade(self) -> None:
        assert fading(item(preset="Assignment"), settings(), NOW) == 1

    def test_a_title_pattern_fades_too(self) -> None:
        fade = {"kinds": [], "titles": ["chapter"], "half_life_days": 3}
        assert fading(item(preset=None), settings(fade), NOW) < 1

    def test_pointless_once_late_wins(self) -> None:
        assert fading(item(), settings(pointless=("Reading",)), NOW) == 1  # never planned late at all, rather
        assert fading(item(expires=True), settings(), NOW) == 1

    def test_the_half_life_must_be_sensible(self) -> None:
        with pytest.raises(ValueError):
            FadingLate(half_life_days=0)


class TestBlackBox:
    @given(days=st.floats(min_value=0, max_value=60), more=st.floats(min_value=0, max_value=60))
    def test_never_matters_more_for_being_later_and_never_drops_to_nothing(self, days: float, more: float) -> None:
        fade = FadingLate(**READINGS)
        assert 0 < fade.factor((days + more) * 1440) <= fade.factor(days * 1440) <= 1

    def test_by_default_the_old_reading_takes_the_morning(self, app: App) -> None:
        app.do("add", title="Old reading", preset="Reading", duration_min=120, due="2026-10-12T17:00")
        app.do("add", title="Problem set", preset="Assignment", duration_min=180, due="2026-10-19T14:00")
        app.do("replan")
        assert first(app, "Old reading") < first(app, "Problem set")

    def test_fading_the_work_still_on_time_comes_first(self, app: App) -> None:
        app.do("settings_set", key="fading_late", value=READINGS)
        app.do("add", title="Old reading", preset="Reading", duration_min=120, due="2026-10-12T17:00")
        app.do("add", title="Problem set", preset="Assignment", duration_min=180, due="2026-10-19T14:00")
        app.do("replan")
        assert first(app, "Problem set") < first(app, "Old reading")

    def test_a_faded_reading_is_still_planned_when_there_is_room(self, app: App) -> None:
        app.do("settings_set", key="fading_late", value=READINGS)
        app.do("add", title="Ancient reading", preset="Reading", duration_min=60, due="2026-09-01T17:00")
        app.do("replan")
        assert first(app, "Ancient reading") is not None  # stays on the list, in spare time

    def test_a_task_says_it_fades(self, app: App) -> None:
        app.do("settings_set", key="fading_late", value=READINGS)
        reading = app.do("add", title="Chapter 4", preset="Reading", duration_min=60, due="2026-10-22T17:00")["item"]
        task = app.do("add", title="Essay", preset="Assignment", duration_min=60, due="2026-10-22T17:00")["item"]
        assert app.do("item", id=reading["id"])["item"]["fading_late"] is True
        assert app.do("item", id=task["id"])["item"]["fading_late"] is False

    def test_undo_brings_back_the_old_order(self, app: App) -> None:
        set_it = app.full("settings_set", payload={"key": "fading_late", "value": READINGS})
        app.do("undo", command_id=set_it.command_id)
        assert app.do("settings")["fading_late"]["kinds"] == []
