"""Mail by app password (tests/features.toml: mail_app), the whole pipeline: a real `fridayd serve` in its own folder,
each command sent over HTTP as Settings → Integrations sends it, and what it changed read back. Nothing here reaches
a real mail server: a mailbox already connected is written to this test server's own secrets.toml (in its tmp
config folder), as `mail_app_set` leaves it after a sign-in; a server that can't be reached is a `.invalid` name."""

import json
import sqlite3
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("mail_app"))
    yield server
    server.stop()


def secrets_file(friday: Friday) -> Path:
    return friday.folder / "config" / "secrets.toml"


def keep(friday: Friday, text: str) -> None:
    secrets_file(friday).write_text(text)


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_no_mailbox_is_listed_before_one_is_connected(friday: Friday) -> None:
    assert not secrets_file(friday).exists()
    assert friday.q("mail_app_accounts") == []


@pytest.mark.parametrize(
    ("body", "field", "words"),
    [
        ({"provider": "icloud", "address": "not-an-address", "password": "abcd"}, "address", "isn't an email address"),
        ({"provider": "icloud", "address": "a b@icloud.com", "password": "abcd"}, "address", "isn't an email address"),
        ({"provider": "yahoo", "address": "me@yahoo.com", "password": "   "}, "password", "Generate app password"),
        ({"provider": "other", "address": "me@example.com", "password": "abcd"}, "host", "imap.example.com"),
        ({"provider": "other", "address": "me@example.com", "password": "abcd", "host": "no dots"}, "host", "IMAP"),
    ],
)
def test_mail_app_set_refuses_what_it_cant_sign_in_with_before_asking_any_server(
    friday: Friday, body: dict, field: str, words: str
) -> None:
    said = refused(friday, "mail_app_set", **body)
    assert said["field"] == field and words in said["message"]
    assert friday.q("mail_app_accounts") == []  # nothing kept
    assert friday.q("settings")["gmail"]["enabled"] is False  # nor mail switched on


def test_mail_app_set_says_when_the_server_cant_be_reached_and_keeps_nothing(friday: Friday) -> None:
    said = refused(friday, "mail_app_set", provider="other", address="Me@Example.com", password="abcd",
                   host="imap.friday-test.invalid")  # fmt: skip
    assert said["field"] == "address" and "couldn't reach Other mail" in said["message"]
    assert friday.q("mail_app_accounts") == [] and not secrets_file(friday).exists()


def test_mail_app_set_refuses_an_unknown_provider(friday: Friday) -> None:
    answer = friday.http.post("/api/c/mail_app_set", json={"provider": "aol", "address": "me@aol.com",
                                                           "password": "x"})  # fmt: skip
    assert answer.status_code == 422, answer.text
    (error,) = answer.json()["detail"]
    assert error["loc"] == ["body", "provider"] and "'icloud', 'yahoo', 'fastmail' or 'other'" in error["msg"]


def test_connected_mailboxes_are_listed_by_provider_never_with_their_passwords(friday: Friday) -> None:
    keep(friday, "\n".join([
        '[mail_app]', 'provider = "icloud"', 'address = "Me@iCloud.com"', 'password = "pw-one"', '',
        '[mail_app_2]', 'provider = "other"', 'address = "work@example.com"', 'password = "pw-two"',
        'host = "imap.friday-test.invalid"', '',
        '[outlook_mail]', 'address = "Me@Outlook.com"', 'tokens = "tok-three"', '',
        '[mail_app_3]', 'provider = "aol"', 'address = "skip@aol.com"', 'password = "pw-four"', '',
    ]))  # fmt: skip
    answer = friday.http.get("/api/q/mail_app_accounts")
    assert answer.status_code == 200
    assert answer.json() == [
        {"provider": "icloud", "name": "iCloud Mail", "address": "me@icloud.com"},  # addresses lowercased
        {"provider": "other", "name": "Other mail", "address": "work@example.com"},
        {"provider": "outlook", "name": "Outlook", "address": "me@outlook.com"},
    ]  # a provider Friday doesn't know is left out
    assert not any(secret in answer.text for secret in ("pw-one", "pw-two", "tok-three"))


def test_mail_app_forget_removes_that_mailbox_and_switches_its_source_off(friday: Friday) -> None:
    db = sqlite3.connect(friday.folder / "data" / "friday.db")
    for address in ("me@icloud.com", "jim.me@icloud.com"):
        db.execute("INSERT INTO sources (user_id, kind, name, config, enabled) VALUES (1, 'mail', ?, ?, 1)",
                   [f"iCloud Mail {address}", json.dumps({"account": address})])  # fmt: skip
    db.commit()
    said = friday.c("mail_app_forget", address=" ME@icloud.com ")
    assert said["message"] == "Removed: Friday no longer reads me@icloud.com. What its mail brought in stays"
    assert [a["address"] for a in friday.q("mail_app_accounts")] == ["work@example.com", "me@outlook.com"]
    kept = tomllib.loads(secrets_file(friday).read_text())
    assert "mail_app" not in kept and kept["mail_app_2"]["password"] == "pw-two"  # the others kept as they were
    enabled = dict(db.execute("SELECT json_extract(config, '$.account'), enabled FROM sources WHERE kind = 'mail'"))
    db.close()
    assert enabled == {"me@icloud.com": 0, "jim.me@icloud.com": 1}  # its own source, not every one containing it


def test_mail_app_forget_removes_an_outlook_mailbox_too(friday: Friday) -> None:
    friday.c("mail_app_forget", address="me@outlook.com")
    assert [a["address"] for a in friday.q("mail_app_accounts")] == ["work@example.com"]
    assert "outlook_mail" not in tomllib.loads(secrets_file(friday).read_text())


def test_mail_app_forget_refuses_an_address_not_connected(friday: Friday) -> None:
    said = refused(friday, "mail_app_forget", address="me@icloud.com")  # forgotten already
    assert said == {"field": "address", "message": "address: me@icloud.com isn't connected"}
    assert refused(friday, "mail_app_forget", address="  ")["message"] == "address: that address isn't connected"
    assert [a["address"] for a in friday.q("mail_app_accounts")] == ["work@example.com"]


def test_mail_app_forget_refuses_a_secrets_file_it_didnt_write(friday: Friday) -> None:
    keep(friday, '[mail_app]\nprovider = "icloud"\naddress = "a@icloud.com"\npassword = "p"\n[odd]\nlist = [1, 2]\n')
    said = refused(friday, "mail_app_forget", address="a@icloud.com")
    assert said["field"] == "password" and "holds more than Friday writes there" in said["message"]
    assert "a@icloud.com" in secrets_file(friday).read_text()  # left as it was
