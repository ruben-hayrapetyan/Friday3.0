"""Gmail with an app password, the whole pipeline (tests/features.toml: gmail_app; 8 Nov: users "can add their own
gmails - right now it just errors out for them"). A real `fridayd serve` in a folder of its own, `gmail_app_set` and
`gmail_app_accounts` sent over HTTP as Settings → Integrations' Gmail card sends them. Gmail itself isn't reached
from a test: what's checked is everything Friday decides before asking Gmail (a wrong address, a usual password, an
address not connected) and what it keeps in the scratch folder's own secrets.toml (written here as Friday writes it,
with made-up addresses): listed without their passwords, and forgotten one by one."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("gmail-app"))
    yield server
    server.stop()


def secrets(friday: Friday) -> Path:
    """The scratch Friday's secrets.toml, beside its friday.toml (never the real one)."""
    return friday.folder / "config" / "secrets.toml"


def keep(friday: Friday, text: str) -> None:
    secrets(friday).write_text(text)


def refused(friday: Friday, **body: Any) -> dict[str, Any]:
    answer = friday.http.post("/api/c/gmail_app_set", json=body)
    assert answer.status_code == 422, answer.text
    out = answer.json()
    return out | {"message": out["message"].removeprefix(f"{out['field']}: ")}


TWO = """[gmail_app]
address = "Pat.Student@gmail.com"
password = "abcdabcdabcdabcd"

[gmail_app_2]
address = "lab.group@gmail.com"
password = "wxyzwxyzwxyzwxyz"

[claude]
api_key = "not-a-real-key"
"""


def test_none_at_first(friday: Friday) -> None:
    assert friday.q("gmail_app_accounts") == []


def test_an_address_that_isnt_one_is_refused_before_gmail_is_asked(friday: Friday) -> None:
    for address in ("pat at gmail", "pat smith@gmail.com"):
        out = refused(friday, address=address, password="abcd abcd abcd abcd")
        assert out["field"] == "address" and out["message"].startswith("that isn't an email address")
    assert friday.q("gmail_app_accounts") == []
    assert not secrets(friday).exists()


def test_a_usual_password_is_refused_with_where_to_make_an_app_password(friday: Friday) -> None:
    for password in ("hunter2", "abcdabcdabcdabc1", "abcdabcdabcdabcdab"):
        out = refused(friday, address="pat@gmail.com", password=password)
        assert out["field"] == "password" and "16 letters" in out["message"]
        assert "https://myaccount.google.com/apppasswords" in out["message"]
    assert friday.q("gmail_app_accounts") == []
    assert friday.q("settings")["gmail"]["enabled"] is False  # nothing switched on by a refusal


def test_forgetting_an_address_not_connected_is_refused(friday: Friday) -> None:
    out = refused(friday, address="nobody@gmail.com", password="")
    assert out["field"] == "address" and out["message"] == "nobody@gmail.com isn't connected with an app password"


def test_the_kept_addresses_are_listed_lowercased_and_never_their_passwords(friday: Friday) -> None:
    keep(friday, TWO)
    answer = friday.http.get("/api/q/gmail_app_accounts")
    assert answer.json() == ["lab.group@gmail.com", "pat.student@gmail.com"]
    assert "abcd" not in answer.text and "wxyz" not in answer.text


def test_an_empty_password_forgets_that_address_alone(friday: Friday) -> None:
    said = friday.c("gmail_app_set", address="PAT.student@gmail.com ", password="  ")
    assert said["message"] == "Removed: Friday no longer reads pat.student@gmail.com. What its mail brought in stays"
    assert friday.q("gmail_app_accounts") == ["lab.group@gmail.com"]
    kept = secrets(friday).read_text()
    assert "pat.student" not in kept.lower() and "lab.group@gmail.com" in kept
    assert "not-a-real-key" in kept  # the AI's key beside it stays as it was
    again = refused(friday, address="pat.student@gmail.com", password="")
    assert "isn't connected" in again["message"]


def test_a_secrets_file_friday_didnt_write_is_left_alone(friday: Friday) -> None:
    keep(friday, '[gmail_app]\naddress = "lab.group@gmail.com"\npassword = "wxyzwxyzwxyzwxyz"\n\n[other]\nlist = [1]\n')
    out = refused(friday, address="lab.group@gmail.com", password="")
    assert out["field"] == "password" and "holds more than Friday writes there" in out["message"]
    assert friday.q("gmail_app_accounts") == ["lab.group@gmail.com"]
    assert "list = [1]" in secrets(friday).read_text()


def test_an_assistant_may_not_connect_a_mailbox(friday: Friday) -> None:
    token = friday.c("token_add", name="helper", scope="read-write")["token"]
    answer = friday.http.post("/api/c/gmail_app_set", json={"address": "lab.group@gmail.com", "password": ""},
                              headers={"authorization": f"Bearer {token}"})  # fmt: skip
    assert answer.status_code == 422, answer.text
    assert "Only you can do that (gmail_app_set), not an assistant" in answer.json()["message"]
    assert friday.q("gmail_app_accounts") == ["lab.group@gmail.com"]
