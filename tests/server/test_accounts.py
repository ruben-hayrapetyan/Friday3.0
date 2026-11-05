"""Glass box: the accounts file of a hosted Friday (server/accounts.py; HOSTED.md S4): accounts, one-time links and
codes, and sessions kept until signed out, with only tokens' hashes stored."""

from pathlib import Path

import pytest

from friday.server.accounts import CODE_MINUTES, LINK_MINUTES, Accounts, digest

NOW = 29_000_000


@pytest.fixture
def accounts(tmp_path: Path) -> Accounts:
    made = Accounts(tmp_path / "accounts.db")
    made.add("Ruben.Hayrapetyan28@gmail.com", "Ruben", "Ruben", "America/New_York", NOW)
    return made


def test_an_account_is_kept_lowercase_and_found_by_email_in_any_case(accounts: Accounts) -> None:
    found = accounts.by_email("RUBEN.hayrapetyan28@GMAIL.com")
    assert found is not None and found.email == "you@gmail.com" and found.username == "ruben"


@pytest.mark.parametrize(
    ("email", "username", "name", "says"),
    [
        ("you@gmail.com", "other", "R", "email: already has an account"),
        ("other@example.com", "RUBEN", "R", "username: already has an account"),
        ("not-an-address", "x2", "R", "email:"),
        ("a@example.com", "-x", "R", "username:"),
        ("a@example.com", "ok", "  ", "name:"),
    ],
)
def test_an_account_that_clashes_or_is_malformed_is_refused(
    accounts: Accounts, email: str, username: str, name: str, says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        accounts.add(email, username, name, "UTC", NOW)


def test_no_link_for_an_address_without_an_account(accounts: Accounts) -> None:
    assert accounts.email_link("nobody@example.com", NOW) is None


def test_a_link_works_once_and_only_until_it_runs_out(accounts: Accounts) -> None:
    made = accounts.email_link("you@gmail.com", NOW)
    assert made is not None
    _, token = made
    assert accounts.redeem(token, "email", NOW + LINK_MINUTES) is not None
    assert accounts.redeem(token, "email", NOW + 1) is None  # used
    _, late = accounts.email_link("you@gmail.com", NOW) or (None, "")
    assert accounts.redeem(late, "email", NOW + LINK_MINUTES + 1) is None


def test_a_link_is_not_a_code_and_a_code_is_not_a_link(accounts: Accounts) -> None:
    _, token = accounts.email_link("you@gmail.com", NOW, app="friday-test") or (None, "")
    assert accounts.redeem(token, "app", NOW) is None
    found, app = accounts.redeem(token, "email", NOW) or (None, None)
    assert found is not None and app == "friday-test"
    code = accounts.app_code(found.id, "friday-test", NOW)
    assert accounts.redeem(code, "email", NOW) is None
    assert accounts.redeem(code, "app", NOW + CODE_MINUTES + 1) is None


def test_only_hashes_are_stored(accounts: Accounts) -> None:
    _, token = accounts.email_link("you@gmail.com", NOW) or (None, "")
    session = accounts.start_session(1, "a browser", NOW)
    raw = accounts.path.read_bytes()
    assert token.encode() not in raw and session.encode() not in raw
    with accounts.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sessions WHERE hash = ?", [digest(session)]).fetchone()[0] == 1


def test_a_session_lasts_until_signed_out_and_notes_when_it_was_last_seen(accounts: Accounts) -> None:
    token = accounts.start_session(1, "a browser", NOW)
    assert accounts.session(token, NOW + 5 * 365 * 24 * 60) is not None  # years later: still signed in (H25)
    with accounts.connect() as conn:
        assert conn.execute("SELECT seen FROM sessions").fetchone()[0] == NOW + 5 * 365 * 24 * 60
    accounts.end_session(token, NOW + 1)
    assert accounts.session(token, NOW + 2) is None
    assert accounts.session(None, NOW) is None and accounts.session("made-up", NOW) is None


def test_signing_out_one_session_leaves_the_others(accounts: Accounts) -> None:
    laptop, app = accounts.start_session(1, "a browser", NOW), accounts.start_session(1, "Friday Test on a Mac", NOW)
    accounts.end_session(laptop, NOW)
    assert accounts.session(app, NOW) is not None


def test_opening_the_file_again_keeps_everything(accounts: Accounts) -> None:
    token = accounts.start_session(1, "a browser", NOW)
    again = Accounts(accounts.path)
    assert [a.username for a in again.all()] == ["ruben"] and again.session(token, NOW) is not None
