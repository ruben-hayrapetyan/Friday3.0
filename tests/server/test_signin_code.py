"""Black box: the emailed code over HTTP (HOSTED.md S4 step 4, H92). The email's subject shows the code; typed on the
page that asked, it signs this browser in, or hands back to Friday Test as the link does; a wrong one says how many
tries are left; the link and code are one sign-in; and another site's page can't type one in."""

import html
import re
from email import message_from_bytes
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.server.hosted import EMAIL, ask_link, codes, mailed

OWN = {"origin": "https://laptop.tailnet.ts.net:8443"}


def type_code(client: TestClient, flow: str, code: str, app: str = "") -> httpx.Response:
    return client.post("/signin/code", data={"flow": flow, "code": code, "email": EMAIL, "app": app}, headers=OWN)


def said(answer: httpx.Response) -> str:
    return html.unescape(answer.text)


def test_the_email_leads_with_the_code_and_still_carries_the_link(hosted: TestClient, tmp_path: Path) -> None:
    ask_link(hosted)
    (code,) = codes(tmp_path)
    (path,) = sorted((tmp_path / "outbox").glob("*.eml"))
    body = message_from_bytes(path.read_bytes()).get_payload(decode=True).decode()
    assert body.startswith(f"Your code to sign in to Friday: {code}") and len(mailed(tmp_path)) == 1


def test_the_page_asks_for_the_code_where_you_are(hosted: TestClient) -> None:
    page = hosted.post("/signin", data={"email": EMAIL}).text
    (box,) = re.findall(r'<input id="code"[^>]*>', page)
    for part in ('autocomplete="one-time-code"', 'inputmode="numeric"', "autofocus"):
        assert part in box, part
    assert "requestSubmit" in page and "Send a new code" in page


def test_the_code_typed_signs_this_browser_in_and_lands_in_friday(hosted: TestClient, tmp_path: Path) -> None:
    flow = ask_link(hosted)
    (code,) = codes(tmp_path)
    answer = type_code(hosted, flow, code)
    assert answer.status_code == 303 and answer.headers["location"] == "/"
    assert "friday_session=" in answer.headers["set-cookie"]
    assert hosted.get("/api/q/status").status_code == 200
    assert hosted.get(mailed(tmp_path)[0].split(".net:8443", 1)[1]).status_code == 400  # its link went with it


def test_a_wrong_code_says_so_and_keeps_the_box(hosted: TestClient, tmp_path: Path) -> None:
    flow = ask_link(hosted)
    (code,) = codes(tmp_path)
    answer = type_code(hosted, flow, f"{(int(code) + 1) % 10**6:06d}")
    assert answer.status_code == 400 and "isn't right. 4 more tries." in said(answer)
    assert f'name="flow" value="{flow}"' in answer.text
    assert hosted.get("/api/q/status").status_code == 401
    assert type_code(hosted, flow, code).status_code == 303


def test_an_address_without_an_account_gets_the_same_page_and_no_mail(hosted: TestClient, tmp_path: Path) -> None:
    flow = ask_link(hosted, "stranger@example.com")
    assert mailed(tmp_path) == [] and codes(tmp_path) == []
    answer = type_code(hosted, flow, "123456")
    assert answer.status_code == 400 and "isn't right. 4 more tries." in said(answer)


def test_for_friday_test_the_code_hands_back_to_the_app(hosted: TestClient, tmp_path: Path) -> None:
    flow = ask_link(hosted, app="friday-test")
    (code,) = codes(tmp_path)
    answer = type_code(hosted, flow, code, app="friday-test")
    assert answer.status_code == 200 and "set-cookie" not in answer.headers
    (back,) = re.findall(r'href="(friday-test://signed-in\?code=[^"]+)"', answer.text)
    assert hosted.get(f"/auth/app?code={back.split('code=', 1)[1]}").status_code == 303
    assert hosted.get("/api/q/status").status_code == 200


def test_another_sites_page_cant_type_a_code(hosted: TestClient, tmp_path: Path) -> None:
    flow = ask_link(hosted)
    (code,) = codes(tmp_path)
    answer = hosted.post("/signin/code", data={"flow": flow, "code": code}, headers={"origin": "https://evil.example"})
    assert answer.status_code == 403 and hosted.get("/api/q/status").status_code == 401
