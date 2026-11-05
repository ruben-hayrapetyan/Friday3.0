"""A hosted Friday for the sign-in tests (tests/server/test_signin.py, test_passkeys_http.py): an app with an accounts
file and your account, its mail written to an outbox, at the staging copy's address."""

import re
from email import message_from_bytes
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.commands.registry import run
from friday.core.db import connect
from friday.server.accounts import Accounts
from friday.server.app import create_app

NOW = 29_000_000
EMAIL = "you@gmail.com"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> int:
        return self.now


@pytest.fixture
def site(tmp_path: Path) -> Path:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html>Friday app</html>")
    return tmp_path / "web"


def friday(tmp_path: Path, site: Path, clock: Clock, accounts: Accounts | None) -> TestClient:
    conn = connect(tmp_path / "friday.db")
    run(conn, "settings_set", {"key": "time", "value": {"timezone": "America/New_York"}}, now_utc=NOW, actor="cli",
        provisional=False)  # fmt: skip
    conn.close()
    app = create_app(tmp_path / "friday.db", clock=clock, background=False, web_dist=site, accounts=accounts)
    return TestClient(app, base_url="https://laptop.tailnet.ts.net:8443", follow_redirects=False)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def hosted(tmp_path: Path, site: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FRIDAY_MAIL_OUTBOX", str(tmp_path / "outbox"))
    monkeypatch.delenv("FRIDAY_PUBLIC_URL", raising=False)
    accounts = Accounts(tmp_path / "accounts.db")
    accounts.add(EMAIL, "ruben", "Ruben", "America/New_York", NOW)
    return friday(tmp_path, site, clock, accounts)


def mailed(tmp_path: Path) -> list[str]:
    """The links in the mail sent so far, oldest first."""
    out = []
    for path in sorted((tmp_path / "outbox").glob("*.eml")):
        body = message_from_bytes(path.read_bytes()).get_payload(decode=True).decode()
        out += re.findall(r"https://\S+/auth/link\?t=\S+", body)
    return out


def codes(tmp_path: Path) -> list[str]:
    """The codes in the mail sent so far, oldest first, read from the subject line as a notification shows them."""
    out = []
    for path in sorted((tmp_path / "outbox").glob("*.eml")):
        out += re.findall(r"^(\d{6}) is your Friday sign-in code$", message_from_bytes(path.read_bytes())["Subject"])
    return out


def ask_link(client: TestClient, email: str = EMAIL, app: str = "") -> str:
    """Asks for an email; the flow the page's code box carries."""
    answer = client.post("/signin", data={"email": email, "app": app})
    assert answer.status_code == 200 and "Check your email" in answer.text
    (flow,) = re.findall(r'name="flow" value="([^"]+)"', answer.text)
    return flow


def signed_in(client: TestClient, tmp_path: Path) -> None:
    ask_link(client)
    link = mailed(tmp_path)[-1]
    answer = client.get(link.split(".net:8443", 1)[1])
    assert answer.status_code == 303 and answer.headers["location"] == "/"
