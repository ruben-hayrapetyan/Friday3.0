"""Connecting Google through the whole of Friday (tests/features.toml: connecting; 24 Nov, the user: "build an extensive
test suite"): a real `fridayd serve`, each command of Settings → Calendars sent over HTTP as the page sends it, and
`google_connect_status` read back after each. Never Google itself: the server can name no address but this machine's
(OFFLINE below: a sync with a made-up token would otherwise ask Google for its calendars), Google Tasks is a
stand-in on this machine (FRIDAY_API_GOOGLE_TASKS), and
an account "signed in" is a made-up token written into the test's own data folder. Signing in itself (Google's page
in a browser) isn't sent: it would open one."""

import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integrations.fake_google_tasks import ACCOUNT, HARNESS, FakeGoogleTasks
from tests.integrations.kit import serve
from tests.system.test_beat_plan_system import Friday

CALENDAR = "https://www.googleapis.com/auth/calendar.readonly"
EVENTS = "https://www.googleapis.com/auth/calendar.events"
TASKS = "https://www.googleapis.com/auth/tasks"
# An OAuth client JSON of the shape Google Cloud downloads for a Desktop app: made up, not anyone's.
DESKTOP = {"installed": {"client_id": "123-made-up.apps.googleusercontent.com", "client_secret": "made-up",
                         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                         "token_uri": "https://oauth2.googleapis.com/token"}}  # fmt: skip


# Loaded by the server's Python at its start (PYTHONPATH): any address but this machine's isn't found, as offline.
OFFLINE = """
import socket

_found = socket.getaddrinfo


def _here_only(host, *args, **kwargs):
    if host not in ("127.0.0.1", "localhost", "::1", None):
        raise socket.gaierror(socket.EAI_NONAME, f"offline for the test: {host}")
    return _found(host, *args, **kwargs)


socket.getaddrinfo = _here_only
"""


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, FakeGoogleTasks]]:
    fake = FakeGoogleTasks(HARNESS.token)
    fake.add("Buy milk", "2026-12-02", in_list="MDI")
    address, stop = serve(fake)
    shim = tmp_path_factory.mktemp("offline")
    (shim / "sitecustomize.py").write_text(OFFLINE)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_API_GOOGLE_TASKS", f"{address}/tasks/v1")
        env.setenv("PYTHONPATH", str(shim))
        friday = Friday(tmp_path_factory.mktemp("connecting_pipeline"))
    yield friday, fake
    friday.stop()
    stop()


@pytest.fixture
def friday(world: tuple[Friday, FakeGoogleTasks]) -> Friday:
    return world[0]


def status(friday: Friday) -> dict:
    return friday.q("google_connect_status")


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def client_path(friday: Friday) -> Path:
    return friday.folder / "config" / "google_client.json"  # beside friday.toml (FRIDAY_CONFIG)


def secrets(friday: Friday) -> Path:
    return friday.folder / "data" / "secrets.json"  # the test's own data folder, beside its friday.db


def sign_in(friday: Friday, account: str, scopes: list[str], expiry: str = "2099-01-01T00:00:00Z") -> None:
    """An account as a finished sign-in leaves it: a made-up token, good until `expiry` (so it isn't renewed), kept
    where Friday keeps them."""
    path = secrets(friday)
    found = json.loads(path.read_text()) if path.exists() else {}
    found.setdefault("google_accounts", {})[account] = {
        "token": HARNESS.token, "refresh_token": "made-up-refresh", "client_id": "made-up", "client_secret": "made-up",
        "token_uri": "https://oauth2.googleapis.com/token", "scopes": scopes, "expiry": expiry}  # fmt: skip
    path.write_text(json.dumps(found))
    os.chmod(path, 0o600)


def test_the_server_cant_reach_anything_but_this_machine(friday: Friday) -> None:
    """The guard itself: without it, the tests below would send made-up tokens to Google."""
    assert friday.q("status")  # this machine: reached
    probe = "import socket; socket.getaddrinfo('www.googleapis.com', 443)"
    run = subprocess.run([sys.executable, "-c", probe], env=friday.env, capture_output=True, text=True, timeout=60)
    assert run.returncode != 0 and "offline for the test: www.googleapis.com" in run.stderr


def test_nothing_connected_yet(friday: Friday) -> None:
    out = status(friday)
    assert out["state"] == "idle" and out["accounts"] == []
    assert (out["calendar"], out["gmail"], out["events"]) == (False, False, False)
    assert out["url"] is None and out["message"] is None


def test_cancel_with_no_sign_in_waiting_changes_nothing(friday: Friday) -> None:
    out = friday.c("google_connect_cancel")
    assert out["state"] == "idle" and out["message"] is None and out["url"] is None and out["accounts"] == []
    assert friday.c("google_connect_cancel") == out  # again: the same
    assert status(friday) == out


