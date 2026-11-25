"""Connect Google (`google_connect`, Settings → Calendars), the whole pipeline: a real `fridayd serve` asked to sign in
over HTTP as the page asks, and the sign-in followed through `google_connect_status`. Never Google itself and never a
real browser: the server can name no address but this machine's (OFFLINE, as test_connecting_pipeline), its key file
is a made-up one in the test's own folder, and its "browser" (BROWSER) only writes down the page it was asked to open.
"""

import contextlib
import json
import os
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.system.test_beat_plan_system import Friday
from tests.system.test_connecting_pipeline import OFFLINE

KEY = {
    "installed": {
        "client_id": "made-up.apps.googleusercontent.com",
        "client_secret": "made-up",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, Path]]:
    shim = tmp_path_factory.mktemp("offline")
    (shim / "sitecustomize.py").write_text(OFFLINE)
    opened = tmp_path_factory.mktemp("browser") / "opened.txt"
    browser = opened.with_name("browser.sh")
    browser.write_text(f'#!/bin/sh\necho "$1" >> "{opened}"\n')
    browser.chmod(browser.stat().st_mode | stat.S_IXUSR)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("PYTHONPATH", str(shim))
        env.setenv("BROWSER", str(browser))
        friday = Friday(tmp_path_factory.mktemp("google_connect"))
    yield friday, opened
    friday.stop()


def status(friday: Friday) -> dict:
    return friday.q("google_connect_status")


def connect(friday: Friday, **body: object) -> dict:
    """Posted as the page posts it: unlogged (a sign-in isn't an undoable change), so no command id."""
    answer = friday.http.post("/api/c/google_connect", json=body)
    assert answer.status_code == 200, answer.text
    assert answer.json()["command_id"] is None
    return answer.json()["result"]


def waiting_url(friday: Friday) -> str:
    return friday.until(lambda: (s := status(friday))["state"] == "waiting" and s["url"], timeout=60)


def test_without_googles_key_file_it_says_so_and_starts_nothing(world: tuple[Friday, Path]) -> None:
    friday, opened = world
    if status(friday)["client_file"]:
        pytest.skip("this Python has Friday's shipped Google key: a sign-in would really start")
    answer = friday.http.post("/api/c/google_connect", json={})
    assert answer.status_code == 422
    assert answer.json()["message"] == "google: Friday needs the key file from Google Cloud first"
    assert status(friday)["state"] == "idle" and not opened.exists()


def test_it_opens_googles_page_asking_for_calendars_and_returns_at_once(world: tuple[Friday, Path]) -> None:
    friday, opened = world
    key = friday.folder / "config" / "google_client.json"  # beside friday.toml, where Settings saves it
    key.write_text(json.dumps(KEY))
    os.chmod(key, 0o600)
    assert status(friday)["client_file"] is True
    first = connect(friday)
    assert first["state"] == "waiting" and first["accounts"] == []
    url = waiting_url(friday)
    page = urlparse(url)
    asked = parse_qs(page.query)
    assert (page.scheme, page.netloc, page.path) == ("https", "accounts.google.com", "/o/oauth2/auth")
    assert asked["client_id"] == ["made-up.apps.googleusercontent.com"]
    assert any("auth/calendar" in scope for scope in asked["scope"][0].split()), asked["scope"]
    assert asked["redirect_uri"][0].startswith("http://localhost:")
    friday.until(lambda: opened.exists() and url in opened.read_text(), timeout=30)  # the browser was given it
    again = connect(friday)  # pressed again while it waits: the same sign-in, nothing new opened
    assert again["state"] == "waiting" and again["url"] == url
    assert opened.read_text().count("accounts.google.com") == 1


def test_cancel_stops_it_and_its_page_connects_nothing_after(world: tuple[Friday, Path]) -> None:
    friday, _ = world
    url = waiting_url(friday)
    out = friday.c("google_connect_cancel")
    assert (out["state"], out["message"], out["url"]) == ("idle", "Sign-in canceled.", None)
    back = parse_qs(urlparse(url).query)["redirect_uri"][0]
    with contextlib.suppress(httpx.HTTPError):  # Google's page coming back after the cancel: nothing is kept
        httpx.get(f"{back}/?code=made-up&state=x", timeout=5)
    time.sleep(1)
    assert status(friday)["state"] == "idle" and status(friday)["accounts"] == []


def test_google_out_of_reach_when_it_comes_back_fails_plainly_and_can_start_again(world: tuple[Friday, Path]) -> None:
    friday, _ = world
    connect(friday)
    url = waiting_url(friday)
    asked = parse_qs(urlparse(url).query)
    # Google's page sends you back with a code; trading it for a token needs Google, which is out of reach here
    httpx.get(f"{asked['redirect_uri'][0]}/?code=made-up&state={asked['state'][0]}", timeout=10)
    failed = friday.until(lambda: (s := status(friday))["state"] == "failed" and s, timeout=60)
    assert failed["message"] and "Traceback" not in failed["message"] and failed["url"] is None
    assert failed["accounts"] == [] and not (friday.folder / "data" / "secrets.json").exists()
    assert connect(friday)["state"] == "waiting"  # and it starts again
    friday.c("google_connect_cancel")
