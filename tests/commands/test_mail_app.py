"""Mail at the edges: by app password (gmail_app_set, mail_app_set, mail_app_forget), an address and a password are
needed, the server refusing or out of reach is said in words, forgetting one that isn't there says so, and a
secrets.toml holding more than Friday writes is left for you to edit. The mail servers are never reached: their
check is a stand-in, and secrets.toml is in the test's own folder (conftest). A mailbox switched off isn't read,
and only mail can be read again."""

from pathlib import Path

import pytest

from friday.commands import gmail_app, mail_app
from friday.commands.mail import mail_source, read_mail
from friday.core.items import FieldError
from friday.planner.store import load_settings
from friday.sync.imap_mail import ImapRefused
from tests.commands.helpers import App, new_app

PASSWORD = "abcdefghijklmnop"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def refused(*args: object, **kwargs: object) -> None:
    raise ImapRefused("the server said no to that address and app password")


def unreachable(*args: object, **kwargs: object) -> None:
    raise OSError("no route to host")


def test_mail_needs_an_address_and_a_password(app: App) -> None:
    with pytest.raises(FieldError, match="that isn't an email address"):
        app.do("mail_app_set", provider="icloud", address="me at icloud", password=PASSWORD)
    with pytest.raises(FieldError, match="paste the app password"):
        app.do("mail_app_set", provider="icloud", address="me@icloud.com", password="  ")


@pytest.mark.parametrize(("check", "field", "said"), [(refused, "password", "said no"), (unreachable, "address",
                         "couldn't reach iCloud Mail")])  # fmt: skip
def test_a_mail_server_refusing_or_out_of_reach_is_said(
    app: App, monkeypatch: pytest.MonkeyPatch, check: object, field: str, said: str
) -> None:
    monkeypatch.setattr(mail_app.imap_any, "check", check)
    with pytest.raises(FieldError, match=said) as error:
        app.do("mail_app_set", provider="icloud", address="me@icloud.com", password=PASSWORD)
    assert error.value.field == field


def test_forgetting_a_mailbox_that_isnt_connected_says_so(app: App) -> None:
    with pytest.raises(FieldError, match="nobody@icloud.com isn't connected"):
        app.do("mail_app_forget", address="nobody@icloud.com")


def test_a_gmail_address_is_an_address(app: App) -> None:
    with pytest.raises(FieldError, match="that isn't an email address"):
        app.do("gmail_app_set", address="me gmail", password=PASSWORD)


@pytest.mark.parametrize(("check", "field", "said"), [(refused, "password", "said no"), (unreachable, "address",
                         "couldn't reach Gmail")])  # fmt: skip
def test_gmail_refusing_or_out_of_reach_is_said(
    app: App, monkeypatch: pytest.MonkeyPatch, check: object, field: str, said: str
) -> None:
    monkeypatch.setattr(gmail_app.imap_mail, "check", check)
    with pytest.raises(FieldError, match=said) as error:
        app.do("gmail_app_set", address="me@gmail.com", password=PASSWORD)
    assert error.value.field == field


def test_an_empty_password_forgets_and_one_not_connected_says_so(app: App) -> None:
    with pytest.raises(FieldError, match="me@gmail.com isn't connected with an app password"):
        app.do("gmail_app_set", address="me@gmail.com", password="")


def test_a_secrets_file_with_more_than_friday_writes_is_left_to_you(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    (no_personal_config / "secrets.toml").write_text('[gmail]\naddress = "me@gmail.com"\n[gmail.extra]\nx = 1\n')
    monkeypatch.setattr(gmail_app.imap_mail, "check", lambda address, password: None)
    with pytest.raises(FieldError, match="holds more than Friday writes there"):
        app.do("gmail_app_set", address="me@gmail.com", password=PASSWORD)


def test_a_mailbox_switched_off_isnt_read(app: App) -> None:
    source = mail_source(app.conn, 1, "me@icloud.com", "mail", "iCloud Mail")
    app.conn.execute("UPDATE sources SET enabled = 0 WHERE id = ?", [source["id"]])
    never = lambda: pytest.fail("a switched-off mailbox was read")  # noqa: E731
    settings = load_settings(app.conn, 1)
    assert read_mail(app.conn, settings, app.now_utc, 1, never, "me@icloud.com", "mail", "iCloud Mail") == 0


def test_only_a_message_from_your_mail_can_be_read_again(app: App) -> None:
    app.do("document_add", name="Note", content="PS5 is due Friday.")
    (note,) = app.table("raw_inputs")
    with pytest.raises(FieldError, match="only a message from your mail can be read again"):
        app.do("mail_retry", id=note["id"])
    with pytest.raises(FieldError, match="only a message from your mail"):
        app.do("mail_retry", id=999)
