"""What you tick off in Friday going back to Apple Reminders (tests/features.toml: reminders), the whole pipeline: a
real `fridayd serve`, Reminders connected from Settings, the Mac app's side spoken over HTTP as RemindersBridge speaks
it: it sends the reminders (`reminders_sync`), asks what to make there (`reminder_writes`) and reports each
(`reminder_written`). A change made is never asked for again; one the Mac app couldn't make is asked again, then
given up and said on Reminders' box in Settings."""

from collections.abc import Iterator
from typing import Any

import pytest

from friday.integrations.sync import MAX_TRIES
from tests.system.test_beat_plan_system import Friday

HOME = {"id": "CAL-0001-HOME", "title": "Home"}


def reminder(rid: str, title: str) -> dict[str, Any]:
    """One reminder as RemindersPayload.reminder sends it."""
    return {"id": rid, "title": title, "notes": "", "list": HOME["title"], "list_id": HOME["id"], "completed": False}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("reminders"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def source(friday: Friday) -> int:
    """Reminders connected, its to-dos coming straight in, and three read from the Mac."""
    connected = friday.c("integration_connect", kind="reminders", token="")["source"]
    friday.c("integration_set", id=connected["id"], arrival="straight")
    sent = [reminder("r-1", "Call the dentist"), reminder("r-2", "Return library books"), reminder("r-3", "Pay rent")]
    friday.c("reminders_sync", reminders=sent, lists=[HOME])
    assert friday.until(lambda: {"Call the dentist", "Return library books", "Pay rent"} <= titles(friday))
    return connected["id"]


def titles(friday: Friday) -> set[str]:
    return {i["title"] for i in friday.q("items")}


def item(friday: Friday, title: str) -> dict[str, Any]:
    (found,) = [i for i in friday.q("items", status="all") if i["title"] == title]
    return found


def jobs(friday: Friday) -> list[dict[str, Any]]:
    return friday.q("reminder_writes")["jobs"]


def box(friday: Friday, source: int) -> dict[str, Any]:
    (found,) = [c for c in friday.q("integrations") if c["id"] == source]
    return found


def test_nothing_waits_for_the_mac_until_you_tick_one_off(friday: Friday, source: int) -> None:
    out = friday.q("reminder_writes")
    assert out["wanted"] is True and out["jobs"] == []


def test_made_in_reminders_it_is_never_asked_for_again(friday: Friday, source: int) -> None:
    friday.c("done", id=item(friday, "Call the dentist")["id"])
    (job,) = jobs(friday)
    assert (job["external_id"], job["op"]) == ("r-1", "done")
    assert friday.c("reminder_written", id=job["id"], ok=True)["message"] == "Made in Apple Reminders"
    assert jobs(friday) == []
    assert box(friday, source)["last_error"] is None
    assert item(friday, "Call the dentist")["status"] == "done"  # Friday's own tick stands


def test_opened_again_in_friday_it_is_opened_again_there(friday: Friday, source: int) -> None:
    friday.c("reopen", id=item(friday, "Call the dentist")["id"])
    (job,) = jobs(friday)
    assert (job["external_id"], job["op"]) == ("r-1", "reopen")
    friday.c("reminder_written", id=job["id"], ok=True)
    assert jobs(friday) == []


def test_one_the_mac_app_couldnt_make_is_asked_again_then_given_up_and_said(friday: Friday, source: int) -> None:
    friday.c("done", id=item(friday, "Return library books")["id"])
    (job,) = jobs(friday)
    for n in range(1, MAX_TRIES):
        said = friday.c("reminder_written", id=job["id"], ok=False, error="The reminder couldn't be saved")
        assert said["message"] == "Kept to try again"
        assert [j["id"] for j in jobs(friday)] == [job["id"]], f"not asked again after {n} tries"
        assert box(friday, source)["last_error"] is None  # not said until it's given up
    friday.c("reminder_written", id=job["id"], ok=False, error="The reminder couldn't be saved")
    assert jobs(friday) == []  # given up after MAX_TRIES, not asked forever
    said = box(friday, source)["last_error"]
    assert said == "Couldn't change a to-do in Apple Reminders: The reminder couldn't be saved"


def test_a_report_on_a_change_that_isnt_waiting_is_refused(friday: Friday, source: int) -> None:
    answer = friday.http.post("/api/c/reminder_written", json={"id": 999_999, "ok": True})
    assert answer.status_code == 422
    assert answer.json() == {"field": "id", "message": "id: no such change waits for an app on this Mac"}
    answer = friday.http.post("/api/c/reminder_written", json={"id": 1})
    assert answer.status_code == 422 and [e["loc"][-1] for e in answer.json()["detail"]] == ["ok"]


def test_reported_twice_the_second_report_changes_nothing(friday: Friday, source: int) -> None:
    friday.c("done", id=item(friday, "Pay rent")["id"])
    (job,) = jobs(friday)
    friday.c("reminder_written", id=job["id"], ok=True)
    friday.c("reminder_written", id=job["id"], ok=True)  # the Mac app retrying a report it thought lost
    assert jobs(friday) == []
