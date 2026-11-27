"""An event on two calendars (27 Nov, a user's notes, "Friday Notes-3": two "Holidays in United States" calendars,
Google's hidden and another shown; no Thanksgiving, until the two were switched round, and then it wore the hidden
Google calendar's green). Friday keeps the event once, by the first calendar that brought it; it's on both: hidden only
when every calendar it's on is, and shown as one that shows."""

from pathlib import Path

import pytest

from friday.planner.hidden import hidden_of
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import calendar, post

GOOGLE = calendar("hol-google", "Holidays in United States (Google)", color="#0b8043")  # its own green
OTHER = calendar("hol-other", "Holidays in United States (sw249)", color="#039be5")


def thanksgiving(cid: str) -> dict:
    return {"id": f"tg-{cid}", "calendar": cid, "title": "Thanksgiving", "start": "2026-10-22", "end": "2026-10-23",
            "all_day": True}  # fmt: skip


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gcal", value={"include_all_day": True})
    post(app, [GOOGLE, OTHER], [])
    for c in (GOOGLE, OTHER):
        app.do("calendar_set", id=c["id"], mac=True, on=True, trusted=True)
    post(app, [GOOGLE, OTHER], [thanksgiving("hol-google"), thanksgiving("hol-other")], minutes_later=1)
    return app


def hide(app: App, *names: str) -> None:
    look = load_settings(app.conn)["calendar_look"].model_dump()
    app.do("settings_set", key="calendar_look", value=look | {"toolbar": list(names)})


def thanksgivings(app: App) -> list[dict]:
    return [i for i in app.table("items") if i["title"] == "Thanksgiving" and i["status"] == "todo"]


def seen(app: App) -> tuple[bool, str | None]:
    """Whether it's hidden, and the calendar it's shown as."""
    [event] = thanksgivings(app)
    hidden = hidden_of(app.conn, load_settings(app.conn), 1)
    return event["id"] in hidden.events, app.do("item", id=event["id"])["item"]["calendar"]


def test_it_is_kept_once_on_both(app: App) -> None:
    assert len(thanksgivings(app)) == 1


def test_one_hidden_the_other_shown_it_shows_as_the_shown_one(app: App) -> None:
    first = seen(app)[1]  # the calendar that brought it first
    other = OTHER["name"] if first == GOOGLE["name"] else GOOGLE["name"]
    hide(app, first)
    assert seen(app) == (False, other)


def test_the_other_hidden_it_shows_as_its_own(app: App) -> None:
    first = seen(app)[1]
    other = OTHER["name"] if first == GOOGLE["name"] else GOOGLE["name"]
    hide(app, other)
    assert seen(app) == (False, first)


def test_both_hidden_it_is_hidden(app: App) -> None:
    hide(app, GOOGLE["name"], OTHER["name"])
    assert seen(app)[0] is True


def test_both_shown_it_shows_as_its_own(app: App) -> None:
    first = seen(app)[1]
    hide(app)
    assert seen(app) == (False, first)


def test_shown_through_the_other_it_wears_that_ones_color_not_the_hidden_ones(app: App) -> None:
    [event] = thanksgivings(app)
    color = lambda: app.do("item", id=event["id"])["item"]["calendar_color"]  # noqa: E731
    own = color()  # nothing hidden: its own calendar's
    hide(app, seen(app)[1])
    through_other = color()
    assert own and through_other and own != through_other  # the two calendars' greens and blues


def test_an_event_on_one_hidden_calendar_alone_is_hidden(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="gcal", value={"include_all_day": True})
    post(app, [GOOGLE], [])
    app.do("calendar_set", id=GOOGLE["id"], mac=True, on=True, trusted=True)
    post(app, [GOOGLE], [thanksgiving("hol-google")], minutes_later=1)
    hide(app, GOOGLE["name"])
    assert seen(app)[0] is True
