"""Pro tips (tests/features.toml: tips), the whole pipeline (24 Nov, the user: "go through every single functionality
of the app and build an extensive test suite"): a real `fridayd serve`, events made over HTTP the way a habit Friday
has a tip for would make them, and the tip the app asks for read back; then shown, as the app says it showed one. The
tests run in order on one server (a tip shown is shown for the rest of the day)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday, local

MEALS = "Friday plans your meals for you: no meal events needed."
WORK = "Add work as a to-do, and Friday finds the time for it."
NONE = {"id": None, "text": None, "page": None}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("tips"))
    yield server
    server.stop()


def event(friday: Friday, title: str, days: int) -> int:
    """An event of yours `days` from now at noon, an hour long."""
    noon = datetime.now(ZoneInfo(TZ)).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=days)
    made = friday.c("add", title=title, when="fixed", start=local(noon), end=local(noon + timedelta(hours=1)))
    return made["item"]["id"]


def test_1_a_new_friday_has_no_tip(friday: Friday) -> None:
    assert friday.q("tips") == NONE


MADE: dict[str, list[int]] = {}  # the meal events made, by title: events aren't to-dos, so `items` doesn't list them


def meal(friday: Friday, title: str, days: int) -> None:
    MADE.setdefault(title, []).append(event(friday, title, days))


def test_2_meal_events_bring_the_meals_tip_only_when_named_just_a_meal(friday: Friday) -> None:
    meal(friday, "Lunch", 1)
    meal(friday, "Lunch", 2)
    meal(friday, "Lunch with Sam", 3)  # a lunch with someone is an event of its own, not a meal Friday plans
    assert friday.q("tips") == NONE
    meal(friday, "dinner", 4)  # the third plain meal, in any case
    assert friday.q("tips") == {"id": "meal_events", "text": MEALS, "page": "/"}


def test_3_the_tip_goes_with_its_habit(friday: Friday) -> None:
    friday.c("drop", id=MADE["dinner"][0])
    assert friday.q("tips") == NONE
    meal(friday, "Breakfast", 5)
    assert friday.q("tips")["id"] == "meal_events"


def test_4_meals_far_off_dont_count(friday: Friday) -> None:
    for made in (*MADE.pop("Lunch"), *MADE.pop("Breakfast")):
        friday.c("drop", id=made)
    assert friday.q("tips") == NONE
    for days in (20, 21, 22):  # more than two weeks away
        meal(friday, "Lunch", days)
    assert friday.q("tips") == NONE
    for days in (1, 2, 3):
        meal(friday, "Lunch", days)
    assert friday.q("tips")["id"] == "meal_events"


def test_5_work_made_as_events_is_offered_first(friday: Friday) -> None:
    event(friday, "Study for prelim", 1)
    assert friday.q("tips")["id"] == "meal_events"  # one work event isn't a habit
    event(friday, "Study for chem final", 2)
    assert friday.q("tips") == {"id": "work_events", "text": WORK, "page": "/todo"}


def test_6_a_tip_friday_has_not_is_said_and_changes_nothing(friday: Friday) -> None:
    assert friday.c("tip_shown", id="no_such_tip")["message"] == "No such tip"
    assert friday.q("tips")["id"] == "work_events"
    answer = friday.http.post("/api/c/tip_shown", json={})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "id"]
    assert friday.q("tips")["id"] == "work_events"


def test_7_once_a_tip_is_shown_no_other_shows_that_day(friday: Friday) -> None:
    assert friday.c("tip_shown", id="work_events")["message"] == "Shown"
    assert friday.q("tips") == NONE  # the meals tip still holds, but one a day at most
    assert friday.c("tip_shown", id="work_events")["message"] == "Shown"  # shown twice the same day: no error
    assert friday.c("tip_shown", id="meal_events", closed=True)["message"] == "Shown"
    assert friday.q("tips") == NONE
