"""The "Adjust new estimates automatically" switch keeps your choice from the first click (Friday Notes, 23 Nov: the
first click said "Nothing learned yet" and the switch stayed off until Friday was quit and reopened; older than 0.6.6).
With nothing learned, the click saved nothing, and lengths learned later took "off". Now the choice is kept as you
make it, and lengths learned later are used at once. Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from friday.commands.learned import keep
from tests.commands.helpers import App, new_app

MODEL = {"model": {"n": 6}, "better": True, "error": 0.2, "error_before": 0.35}  # a fit, as read


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def learned(app: App) -> None:
    """Lengths learned, as the nightly fit (or the lengths job) keeps them."""
    keep(app.conn, 1, "learned_durations", dict(MODEL))


def test_switched_on_before_anything_is_learned_it_stays_on(app: App) -> None:
    said = app.do("learn_module", module="durations", use=True)["message"]
    assert said == "On: Friday adjusts new estimates once it has learned how long things take"
    assert app.do("learning")["durations_wanted"] is True  # the switch shows on


def test_lengths_learned_later_are_used_at_once(app: App) -> None:
    app.do("learn_module", module="durations", use=True)
    learned(app)
    assert app.do("learning")["durations"]["in_use"] is True


def test_switched_off_they_are_not(app: App) -> None:
    app.do("learn_module", module="durations", use=True)
    app.do("learn_module", module="durations", use=False)
    learned(app)
    assert app.do("learning")["durations"]["in_use"] is False


def test_once_learned_the_switch_works_as_before(app: App) -> None:
    learned(app)
    assert app.do("learning")["durations"]["in_use"] is False
    assert app.do("learn_module", module="durations", use=True)["message"] == "Using learned durations"
    assert app.do("learning")["durations"]["in_use"] is True
