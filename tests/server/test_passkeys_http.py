"""Black box: passkeys on a hosted Friday over HTTP (HOSTED.md S4 step 2; H88–H91), Touch ID played by a software
authenticator. After an emailed link Friday offers a passkey once; one made in Settings signs you in from the email
box's autofill, in the browser or for Friday Test (handed back as the link is); your passkeys are listed and can be
removed; and another site's page can do none of it."""

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


def test_after_an_emailed_link_friday_offers_a_passkey_until_you_say_not_now(
    hosted: TestClient, tmp_path: Path
) -> None:
    assert sign_in_by_link(hosted, tmp_path) == "/auth/passkey/offer"
    offer = hosted.get("/auth/passkey/offer")
    assert "Use Touch ID next time?" in offer.text and "Not now" in offer.text
    later = hosted.get("/auth/passkey/later")
    assert later.headers["location"] == "/" and "friday_passkey=later" in later.headers["set-cookie"]
    assert sign_in_by_link(hosted, tmp_path) == "/"  # not offered again in this browser


def test_the_offer_isnt_made_again_once_this_browser_has_a_passkey(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    add_passkey(hosted)
    assert sign_in_by_link(hosted, tmp_path) == "/"


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
    assert done["status"] == 200 and done["cookie"] == ""  # the browser isn't signed in by it
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
    assert hosted.get("/auth/passkey/offer").status_code == 401


def test_another_sites_page_can_do_none_of_it(hosted: TestClient, tmp_path: Path) -> None:
    sign_in_by_link(hosted, tmp_path)
    evil = {"origin": "https://evil.example"}
    for path in ("/auth/passkey/register/options", "/auth/passkey/register", "/auth/passkey/signin/options",
                 "/auth/passkey/signin", "/auth/passkeys/remove"):  # fmt: skip
        assert hosted.post(path, json={}, headers=evil).status_code == 403, path


@pytest.mark.parametrize("flow", ["", "made-up"])
def test_an_unknown_ceremony_is_refused_in_words(hosted: TestClient, flow: str) -> None:
    answer = hosted.post("/auth/passkey/signin", json={"flow": flow, "credential": {}}, headers=OWN)
    assert answer.status_code == 400 and "try again" in answer.json()["message"]
