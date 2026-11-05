"""Black box: signing in to a hosted Friday over HTTP (HOSTED.md S4; H81–H87). Everything waits behind the sign-in
page; the emailed link signs this browser in until it signs out; the Mac app's sign-in goes through the browser and
back (H43); another site's page can't sign anyone in or out; and your own Friday, with no accounts file, is as it was.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.server.accounts import LINK_MINUTES
from tests.server.hosted import EMAIL, NOW, Clock, ask_link, friday, mailed, signed_in


def test_everything_waits_behind_the_sign_in_page(hosted: TestClient) -> None:
    assert hosted.get("/").headers["location"] == "/signin"
    assert hosted.get("/todo").headers["location"] == "/signin"
    for path in ("/api/q/status", "/events", "/auth/me"):
        answer = hosted.get(path)
        assert answer.status_code == 401 and answer.json()["signin"] == "/signin", path
    assert hosted.post("/api/c/sync_now", json={}).status_code == 401
    page = hosted.get("/signin")
    assert page.status_code == 200 and "Email me a link" in page.text


def test_the_emailed_link_signs_this_browser_in_with_a_lasting_secure_cookie(
    hosted: TestClient, tmp_path: Path
) -> None:
    ask_link(hosted, "RUBEN.Hayrapetyan28@gmail.com")
    (link,) = mailed(tmp_path)
    assert link.startswith("https://laptop.tailnet.ts.net:8443/auth/link?t=")
    answer = hosted.get(link.split(".net:8443", 1)[1])
    cookie = answer.headers["set-cookie"].lower()
    for part in ("friday_session=", "httponly", "secure", "samesite=lax", "max-age=315360000"):
        assert part in cookie, part
    assert hosted.get("/").text == "<html>Friday app</html>"
    assert hosted.get("/api/q/status").status_code == 200
    assert hosted.get("/auth/me").json() == {"email": EMAIL, "username": "ruben", "name": "Ruben"}
    assert hosted.get("/signin").headers["location"] == "/"  # already in


def test_an_address_without_an_account_gets_the_same_answer_and_no_mail(hosted: TestClient, tmp_path: Path) -> None:
    ask_link(hosted, "stranger@example.com")
    assert mailed(tmp_path) == []


def test_a_link_works_once_and_not_after_fifteen_minutes(hosted: TestClient, tmp_path: Path, clock: Clock) -> None:
    ask_link(hosted)
    path = mailed(tmp_path)[0].split(".net:8443", 1)[1]
    clock.now += LINK_MINUTES + 1
    assert hosted.get(path).status_code == 400
    clock.now = NOW
    ask_link(hosted)
    fresh = mailed(tmp_path)[1].split(".net:8443", 1)[1]
    assert hosted.get(fresh).status_code == 303
    hosted.cookies.clear()
    late = hosted.get(fresh)
    assert late.status_code == 400 and "used or is too old" in late.text


def test_signing_out_ends_the_session_and_clears_what_the_browser_kept(hosted: TestClient, tmp_path: Path) -> None:
    signed_in(hosted, tmp_path)
    cookie = hosted.cookies.get("friday_session")
    answer = hosted.post("/auth/signout", headers={"origin": "https://laptop.tailnet.ts.net:8443"})
    assert answer.status_code == 303 and answer.headers["location"] == "/signin"
    assert answer.headers["clear-site-data"] == '"cache", "storage"'
    assert hosted.get("/api/q/status").status_code == 401
    hosted.cookies.set("friday_session", cookie or "")  # the old cookie, kept somewhere: ended all the same
    assert hosted.get("/api/q/status").status_code == 401


def test_another_sites_page_cant_sign_in_or_out(hosted: TestClient, tmp_path: Path) -> None:
    refused = hosted.post("/signin", data={"email": EMAIL}, headers={"origin": "https://evil.example"})
    assert refused.status_code == 403 and mailed(tmp_path) == []
    signed_in(hosted, tmp_path)
    assert hosted.post("/auth/signout", headers={"origin": "https://evil.example"}).status_code == 403
    assert hosted.get("/api/q/status").status_code == 200


def test_the_mac_app_signs_in_through_the_browser_and_back(hosted: TestClient, tmp_path: Path) -> None:
    page = hosted.get("/signin?app=friday-test")
    assert "Signing in Friday Test" in page.text and 'name="app" value="friday-test"' in page.text
    ask_link(hosted, app="friday-test")
    handed = hosted.get(mailed(tmp_path)[0].split(".net:8443", 1)[1])
    assert handed.status_code == 200 and "set-cookie" not in handed.headers  # the browser isn't signed in by it
    (back,) = re.findall(r'href="(friday-test://signed-in\?code=[^"]+)"', handed.text)
    code = back.split("code=", 1)[1]
    window = hosted.get(f"/auth/app?code={code}")  # the app's window, given the code
    assert window.status_code == 303 and "friday_session=" in window.headers["set-cookie"]
    assert hosted.get("/api/q/status").status_code == 200
    hosted.cookies.clear()
    assert hosted.get(f"/auth/app?code={code}").status_code == 400  # once only


def test_an_app_name_not_on_the_list_is_ignored(hosted: TestClient, tmp_path: Path) -> None:
    ask_link(hosted, app="evil")
    assert hosted.get(mailed(tmp_path)[0].split(".net:8443", 1)[1]).status_code == 303  # a plain sign-in


def test_without_a_mail_password_the_page_says_so(hosted: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_MAIL_OUTBOX")
    monkeypatch.delenv("FRIDAY_SMTP_PASSWORD", raising=False)
    answer = hosted.post("/signin", data={"email": EMAIL})
    assert answer.status_code == 503 and "app password" in answer.text and EMAIL in answer.text


def test_your_own_friday_with_no_accounts_file_needs_no_sign_in(tmp_path: Path, site: Path, clock: Clock) -> None:
    local = friday(tmp_path, site, clock, None)
    assert local.get("/").text == "<html>Friday app</html>"
    assert local.get("/api/q/status").status_code == 200
    assert local.get("/signin").status_code in (200, 404)  # the app's own page, if anything: no sign-in there
    assert "Email me a link" not in local.get("/signin").text
