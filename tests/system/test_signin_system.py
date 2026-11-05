"""Signing in to a hosted Friday, the whole system (HOSTED.md S4): `fridayd account-add` makes your account in an
accounts file (H84), `fridayd --accounts … demo` serves behind the sign-in page as the server's copies do, the link
arrives by mail (written to an outbox here), opens a session over HTTP, and signing out ends it."""

import re
import subprocess
import sys
import time
from collections.abc import Iterator
from email import message_from_bytes
from pathlib import Path

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, free_port
from tests.system.test_profiles_system import env

EMAIL = "you@gmail.com"


class Hosted:
    def __init__(self, folder: Path) -> None:
        self.folder, self.port = folder, free_port()
        self.env = env(folder) | {"FRIDAY_MAIL_OUTBOX": str(folder / "outbox"),
                                  "FRIDAY_PUBLIC_URL": f"http://127.0.0.1:{self.port}"}  # fmt: skip
        self.fridayd = [sys.executable, "-m", "friday.server.main", "--accounts", str(folder / "accounts.db")]
        self.log = (folder / "server.out").open("w")
        self.process = subprocess.Popen(
            [*self.fridayd, "--data-dir", str(folder / "data"), "demo", "--port", str(self.port)],
            cwd=REPO, env=self.env, stdout=self.log, stderr=subprocess.STDOUT,
        )  # fmt: skip
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=60)
        for _ in range(240):
            try:
                if self.http.get("/signin").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("fridayd didn't start: " + (folder / "server.out").read_text()[-2000:])

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.fridayd, *args], cwd=REPO, env=self.env, capture_output=True, text=True, timeout=60
        )

    def links(self) -> list[str]:
        out = []
        for path in sorted((self.folder / "outbox").glob("*.eml")):
            body = message_from_bytes(path.read_bytes()).get_payload(decode=True).decode()
            out += re.findall(r"http://\S+/auth/link\?t=\S+", body)
        return out

    def codes(self) -> list[str]:
        out = []
        for path in sorted((self.folder / "outbox").glob("*.eml")):
            out += re.findall(r"^(\d{6}) is your", message_from_bytes(path.read_bytes())["Subject"])
        return out

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(15)
        self.log.close()


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Hosted]:
    server = Hosted(tmp_path_factory.mktemp("signin"))
    yield server
    server.stop()


def test_account_add_makes_your_account_once(hosted: Hosted) -> None:
    made = hosted.cli("account-add", "--email", EMAIL, "--username", "ruben", "--name", "Ruben", "--timezone",
                      "America/New_York")  # fmt: skip
    assert made.returncode == 0 and "Account ruben" in made.stdout, made.stderr
    again = hosted.cli("account-add", "--email", EMAIL, "--username", "ruben2", "--name", "Ruben")
    assert again.returncode != 0 and "already has an account" in again.stderr


def test_signed_out_everything_waits_and_the_link_signs_you_in_then_out(hosted: Hosted) -> None:
    assert hosted.http.get("/").status_code == 303
    assert hosted.http.get("/api/q/status").status_code == 401
    sent = hosted.http.post("/signin", data={"email": EMAIL})
    assert sent.status_code == 200 and "Check your email" in sent.text
    for _ in range(20):
        if hosted.links():
            break
        time.sleep(0.25)
    (link,) = hosted.links()
    opened = hosted.http.get(link, follow_redirects=False)
    assert opened.status_code == 303 and "friday_session=" in opened.headers["set-cookie"]
    assert hosted.http.get("/api/q/status").json()["demo"] is True
    assert hosted.http.get("/auth/me").json()["username"] == "ruben"
    page = hosted.http.get("/")
    assert page.status_code == 200 and "<html" in page.text.lower()  # the app itself
    out = hosted.http.post("/auth/signout", follow_redirects=False)
    assert out.status_code == 303 and hosted.http.get("/api/q/status").status_code == 401


def test_account_add_without_an_accounts_file_says_what_it_needs() -> None:
    done = subprocess.run([sys.executable, "-m", "friday.server.main", "account-add", "--email", EMAIL, "--username",
                           "x1", "--name", "X"], cwd=REPO, capture_output=True, text=True, timeout=60)  # fmt: skip
    assert done.returncode != 0 and "needs --accounts" in done.stderr


def test_a_passkey_made_after_the_link_signs_you_in_again_over_http(hosted: Hosted) -> None:
    from tests.server.softkey import SoftKey

    own = {"origin": f"http://127.0.0.1:{hosted.port}"}
    hosted.http.post("/signin", data={"email": EMAIL})
    for _ in range(20):
        if len(hosted.links()) >= 2:
            break
        time.sleep(0.25)
    opened = hosted.http.get(hosted.links()[-1], follow_redirects=False)
    assert opened.headers["location"] == "/" and hosted.http.get("/auth/me").json()["offer_passkey"] is True
    soft = SoftKey(own["origin"], "127.0.0.1")
    asked = hosted.http.post("/auth/passkey/register/options", json={}, headers=own).json()
    made = hosted.http.post("/auth/passkey/register", headers=own,
                            json={"flow": asked["flow"], "credential": soft.create(asked["options"])})  # fmt: skip
    assert made.status_code == 200, made.text
    hosted.http.post("/auth/signout", headers=own, follow_redirects=False)
    assert hosted.http.get("/api/q/status").status_code == 401
    asked = hosted.http.post("/auth/passkey/signin/options", json={}, headers=own).json()
    done = hosted.http.post("/auth/passkey/signin", headers=own,
                            json={"flow": asked["flow"], "credential": soft.get(asked["options"])})  # fmt: skip
    assert done.status_code == 200 and done.json()["next"] == "/"
    assert hosted.http.get("/api/q/status").status_code == 200
    (listed,) = hosted.http.get("/auth/passkeys").json()
    assert listed["used"] is not None


def test_the_emailed_code_typed_where_you_asked_signs_you_in(hosted: Hosted) -> None:
    hosted.cli("account-add", "--email", EMAIL, "--username", "ruben", "--name", "Ruben")  # made once, either order
    own = {"origin": f"http://127.0.0.1:{hosted.port}"}
    hosted.http.post("/auth/signout", headers=own, follow_redirects=False)
    before = len(hosted.codes())
    page = hosted.http.post("/signin", data={"email": EMAIL}, headers=own)
    (flow,) = re.findall(r'name="flow" value="([^"]+)"', page.text)
    for _ in range(20):
        if len(hosted.codes()) > before:
            break
        time.sleep(0.25)
    code = hosted.codes()[-1]
    typed = hosted.http.post("/signin/code", data={"flow": flow, "code": code}, headers=own, follow_redirects=False)
    assert typed.status_code == 303 and typed.headers["location"] == "/"
    assert hosted.http.get("/auth/me").json()["username"] == "ruben"
