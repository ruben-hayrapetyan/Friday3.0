"""The sender (C97, your "yes": done reaches its app at once): woken by what's queued, it sends after the command
commits; what was rolled back sends nothing; stopping it is quick; a change the app keeps refusing is tried again,
then said on its box; a send that breaks doesn't stop it. And when each integration is read."""

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from friday.core.db import connect
from friday.core.time import format_utc
from friday.integrations import sync
from friday.integrations.base import ConnectorError
from friday.integrations.todoist import Todoist
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


def test_a_change_the_app_keeps_refusing_is_tried_again_then_said_on_its_box(w: World) -> None:
    w.h.add(w.fake, "Pay rent", THU)
    source = w.connect()
    w.sync()
    w.app.do("done", id=w.item("Pay rent")["id"])

    def refusing(s: dict[str, Any]) -> Any:
        class Refuses:
            def write(self, external_id: str, op: str) -> None:
                raise ConnectorError("down", "Todoist is having trouble (503): Friday tries again")

        return Refuses()

    for n in range(sync.MAX_TRIES):
        assert sync.send_writes(w.app.conn, w.app.now_utc, make=refusing) == 0
        said = w.source()["last_error"] if w.source() else None
        assert (said is None) == (n < sync.MAX_TRIES - 1), f"said after {n + 1} tries: {said}"
    assert said == "Couldn't mark it done in Todoist: Todoist is having trouble (503): Friday tries again"
    (write,) = w.app.table("source_writes")
    assert write["tries"] == sync.MAX_TRIES and write["done_utc"] is None and write["source_id"] == source
    assert sync.send_writes(w.app.conn, w.app.now_utc, make=refusing) == 0  # given up: not tried forever


def test_a_send_that_breaks_doesnt_stop_the_sender(
    w: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    tries: list[int] = []

    def breaks(conn: Any, now_utc: int) -> int:
        tries.append(now_utc)
        raise RuntimeError("a bug in one connector")

    monkeypatch.setattr(sync, "send_writes", breaks)
    sender = started(w, tmp_path)
    try:
        for wanted in (1, 2):  # woken twice: the second send happens though the first broke
            sync.WAKE.set()
            for _ in range(30):
                if len(tries) == wanted:
                    break
                time.sleep(0.1)
            assert len(tries) == wanted and sender.thread.is_alive(), tries
        assert "sending to integrations" in caplog.text
    finally:
        sender.stop()


def test_an_integration_is_read_when_asked_new_or_ten_minutes_on() -> None:
    last = {"last_sync_utc": format_utc(1000)}
    assert sync.due_now({"last_sync_utc": None}, 1000, asked=False)
    assert sync.due_now(last, 1001, asked=True)
    assert not sync.due_now(last, 1000 + sync.POLL_MIN - 1, asked=False)
    assert sync.due_now(last, 1000 + sync.POLL_MIN, asked=False)


def test_the_sender_and_the_job_never_send_the_same_change_twice_or_out_of_order(w: World, tmp_path: Path) -> None:
    # The sender and the integrations job's minute each send what waits, on connections of their own: one still
    # sending a done when the other started sent it again, after the reopen made meanwhile, so the task ended done
    # there while open here
    w.h.add(w.fake, "Pay rent", THU)
    w.connect()
    w.sync()
    mine = w.item("Pay rent")["id"]
    w.app.do("done", id=mine)
    sent: list[str] = []
    entered, go = threading.Event(), threading.Event()

    class Slow:
        def write(self, external_id: str, op: str) -> None:
            if not entered.is_set():
                entered.set()
                go.wait(5)
            sent.append(op)

    first = threading.Thread(target=sync.send_writes, args=(w.app.conn, w.app.now_utc, lambda s: Slow()))
    first.start()
    assert entered.wait(5)
    w.app.do("reopen", id=mine)
    other = connect(tmp_path / "friday.db")
    second = threading.Thread(target=sync.send_writes, args=(other, w.app.now_utc, lambda s: Slow()))
    second.start()
    second.join(0.5)
    go.set()
    first.join(5)
    second.join(5)
    other.close()
    assert sent == ["done", "reopen"]


def test_a_choice_made_while_the_first_read_runs_is_kept(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    # The first read marks the integration read by writing its whole config back as it was when the read began: a
    # choice made in its box meanwhile (how new to-dos arrive, which lists), just after connecting, was undone
    w.h.add(w.fake, "Pay rent", THU)
    source = w.connect()
    reading = Todoist.read

    def read(self: Todoist) -> Any:
        w.app.do("integration_set", id=source, arrival="inbox")  # in its box, while Todoist answers
        return reading(self)

    monkeypatch.setattr(Todoist, "read", read)
    w.sync()
    config = json.loads(w.source()["config"])  # type: ignore[index]
    assert config["synced"] is True and config["arrival"] == "inbox"
