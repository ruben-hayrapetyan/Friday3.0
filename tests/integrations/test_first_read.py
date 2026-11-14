"""Whether an integration is being read for the first time (13 Nov: connecting one and its first read is slow, so its
box shows a small spinner until the read is in), black box through the commands the box reads."""

from pathlib import Path

import pytest

from friday.integrations import sync
from friday.planner.store import load_settings
from tests.commands.helpers import new_app
from tests.integrations.contract import THU, World
from tests.integrations.fake_mac_reminders import HARNESS as REMINDERS
from tests.integrations.fake_todoist import HARNESS as TODOIST


@pytest.fixture
def todoist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = TODOIST.fake(TODOIST.token)
    monkeypatch.setitem(sync.TRANSPORTS, "todoist", fake.transport)
    return World(TODOIST, new_app(tmp_path), fake)


def box(w: World) -> dict:
    (found,) = [c for c in w.app.do("integrations") if c["id"] == w.source_id]
    return found


def test_connected_it_is_being_read_until_its_first_read_is_in(todoist: World) -> None:
    todoist.h.add(todoist.fake, "Read chapter 4", THU)
    out = todoist.app.do("integration_connect", kind="todoist", token=TODOIST.token)
    todoist.source_id = out["source"]["id"]
    assert out["source"]["reading"] is True and box(todoist)["reading"] is True
    todoist.sync()
    assert box(todoist)["reading"] is False and box(todoist)["waiting"] == 1  # the first read, in the Inbox
    todoist.sync()
    assert box(todoist)["reading"] is False  # once, not at every read


def test_a_first_read_that_fails_stops_the_spinner_and_says_why(todoist: World) -> None:
    todoist.connect()
    todoist.fake.fail_next(503)
    todoist.sync()
    assert box(todoist)["reading"] is False and "503" in box(todoist)["last_error"]
    todoist.sync()  # then read: still not being read for the first time
    assert box(todoist)["reading"] is False and box(todoist)["last_error"] is None


def test_reminders_is_being_read_until_the_mac_app_has_sent_them_or_macos_said_no(tmp_path: Path) -> None:
    w = World(REMINDERS, new_app(tmp_path), REMINDERS.fake(""))
    w.connect()
    sync.sync_all(w.app.conn, load_settings(w.app.conn), w.app.now_utc, asked=True)
    assert box(w)["reading"] is True, "the Mac app hasn't sent them: still waiting for the first"
    w.app.do("reminders_sync", denied=True)
    assert box(w)["reading"] is False
    w.app.do("reminders_sync", reminders=[])
    w.sync()
    assert box(w)["reading"] is False and box(w)["last_error"] is None
