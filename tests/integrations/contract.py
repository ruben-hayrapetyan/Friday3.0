"""The contract every integration keeps (C96, written from what any of them must do, not from how one works): each
check drives Friday through its commands and an integration's fake, and fails with what went wrong. The same checks
run against every integration (test_contract.py) and against connectors broken on purpose
(test_contract_catches.py), so a check that can't catch its bug fails too."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from friday.core.items import FieldError
from friday.integrations import sync
from friday.planner.store import load_settings
from tests.commands.helpers import App
from tests.integrations.kit import FakeService, Harness

MON = "2026-10-19"  # new_app's Monday, 09:00 in New York
THU, FRI_5PM = "2026-10-22", "2026-10-23T17:00"


@dataclass
class World:
    h: Harness
    app: App
    fake: FakeService
    source_id: int | None = None
    errors: list[str] = field(default_factory=list)

    def connect(self, arrival: str = "straight", token: str | None = None) -> int:
        out = self.app.do("integration_connect", kind=self.h.kind, token=token or self.h.token, fields=self.h.fields)
        self.source_id = int(out["source"]["id"])
        if arrival != "inbox_first":
            self.app.do("integration_set", id=self.source_id, arrival=arrival)
        return self.source_id

    def sync(self) -> int:
        if hasattr(self.fake, "push"):  # the Mac app sends what it reads first (Apple Reminders)
            self.fake.push(self.app)
        made = sync.sync_all(self.app.conn, load_settings(self.app.conn), self.app.now_utc, asked=True)
        if (s := self.source()) and s["last_error"]:
            self.errors.append(s["last_error"])
        return made

    def send(self) -> int:
        sent = sync.send_writes(self.app.conn, self.app.now_utc)
        if hasattr(self.fake, "deliver"):  # the Mac app does what waits for it
            sent += self.fake.deliver(self.app)
        return sent

    def source(self) -> dict[str, Any] | None:
        found = [s for s in self.app.table("sources") if s["id"] == self.source_id]
        return found[0] if found else None

    def items(self, status: str = "todo") -> list[dict[str, Any]]:
        return [i for i in self.app.table("items") if i["status"] == status]

    def item(self, title: str) -> dict[str, Any]:
        found = [i for i in self.app.do("items") if i["title"] == title]
        assert len(found) == 1, f"{title!r} is in Friday {len(found)} times"
        return found[0]

    def writes(self) -> list[str]:
        return self.fake.writes()


# Connecting


def check_a_good_token_connects_and_a_bad_one_is_refused_in_words(w: World) -> None:
    if w.h.on_mac:
        pytest.skip("no token: macOS asks instead")
    with pytest.raises(FieldError) as refused:
        w.connect(token="not-the-token")
    assert "token" in str(refused.value).lower(), refused.value
    assert w.h.token not in str(refused.value)
    assert not [s for s in w.app.table("sources") if s["kind"] == w.h.kind], "a refused token left a source"
    w.connect()
    assert w.source() and w.source()["enabled"] == 1


# Coming in


def check_each_to_do_comes_in_once_with_its_title_due_and_length(w: World) -> None:
    w.h.add(w.fake, "Write the report", THU, 90)
    w.h.add(w.fake, "Call the landlord", FRI_5PM)
    w.h.add(w.fake, "Someday: learn Rust")
    w.connect()
    w.sync()
    report, call = w.item("Write the report"), w.item("Call the landlord")
    assert report["due"].startswith(THU), report["due"]
    assert call["due"] == (FRI_5PM if w.h.times else f"{FRI_5PM[:10]}T23:59"), call["due"]
    w.item("Someday: learn Rust")
    if w.h.lengths:
        assert report["duration_min"] == 90, report["duration_min"]


def check_a_plain_title_comes_in_as_the_integration_s_kind_and_a_school_one_as_itself(w: World) -> None:
    """C97: "Book dentist" from a to-do app is a Task (from a tracker a Work task), not a 2-hour Assignment; a title
    that says what it is keeps that."""
    w.h.add(w.fake, "Book dentist", THU)
    w.h.add(w.fake, "Study guide for prelim 2", THU)
    w.connect()
    w.sync()
    kind = sync.CONNECTORS[w.h.kind].caps.kind
    assert w.item("Book dentist")["preset"] == kind, w.item("Book dentist")["preset"]
    assert w.item("Study guide for prelim 2")["preset"] == "Exam prep"


def check_reading_again_with_nothing_changed_makes_nothing_and_sends_nothing(w: World) -> None:
    for n in range(5):
        w.h.add(w.fake, f"Task {n}", THU)
    w.connect()
    w.sync()
    before = len(w.items())
    assert w.sync() == 0
    assert w.sync() == 0
    assert len(w.items()) == before == 5, f"{before} then {len(w.items())}: duplicated on reading again"
    assert w.writes() == [], f"reading sent changes: {w.writes()}"


def check_a_change_there_changes_only_what_the_service_owns(w: World) -> None:
    task = w.h.add(w.fake, "Draft", THU, 60)
    w.connect()
    w.sync()
    mine = w.item("Draft")
    w.app.do("edit", id=mine["id"], duration_min=150)  # yours: the length
    w.h.move(w.fake, task, "2026-10-24")
    w.h.rename(w.fake, task, "Draft v2")
    w.sync()
    now = w.item("Draft v2")
    assert now["id"] == mine["id"], "a change there made a new item"
    assert now["due"].startswith("2026-10-24"), now["due"]
    assert now["duration_min"] == 150, f"your length became {now['duration_min']}"


def check_done_there_is_done_here_and_nothing_echoes_back(w: World) -> None:
    task = w.h.add(w.fake, "Pay rent", THU)
    w.connect()
    w.sync()
    w.h.finish(w.fake, task)
    w.sync()
    assert "Pay rent" in [i["title"] for i in w.items("done")], "done there, still open here"
    w.send()
    assert w.writes() == [], f"Friday sent back what came from there: {w.writes()}"


# Going back


def check_done_here_goes_back_exactly_once_and_reopen_too(w: World) -> None:
    if not w.h.two_way:
        pytest.skip("read only")
    task = w.h.add(w.fake, "Send invoice", THU)
    w.connect()
    w.sync()
    mine = w.item("Send invoice")
    w.app.do("done", id=mine["id"])
    w.send()
    w.send()
    assert w.h.is_done(w.fake, task), "done here, still open there"
    assert len(w.writes()) == 1, f"sent {w.writes()}"
    w.sync()  # it's done there now: nothing changes back
    w.app.do("reopen", id=mine["id"])
    w.send()
    assert not w.h.is_done(w.fake, task), "opened again here, still done there"
    assert len(w.writes()) == 2, f"sent {w.writes()}"


def check_a_failed_send_is_kept_and_sent_later_once(w: World) -> None:
    if not w.h.two_way:
        pytest.skip("read only")
    task = w.h.add(w.fake, "Book flights", THU)
    w.connect()
    w.sync()
    w.app.do("done", id=w.item("Book flights")["id"])
    w.fake.fail_next(503)
    w.send()
    assert not w.h.is_done(w.fake, task)
    w.send()
    assert w.h.is_done(w.fake, task), "a failed send was lost"
    assert w.send() == 0


# Going wrong


@pytest.mark.parametrize("failure", ["token", "rate", "down", "timeout"])
def check_a_failure_is_said_in_words_and_loses_nothing(w: World, failure: str) -> None:
    if w.h.on_mac:
        pytest.skip("nothing over the internet")
    for n in range(3):
        w.h.add(w.fake, f"Task {n}", THU)
    w.connect()
    w.sync()
    if failure == "timeout":
        w.fake.time_out_next()
    else:
        w.fake.fail_next({"token": 401, "rate": 429, "down": 500}[failure], headers={"retry-after": "30"})
    w.sync()
    said = (w.source() or {})["last_error"] or ""
    words = {"token": "token", "rate": "slow down", "down": "again", "timeout": "in time"}[failure]
    assert words in said.lower(), f"{failure}: said {said!r}"
    assert len(w.items()) == 3, "a failed read lost to-dos"
    w.sync()
    assert not (w.source() or {})["last_error"], "the error stayed after a good read"


def check_the_token_is_never_kept_outside_its_secret(w: World) -> None:
    if w.h.on_mac:
        pytest.skip("no token")
    w.h.add(w.fake, "Task", THU)
    w.connect()
    w.sync()
    for status in (401, 429, 500):
        w.fake.fail_next(status)
        w.sync()
    w.app.do("done", id=w.item("Task")["id"])
    w.fake.fail_next(500)
    w.send()
    dump = "\n".join(w.app.conn.iterdump())
    assert w.h.token not in dump, "the token is in the database"
    assert all(w.h.token not in e for e in w.errors), "the token is in an error"


def check_requests_go_only_to_the_service(w: World) -> None:
    if w.h.on_mac:
        assert w.fake.requests == [], "the Mac's Reminders went over the internet"
        return
    w.h.add(w.fake, "Task", THU)
    w.connect()
    w.sync()
    w.app.do("done", id=w.item("Task")["id"])
    w.send()
    hosts = {r.url.host for r in w.fake.requests}
    assert hosts == {w.fake.host}, f"requests went to {hosts}"
    assert all(r.url.scheme == "https" for r in w.fake.requests), "a request wasn't https"


def check_a_thousand_to_dos_come_in_once_and_in_time(w: World) -> None:
    for n in range(1000):
        w.h.add(w.fake, f"Task {n:04}", "2026-11-20")
    w.connect()
    began = time.perf_counter()
    w.sync()
    took = time.perf_counter() - began
    assert len(w.items()) == 1000, len(w.items())
    assert took < 60, f"the first read took {took:.0f}s"


# Arrival and disconnecting


def check_the_first_read_waits_in_the_inbox_then_new_ones_come_straight_in(w: World) -> None:
    w.h.add(w.fake, "First one", THU)
    w.h.add(w.fake, "Second one", THU)
    w.connect(arrival="inbox_first")
    w.sync()
    assert w.items() == [], "the first read went straight in"
    batch = {s["batch"] for s in w.app.table("suggestions") if s["status"] == "pending"}
    assert len(batch) == 1 and None not in batch, f"not one batch to review together: {batch}"
    w.app.do("batch_accept", batch=batch.pop())
    assert len(w.items()) == 2
    w.h.add(w.fake, "Third one", THU)
    w.sync()
    w.item("Third one")  # straight in


def check_inbox_always_means_every_new_one_waits(w: World) -> None:
    w.h.add(w.fake, "One", THU)
    w.connect(arrival="inbox")
    w.sync()
    assert w.items() == []
    w.app.do("batch_accept", batch=next(s["batch"] for s in w.app.table("suggestions") if s["status"] == "pending"))
    w.h.add(w.fake, "Two", THU)
    w.sync()
    assert [i["title"] for i in w.items()] == ["One"], "a new one went straight in"


@pytest.mark.parametrize("keep", [True, False])
def check_disconnecting_keeps_or_drops_what_it_brought_and_forgets_the_token(w: World, keep: bool) -> None:
    w.h.add(w.fake, "Kept or not", THU)
    source_id = w.connect()
    w.sync()
    assert w.h.on_mac or sync.token_of(source_id), "the token wasn't kept"
    w.app.do("integration_disconnect", id=source_id, keep=keep)
    assert not sync.token_of(source_id), "the token outlived the connection"
    titles = [i["title"] for i in w.items()]
    assert ("Kept or not" in titles) == keep, f"keep={keep}: {titles}"
    asked = len(w.fake.requests)
    w.sync()
    assert len(w.fake.requests) == asked, "a disconnected integration was still read"


def check_until_the_mac_app_is_heard_from_nothing_is_taken_as_done(w: World) -> None:
    """A Mac-fed integration (Apple Reminders) not yet read: no to-do it brought in is marked done for missing."""
    if not w.h.on_mac:
        pytest.skip("fetched, not fed by the Mac app")
    w.h.add(w.fake, "Water the plants", THU)
    w.connect()
    w.sync()
    assert [i["title"] for i in w.items()] == ["Water the plants"]
    w.app.conn.execute("DELETE FROM kv WHERE key = 'mac_reminders'")  # as before the app's first reading
    sync.sync_all(w.app.conn, load_settings(w.app.conn), w.app.now_utc, asked=True)
    assert [i["title"] for i in w.items()] == ["Water the plants"], "done for want of a reading"


CHECKS = {name: fn for name, fn in dict(globals()).items() if name.startswith("check_")}


def run_check(name: str, w: World, **params: Any) -> None:
    CHECKS[name](w, **params)


__all__ = ["CHECKS", "World", "json", "run_check"]
