"""Sign in with Google (server/google_signin.py; HOSTED.md S4 step 3), against a fake Google that signs real tokens
(tests/server/fakegoogle.py). Glass box: the authorize address, PKCE and the one-time state. Black box over HTTP: the
button only once the copy has a client, back from Google into your account (or Friday Test's), an address without an
account told so, and every way an answer can be wrong refused."""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from friday.server.accounts import Accounts
from friday.server.google_signin import Client, GoogleError, GoogleSignIn, challenge_of
from tests.server.fakegoogle import CLIENT_ID, FakeGoogle
from tests.server.hosted import EMAIL, NOW, Clock, friday

BACK = "https://laptop.tailnet.ts.net:8443/auth/google"


@pytest.fixture
def google() -> Iterator[FakeGoogle]:
    fake = FakeGoogle()
    yield fake
    fake.stop()


@pytest.fixture
def signin(tmp_path: Path, google: FakeGoogle) -> GoogleSignIn:
    accounts = Accounts(tmp_path / "glass.db")
    env = google.environment()
    client = Client(env["FRIDAY_GOOGLE_CLIENT_ID"], "s", env["FRIDAY_GOOGLE_TOKEN_URL"], env["FRIDAY_GOOGLE_CERTS_URL"])
    return GoogleSignIn(accounts, client)


def query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# Glass box


def test_the_authorize_address_asks_only_to_sign_in_with_pkce_and_a_fresh_state(signin: GoogleSignIn) -> None:
    first, second = query(signin.start(BACK, NOW, None)), query(signin.start(BACK, NOW, None))
    assert first["scope"] == "openid email profile" and first["response_type"] == "code"
    assert first["redirect_uri"] == BACK and first["client_id"] == CLIENT_ID
    assert first["code_challenge_method"] == "S256" and first["prompt"] == "select_account"
    assert first["state"] != second["state"] and first["nonce"] != second["nonce"]


def test_the_code_is_traded_with_the_verifier_whose_challenge_was_sent(
    signin: GoogleSignIn, google: FakeGoogle
) -> None:
    asked = query(signin.start(BACK, NOW, "friday-test"))
    google.claims = {"email": "Ruben.Hayrapetyan28@gmail.com", "nonce": asked["nonce"]}
    assert signin.finish("the-code", asked["state"], BACK, NOW) == (EMAIL, "friday-test")
    (sent,) = google.requests
    assert challenge_of(sent["code_verifier"]) == asked["code_challenge"] and sent["code"] == "the-code"
    assert sent["redirect_uri"] == BACK and sent["grant_type"] == "authorization_code"


def test_a_state_is_used_once_and_runs_out(signin: GoogleSignIn, google: FakeGoogle) -> None:
    asked = query(signin.start(BACK, NOW, None))
    google.claims = {"email": EMAIL, "nonce": asked["nonce"]}
    signin.finish("c", asked["state"], BACK, NOW)
    with pytest.raises(GoogleError, match="already used"):
        signin.finish("c", asked["state"], BACK, NOW)
    late = query(signin.start(BACK, NOW, None))
    with pytest.raises(GoogleError, match="too long"):
        signin.finish("c", late["state"], BACK, NOW + 11)


@pytest.mark.parametrize(
    ("claims", "says"),
    [
        ({"nonce": "another"}, "wasn't for this sign-in"),
        ({"email_verified": False}, "hasn't checked"),
        ({"email": ""}, "hasn't checked"),
        ({"iss": "https://evil.example"}, "couldn't be checked|didn't come from Google"),
        ({"aud": "someone-elses-client"}, "couldn't be checked"),
    ],
)
def test_a_wrong_answer_is_refused(signin: GoogleSignIn, google: FakeGoogle, claims: dict, says: str) -> None:
    asked = query(signin.start(BACK, NOW, None))
    google.claims = {"email": EMAIL, "nonce": asked["nonce"]} | claims
    with pytest.raises(GoogleError, match=says):
        signin.finish("c", asked["state"], BACK, NOW)