def test_a_key_file_that_isnt_googles_is_said_and_nothing_is_kept(friday: Friday) -> None:
    before = status(friday)["client_file"]
    cases = [
        ("{not json", "that isn't Google's key file"),
        (json.dumps(["installed"]), "that isn't Google's key file"),
        (json.dumps({"installed": {"client_id": "x"}}), "that isn't Google's key file"),
        (json.dumps({"installed": {**DESKTOP["installed"], "client_secret": 7}}), "that isn't Google's key file"),
        (json.dumps({"web": DESKTOP["installed"]}), "that key is for a website"),
        ("x" * 64_001, "too big to be Google's key file"),
    ]
    for content, said in cases:
        out = refused(friday, "google_client_save", content=content)
        assert out["field"] == "file" and said in out["message"], (content[:40], out)
    assert not client_path(friday).exists()
    assert status(friday)["client_file"] == before
    assert refused(friday, "google_client_save")  # no content at all


def test_a_desktop_apps_key_file_is_kept_privately_where_connect_looks(friday: Friday) -> None:
    out = friday.c("google_client_save", content=json.dumps(DESKTOP))
    assert out["client_file"] is True and status(friday)["client_file"] is True
    kept = client_path(friday)
    assert kept.exists() and stat.S_IMODE(kept.stat().st_mode) == 0o600  # only you can read it
    first = kept.stat().st_size
    friday.c("google_client_save", content=json.dumps(DESKTOP, indent=2))  # saved again: replaced, not added to
    assert kept.stat().st_size == len(json.dumps(DESKTOP))  # kept as JSON Friday wrote, whatever its spacing
    assert first == kept.stat().st_size
    refused(friday, "google_client_save", content="{broken")  # a bad one after a good one leaves the good one
    assert kept.stat().st_size == first


def test_removing_an_account_thats_not_connected_is_said(friday: Friday) -> None:
    out = refused(friday, "google_remove", account="nobody@gmail.com")
    assert out["field"] == "account" and out["message"] == "account: nobody@gmail.com isn't connected"
    assert refused(friday, "google_remove", account="")["message"] == "account: that account isn't connected"
    assert refused(friday, "google_remove")  # no account given


def test_a_signed_in_account_shows_with_what_it_allowed(friday: Friday) -> None:
    sign_in(friday, ACCOUNT, [CALENDAR, EVENTS, TASKS])
    out = status(friday)
    assert [(a["email"], a["events"], a["gmail"], a["tasks"]) for a in out["accounts"]] == [
        (ACCOUNT, True, False, True)]  # fmt: skip
    assert (out["calendar"], out["events"], out["gmail"]) == (True, True, False)


def test_tasks_cant_be_read_from_an_account_not_signed_in_or_none(friday: Friday) -> None:
    out = refused(friday, "google_tasks_connect", account="someone@else.com")
    assert out["field"] == "account" and "isn't signed in to Google any more" in out["message"]
    assert "Sign in with Google first" in refused(friday, "google_tasks_connect", account="")["message"]
    assert not [s for s in friday.q("integrations") if s["kind"] == "google_tasks"]


def test_tasks_cant_be_read_from_an_account_that_didnt_allow_them(friday: Friday) -> None:
    sign_in(friday, "noTasks@gmail.com", [CALENDAR, EVENTS])
    out = refused(friday, "google_tasks_connect", account="noTasks@gmail.com")
    assert "hasn't allowed Google Tasks" in out["message"]
    friday.c("google_remove", account="noTasks@gmail.com")


def test_google_tasks_connects_from_an_account_that_allowed_them_and_its_tasks_come_in(world) -> None:  # noqa: ANN001
    friday, fake = world
    out = friday.c("google_tasks_connect", account=ACCOUNT)
    assert out["message"].startswith(f"Google Tasks connected ({ACCOUNT}): its tasks come to your Inbox")
    assert out["source"]["kind"] == "google_tasks"
    assert any(r.url.path.endswith("/users/@me/lists") for r in fake.requests)  # checked against Google Tasks
    friday.c("sync_now")
    assert friday.until(lambda: any(s["input"].get("title") == "Buy milk" for s in friday.q("inbox")["suggestions"]))


def test_removing_an_account_forgets_it_and_only_it(friday: Friday) -> None:
    sign_in(friday, "second@gmail.com", [CALENDAR])
    assert [a["email"] for a in status(friday)["accounts"]] == [ACCOUNT, "second@gmail.com"]
    out = friday.c("google_remove", account=ACCOUNT)
    assert [a["email"] for a in out["accounts"]] == ["second@gmail.com"]
    assert out["events"] is False and out["calendar"] is True
    assert ACCOUNT not in json.loads(secrets(friday).read_text())["google_accounts"]
    out = friday.c("google_remove", account="second@gmail.com")
    assert out["accounts"] == [] and out["calendar"] is False
    assert refused(friday, "google_remove", account="second@gmail.com")["field"] == "account"  # gone already


# Last: what it leaves behind (a 500) can't be cleaned up by the app.
@pytest.mark.xfail(
    strict=True,
    reason="BUG: offline with an expired sign-in, google_tasks_connect answers 500 "
    "(TransportError) instead of saying Google can't be reached",
)
def test_tasks_with_an_expired_sign_in_and_google_out_of_reach_is_said_in_words(friday: Friday) -> None:
    sign_in(friday, "expired@gmail.com", [CALENDAR, TASKS], expiry="2020-01-01T00:00:00Z")
    answer = friday.http.post("/api/c/google_tasks_connect", json={"account": "expired@gmail.com"})
    assert answer.status_code == 422, answer.text  # as Connect's own failure is said ("couldn't reach Google")
    assert "reach Google" in answer.json()["message"]
