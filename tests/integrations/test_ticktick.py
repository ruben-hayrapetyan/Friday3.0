"""TickTick (C111), glass box against its stand-in: the Inbox and every open list, abandoned and completed tasks
left out, an all-day task due on its own day in its own time zone, a timed one at its moment, done sent to the task's
real list (the Inbox's own id), opened again set back to normal; a sign-in that has run out says to sign in again."""

import base64
import json

import httpx
import pytest

from friday.integrations import oauth, ticktick
from friday.integrations.base import ConnectorError
from tests.integrations.fake_ticktick import HARNESS, INBOX_ID, FakeTickTick


def connector(fake: FakeTickTick) -> ticktick.TickTick:
    return ticktick.TickTick(HARNESS.token, {}, fake.transport)


def test_the_inbox_and_open_lists_with_their_dues() -> None:
    fake = FakeTickTick("")
    fake.add("Call mom", "2026-10-23T17:00")
    fake.add("Report", "2026-10-22", project="p-work")
    fake.add("In a closed list", "2026-10-22", project="p-old")
    dropped = fake.add("Dropped", "2026-10-22")
    fake.tasks[dropped]["status"] = -1
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Call mom", "Report"}
    assert found["Call mom"].due == "2026-10-23T21:00+00:00"  # its moment: the sync puts it on your clock
    assert found["Report"].due == "2026-10-22"  # all day: its own day where it was set, not the UTC one
    assert found["Call mom"].external_id.startswith(f"{INBOX_ID}/") and found["Report"].notes == "In TickTick: Work"


def test_done_goes_to_the_tasks_real_list_and_reopen_sets_it_back() -> None:
    fake = FakeTickTick("")
    task = fake.add("Call mom", "2026-10-23")
    connector(fake).write(f"{INBOX_ID}/{task}", "done")
    assert fake.tasks[task]["status"] == 2
    connector(fake).write(f"{INBOX_ID}/{task}", "reopen")
    assert fake.tasks[task]["status"] == 0
    assert fake.writes() == [f"POST /project/{INBOX_ID}/task/{task}/complete", f"POST /task/{task}"]


def test_a_sign_in_that_ran_out_says_to_sign_in_again() -> None:
    old = json.dumps({"access_token": "tt-old", "expires_at": 1})
    with pytest.raises(ConnectorError, match="ran out: press Sign in again"):
        ticktick.TickTick(old, {}, FakeTickTick("").transport).read()


def test_the_sign_in_asks_with_fridays_secret_by_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_TICKTICK_CLIENT_ID", "tt-friday")
    monkeypatch.setenv("FRIDAY_TICKTICK_CLIENT_SECRET", "tt-secret")
    assert ticktick.PROVIDER.ready() and not ticktick.PROVIDER.secret_in_body
    assert ticktick.PROVIDER.scopes == ("tasks:read", "tasks:write")


def test_an_all_day_task_in_a_time_zone_python_doesnt_know_is_on_its_utc_day() -> None:
    task = {"dueDate": "2026-11-20T05:00:00.000+0000", "isAllDay": True, "timeZone": "Mars/Olympus_Mons"}
    assert ticktick.due_of(task) == "2026-11-20"
    assert ticktick.due_of(task | {"timeZone": "America/Los_Angeles"}) == "2026-11-19"  # its own day where it was set


def test_the_sign_in_trades_its_code_with_fridays_secret_by_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_TICKTICK_CLIENT_ID", "tt-friday")
    monkeypatch.setenv("FRIDAY_TICKTICK_CLIENT_SECRET", "tt-secret")
    asked: list[httpx.Request] = []

    def token_endpoint(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, json={"access_token": "tt-access-2", "token_type": "bearer", "expires_in": 3600})

    monkeypatch.setitem(oauth.TRANSPORTS, "ticktick", httpx.MockTransport(token_endpoint))
    tokens = oauth.trade(ticktick.PROVIDER, {"grant_type": "authorization_code", "code": "c"}, now=1000.0)
    assert tokens == {"access_token": "tt-access-2", "expires_at": 4600.0}
    (request,) = asked
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"tt-friday:tt-secret").decode()
    assert "tt-secret" not in request.content.decode()  # not in the body as well