def test_a_token_signed_by_another_key_is_refused(signin: GoogleSignIn, google: FakeGoogle) -> None:
    impostor = FakeGoogle()
    google.signer = impostor.signer  # signs with a key Google never published
    asked = query(signin.start(BACK, NOW, None))
    google.claims = {"email": EMAIL, "nonce": asked["nonce"]}
    with pytest.raises(GoogleError, match="couldn't be checked"):
        signin.finish("c", asked["state"], BACK, NOW)
    impostor.stop()


def test_google_refusing_the_code_is_said(signin: GoogleSignIn, google: FakeGoogle) -> None:
    asked = query(signin.start(BACK, NOW, None))
    google.refuse = True
    with pytest.raises(GoogleError, match="didn't accept"):
        signin.finish("c", asked["state"], BACK, NOW)


# Black box over HTTP


@pytest.fixture
def with_google(tmp_path: Path, site: Path, google: FakeGoogle, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for key, value in google.environment().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("FRIDAY_MAIL_OUTBOX", str(tmp_path / "outbox"))
    monkeypatch.delenv("FRIDAY_PUBLIC_URL", raising=False)
    accounts = Accounts(tmp_path / "accounts.db")
    accounts.add(EMAIL, "ruben", "Ruben", "America/New_York", NOW)
    return friday(tmp_path, site, Clock(), accounts)


def to_google(client: TestClient, app: str = "") -> dict[str, str]:
    started = client.get("/auth/google/start" + (f"?app={app}" if app else ""))
    assert started.status_code == 303 and started.headers["location"].startswith("http://127.0.0.1:")
    return query(started.headers["location"])


def test_no_button_until_the_copy_has_a_google_client(hosted: TestClient) -> None:
    assert "Continue with Google" not in hosted.get("/signin").text
    assert hosted.get("/auth/google/start").status_code == 404


def test_continue_with_google_signs_your_account_in(with_google: TestClient, google: FakeGoogle) -> None:
    assert "Continue with Google" in with_google.get("/signin").text
    asked = to_google(with_google)
    assert asked["redirect_uri"] == BACK
    google.claims = {"email": EMAIL, "nonce": asked["nonce"]}
    back = with_google.get(f"/auth/google?code=c&state={asked['state']}")
    assert (
        back.status_code == 303 and back.headers["location"] == "/" and "friday_session=" in back.headers["set-cookie"]
    )
    assert with_google.get("/auth/me").json()["username"] == "ruben"


def test_for_friday_test_google_hands_back_to_the_app(with_google: TestClient, google: FakeGoogle) -> None:
    assert 'href="/auth/google/start?app=friday-test"' in with_google.get("/signin?app=friday-test").text
    asked = to_google(with_google, "friday-test")
    google.claims = {"email": EMAIL, "nonce": asked["nonce"]}
    back = with_google.get(f"/auth/google?code=c&state={asked['state']}")
    assert back.status_code == 200 and "friday-test://signed-in?code=" in back.text and "set-cookie" not in back.headers


def test_a_google_account_without_a_friday_account_is_told_so(with_google: TestClient, google: FakeGoogle) -> None:
    asked = to_google(with_google)
    google.claims = {"email": "stranger@gmail.com", "nonce": asked["nonce"]}
    back = with_google.get(f"/auth/google?code=c&state={asked['state']}")
    assert back.status_code == 403 and "No Friday account for stranger@gmail.com" in back.text
    assert with_google.get("/api/q/status").status_code == 401


def test_cancel_on_googles_page_or_a_stale_state_signs_nobody_in(with_google: TestClient) -> None:
    assert with_google.get("/auth/google?error=access_denied&state=x").status_code == 400
    stale = with_google.get("/auth/google?code=c&state=made-up")
    assert stale.status_code == 400 and "try again" in stale.text
    assert with_google.get("/api/q/status").status_code == 401
