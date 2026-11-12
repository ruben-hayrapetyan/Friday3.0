"""Settings and paces through the registry (DESIGN §17): a pace setting changed in part, switching pace for some
days or until a date, the refusals in words, deleting a pace your week uses, and a day override's checks."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_weekly_pace_keeps_the_default_pace(app: App) -> None:
    app.do("settings_set", key="pace", value={"weekly": {"sat": "Easy"}})
    pace = app.do("settings")["pace"]
    assert pace["default"] == "Normal" and pace["weekly"] == {"sat": "Easy"}


def test_a_pace_until_a_day_said_in_words_ends_that_day(app: App) -> None:
    out = app.do("pace", name="easy", until="friday")
    assert out["end_date"] == "2026-10-23"
    assert out["message"] == "Easy pace, today through Fri Oct 23. Then back to Normal."


def test_switching_back_to_the_default_pace_says_just_that(app: App) -> None:
    app.do("pace", name="easy")
    assert app.do("pace", name="normal")["message"] == "Normal pace from today."


@pytest.mark.parametrize(
    ("given", "field", "said"),
    [
        ({"name": "easy", "for_days": 0}, "for_days", "must be at least 1"),
        ({"name": "easy", "until": "whenever"}, "until", "'whenever' isn't a date"),
        ({"name": "nope"}, "name", "no pace called nope; saved: Normal, Easy, Push"),
        ({"capacity": 5}, "dials", "less than or equal to 1.5"),
    ],
)
def test_a_pace_that_cannot_be_set_says_why(app: App, given: dict, field: str, said: str) -> None:
    with pytest.raises(FieldError, match=said) as refused:
        app.do("pace", **given)
    assert refused.value.field == field
    assert app.table("pace_periods") == []


def test_a_saved_pace_with_a_dial_out_of_range_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="greater than or equal to 0.3") as refused:
        app.do("pace_save", name="Gentle", capacity=-3)
    assert refused.value.field == "dials" and "Gentle" not in app.do("settings")["paces"]


def test_deleting_a_pace_that_does_not_exist_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="no pace called nope"):
        app.do("pace_delete", name="nope")


def test_deleting_a_pace_your_week_uses_puts_those_days_back_to_the_default(app: App) -> None:
    app.do("settings_set", key="pace", value={"weekly": {"sat": "Easy", "sun": "Push"}})
    assert app.do("pace_delete", name="easy")["message"] == "Deleted pace Easy"
    settings = app.do("settings")
    assert settings["pace"]["weekly"] == {"sun": "Push"} and "Easy" not in settings["paces"]


def test_a_day_override_with_a_time_that_does_not_exist_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="'25:00' is not a time like 04:00") as refused:
        app.do("day_override", date="2026-10-21", bedtime="25:00")
    assert refused.value.field == "bedtime"  # said on the time, not the date
    with pytest.raises(ValidationError, match="margin_min"):
        app.do("day_override", date="2026-10-21", margin_min=-5)
    assert app.table("day_overrides") == []


def test_a_night_that_is_not_its_own_times_is_refused_in_words(app: App) -> None:
    with pytest.raises(FieldError, match="mon: give its times") as refused:
        app.do("settings_set", key="sleep", value={"mon": "bad"})
    assert refused.value.field == "value"
