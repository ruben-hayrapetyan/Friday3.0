"""Black box: passkeys on a hosted Friday over HTTP (HOSTED.md S4 steps 2 and 4; H88–H91, H93, H94), Touch ID played
by a software authenticator. After an emailed link you land in Friday, which offers a passkey until you say Not now;
one made signs you in from the email box's autofill or straight away, by itself on a browser that has one, in the
browser or for Friday Test (handed back as the link is); your passkeys are listed and can be removed; and another
site's page can do none of it."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.server.hosted import ask_link, mailed
from tests.server.softkey import SoftKey

ORIGIN = "https://laptop.tailnet.ts.net:8443"
OWN = {"origin": ORIGIN}
CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


def path_of(link: str) -> str:
    return link.split(".net:8443", 1)[1]


def sign_in_by_link(client: TestClient, tmp_path: Path) -> str:
    """Signed in by an emailed link; where it lands."""
    ask_link(client)
    return client.get(path_of(mailed(tmp_path)[-1]), headers={"user-agent": CHROME}).headers["location"]


def add_passkey(client: TestClient) -> SoftKey:
    soft = SoftKey(ORIGIN, "laptop.tailnet.ts.net")
    asked = client.post("/auth/passkey/register/options", json={}, headers=OWN).json()
    body = {"flow": asked["flow"], "credential": soft.create(asked["options"])}
    made = client.post("/auth/passkey/register", json=body, headers=OWN | {"user-agent": CHROME})
    assert made.status_code == 200 and made.json()["name"] == "Mac, Chrome", made.text
    return soft


def passkey_signin(client: TestClient, soft: SoftKey, app: str | None = None) -> dict:
    asked = client.post("/auth/passkey/signin/options", json={"app": app}, headers=OWN).json()
    answer = client.post("/auth/passkey/signin", json={"flow": asked["flow"], "credential": soft.get(asked["options"])},
                         headers=OWN)  # fmt: skip
    return {"status": answer.status_code, **answer.json(), "cookie": answer.headers.get("set-cookie", "")}


def test_an_emailed_link_lands_in_friday_which_offers_a_passkey_until_you_say_not_now(
    hosted: TestClient, tmp_path: Path
) -> None:
    assert sign_in_by_link(hosted, tmp_path) == "/"  # no page in between (H94)
    assert hosted.get("/auth/me").json()["offer_passkey"] is True
    assert "Use Touch ID next time?" not in hosted.get("/auth/passkey/offer").text  # the old page is gone
    later = hosted.post("/auth/passkey/later", headers=OWN)
    assert later.json() == {"offer_passkey": False} and "friday_passkey=later" in later.headers["set-cookie"]
    sign_in_by_link(hosted, tmp_path)
    assert hosted.get("/auth/me").json()["offer_passkey"] is False  # not offered again in this browser


def test_the_offer_isnt_made_again_once_this_browser_has_a_passkey(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    add_passkey(hosted)
    sign_in_by_link(hosted, tmp_path)
    assert hosted.get("/auth/me").json()["offer_passkey"] is False


def test_touch_id_asks_by_itself_only_on_a_browser_that_has_a_passkey(hosted: TestClient, tmp_path: Path) -> None:
    assert "const KNOWN = false" in hosted.get("/signin").text
    assert 'id="passkey-button"' in hosted.get("/signin").text  # elsewhere, a button (H93)
    sign_in_by_link(hosted, tmp_path)
    add_passkey(hosted)
    hosted.post("/auth/signout", headers=OWN)
    assert "const KNOWN = true" in hosted.get("/signin").text


def test_signing_in_with_a_passkey_marks_this_browser_as_having_one(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    soft = add_passkey(hosted)
    hosted.post("/auth/signout", headers=OWN)
    hosted.cookies.clear()  # another browser, where the passkey arrived by sync
    assert "const KNOWN = false" in hosted.get("/signin").text
    done = passkey_signin(hosted, soft)
    assert "friday_passkey=made" in done["cookie"]
    assert hosted.get("/auth/me").json()["offer_passkey"] is False


def test_removing_your_last_passkey_brings_the_offer_back_and_stops_touch_id_asking(
    hosted: TestClient, tmp_path: Path
) -> None:
    sign_in_by_link(hosted, tmp_path)
    add_passkey(hosted)
    (listed,) = hosted.get("/auth/passkeys").json()
    hosted.post("/auth/passkeys/remove", json={"id": listed["id"]}, headers=OWN)
    assert hosted.get("/auth/me").json()["offer_passkey"] is True
    hosted.post("/auth/signout", headers=OWN)
    assert "const KNOWN = false" in hosted.get("/signin").text


def test_a_passkey_made_signs_this_browser_in_from_the_email_boxs_autofill(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    soft = add_passkey(hosted)
    hosted.post("/auth/signout", headers=OWN)
    assert hosted.get("/api/q/status").status_code == 401
    page = hosted.get("/signin").text
    assert 'autocomplete="username webauthn"' in page and "isConditionalMediationAvailable" in page
    done = passkey_signin(hosted, soft)
    assert done["status"] == 200 and done["next"] == "/" and "friday_session=" in done["cookie"]
    assert hosted.get("/api/q/status").status_code == 200


def test_for_friday_test_the_passkey_hands_back_to_the_app_as_the_link_does(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    soft = add_passkey(hosted)
    hosted.post("/auth/signout", headers=OWN)
    assert 'const APP = "friday-test"' in hosted.get("/signin?app=friday-test").text
    done = passkey_signin(hosted, soft, app="friday-test")
    assert done["status"] == 200 and "friday_session=" not in done["cookie"]  # the browser isn't signed in by it
    (code,) = re.findall(r"^friday-test://signed-in\?code=(.+)$", done["next"])
    assert hosted.get(f"/auth/app?code={code}").status_code == 303
    assert hosted.get("/api/q/status").status_code == 200


def test_your_passkeys_are_listed_and_one_removed_signs_nobody_in(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    soft = add_passkey(hosted)
    (listed,) = hosted.get("/auth/passkeys").json()
    assert listed["name"] == "Mac, Chrome" and listed["used"] is None
    assert hosted.post("/auth/passkeys/remove", json={"id": listed["id"]}, headers=OWN).json() == {"removed": True}
    assert hosted.get("/auth/passkeys").json() == []
    hosted.post("/auth/signout", headers=OWN)
    done = passkey_signin(hosted, soft)
    assert done["status"] == 400 and "doesn't know that passkey" in done["message"]


def test_signed_out_you_can_ask_to_sign_in_but_not_make_list_or_remove(hosted: TestClient) -> None:
    assert hosted.post("/auth/passkey/signin/options", json={}, headers=OWN).status_code == 200
    for path in ("/auth/passkey/register/options", "/auth/passkeys/remove"):
        assert hosted.post(path, json={}, headers=OWN).status_code == 401, path
    assert hosted.get("/auth/passkeys").status_code == 401
    assert hosted.post("/auth/passkey/later", headers=OWN).status_code == 401


def test_another_sites_page_can_do_none_of_it(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    evil = {"origin": "https://evil.example"}
    for path in ("/auth/passkey/register/options", "/auth/passkey/register", "/auth/passkey/signin/options",
                 "/auth/passkey/signin", "/auth/passkeys/remove", "/auth/passkey/later"):  # fmt: skip
        assert hosted.post(path, json={}, headers=evil).status_code == 403, path


@pytest.mark.parametrize("flow", ["", "made-up"])
def test_an_unknown_ceremony_is_refused_in_words(hosted: TestClient, flow: str) -> None:
    answer = hosted.post("/auth/passkey/signin", json={"flow": flow, "credential": {}}, headers=OWN)
    assert answer.status_code == 400 and "try again" in answer.json()["message"]


def test_the_email_box_is_focused_only_once_the_passkey_request_waits(hosted: TestClient) -> None:
    # 5 Nov: autofocused before the request began, Chrome never listed the passkey
    page = hosted.get("/signin").text
    (box,) = re.findall(r"<input id=\"email\"[^>]*>", page)
    assert "autofocus" not in box
    script = page[page.index("<script>") :]
    assert script.index('mediation: "conditional"') < script.index("focus();\n  let cred")
    assert "setTimeout(() => listen(tries + 1)" in script  # an ended request is made again
    ask = script[script.index("async function ask()") :]
    assert ask.index("stop.abort()") < ask.index("navigator.credentials.get")  # the box's request set aside first
