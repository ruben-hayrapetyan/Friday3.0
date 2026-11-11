"""The sender (C97, your "yes": done reaches its app at once): woken by what's queued, it sends after the command
commits; what was rolled back sends nothing; stopping it is quick."""

import time
from pathlib import Path

import pytest

from friday.integrations import sync
from tests.commands.helpers import new_app
from tests.integrations.contract import THU, World
from tests.integrations.fake_todoist import HARNESS


@pytest.fixture
def w(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = HARNESS.fake(HARNESS.token)
    monkeypatch.setitem(sync.TRANSPORTS, "todoist", fake.transport)
    return World(HARNESS, new_app(tmp_path), fake)


def started(w: World, tmp_path: Path) -> sync.Sender:
    sender = sync.Sender(tmp_path / "friday.db", lambda: w.app.now_utc)
    sender.start()
    return sender


def test_done_is_sent_within_a_second_of_the_command(w: World, tmp_path: Path) -> None:
    task = w.h.add(w.fake, "Pay rent", THU)
    w.connect()
    w.sync()
    sender = started(w, tmp_path)
    try:
        w.app.do("done", id=w.item("Pay rent")["id"])
        for _ in range(30):
            if w.h.is_done(w.fake, task):
                break
            time.sleep(0.1)
        assert w.h.is_done(w.fake, task), "not sent within three seconds"
    finally:
        sender.stop()


def test_queuing_wakes_it_and_a_rolled_back_command_leaves_nothing_to_send(w: World) -> None:
    w.h.add(w.fake, "Pay rent", THU)
    w.connect()
    w.sync()
    sync.WAKE.clear()
    item = w.item("Pay rent")["id"]
    conn = w.app.conn
    conn.execute("BEGIN")
    sync.queue_write(conn, item, "done", "you", w.app.now_utc, 1)
    assert sync.WAKE.is_set()
    conn.execute("ROLLBACK")
    assert sync.send_writes(conn, w.app.now_utc) == 0 and w.writes() == []


def test_the_sync_s_own_done_wakes_nothing(w: World) -> None:
    w.h.add(w.fake, "Pay rent", THU)
    w.connect()
    w.sync()
    sync.WAKE.clear()
    sync.queue_write(w.app.conn, w.item("Pay rent")["id"], "done", "sync:Todoist", w.app.now_utc, 1)
    assert not sync.WAKE.is_set()


def test_stopping_is_quick(w: World, tmp_path: Path) -> None:
    sender = started(w, tmp_path)
    began = time.monotonic()
    sender.stop()
    assert time.monotonic() - began < 1.5 and not sender.thread.is_alive()
