"""Glass box: passkeys in a hosted Friday's accounts file (server/passkeys.py; H88–H91), with a software
authenticator standing in for Touch ID (tests/server/softkey.py)."""

from pathlib import Path

import pytest

from friday.server.accounts import Account, Accounts
from friday.server.passkeys import CHALLENGE_MINUTES, Party, PasskeyError, Passkeys, device_name
from tests.server.softkey import SoftKey

NOW = 29_000_000
PARTY = Party.of("https://laptop.tailnet.ts.net:8443")


@pytest.fixture
def made(tmp_path: Path) -> tuple[Passkeys, Account]:
    accounts = Accounts(tmp_path / "accounts.db")
    me = accounts.add("you@gmail.com", "ruben", "Ruben", "America/New_York", NOW)
    return Passkeys(accounts), me


def registered(keys: Passkeys, me: Account) -> SoftKey:
    soft = SoftKey(PARTY.origin, PARTY.rp_id)
    asked = keys.registration_options(me, PARTY, NOW)
    keys.register(me, asked["flow"], soft.create(asked["options"]), "Mac, Chrome", PARTY, NOW)
    return soft


def test_the_party_is_the_copys_own_address() -> None:
    assert Party("https://laptop.tailnet.ts.net:8443", "laptop.tailnet.ts.net") == PARTY
    assert Party.of("https://laptop.tailnet.ts.net/").origin == "https://laptop.tailnet.ts.net"


@pytest.mark.parametrize(
    ("agent", "name"),
    [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Mac, Chrome",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1) AppleWebKit/605.1.15 Version/18.1 Mobile Safari/604.1",
            "iPhone, Safari",
        ),
        ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/131.0 Safari/537.36 Edg/131.0", "Windows, Edge"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0", "Linux, Firefox"),
        ("curl/8.7.1", "A device"),
    ],
)
def test_a_passkeys_first_name_says_the_device_and_browser(agent: str, name: str) -> None:
    assert device_name(agent) == name


def test_registration_asks_for_a_discoverable_key_and_leaves_out_ones_already_made(
    made: tuple[Passkeys, Account],
) -> None:
    keys, me = made
    first = keys.registration_options(me, PARTY, NOW)["options"]
    assert first["rp"] == {"id": PARTY.rp_id, "name": "Friday"} and first["user"]["name"] == me.email
    assert first["authenticatorSelection"]["residentKey"] == "required" and first["excludeCredentials"] == []
    soft = registered(keys, me)
    again = keys.registration_options(me, PARTY, NOW)["options"]
    assert [c["id"] for c in again["excludeCredentials"]] == [keys.of(me.id)[0].id]
    assert keys.of(me.id)[0].id == soft.create(again)["id"]  # the same key: it would be refused by the browser


def test_a_made_passkey_signs_in_and_its_count_and_use_are_kept(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    soft = registered(keys, me)
    asked = keys.signin_options(PARTY, NOW + 5, None)
    found, app = keys.signin(asked["flow"], soft.get(asked["options"]), PARTY, NOW + 5)
    assert found == me and app is None
    (kept,) = keys.of(me.id)
    assert kept.name == "Mac, Chrome" and kept.created == NOW and kept.used == NOW + 5
    with keys.accounts.connect() as conn:
        assert conn.execute("SELECT sign_count FROM passkeys").fetchone()[0] == soft.count


def test_the_app_that_asked_comes_back_with_the_account(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    soft = registered(keys, me)
    asked = keys.signin_options(PARTY, NOW, "friday-test")
    assert keys.signin(asked["flow"], soft.get(asked["options"]), PARTY, NOW)[1] == "friday-test"


def test_a_ceremony_is_used_once_and_runs_out(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    soft = registered(keys, me)
    asked = keys.signin_options(PARTY, NOW, None)
    answer = soft.get(asked["options"])
    keys.signin(asked["flow"], answer, PARTY, NOW)
    with pytest.raises(PasskeyError, match="too long"):
        keys.signin(asked["flow"], answer, PARTY, NOW)  # replayed
    late = keys.signin_options(PARTY, NOW, None)
    with pytest.raises(PasskeyError, match="too long"):
        keys.signin(late["flow"], soft.get(late["options"]), PARTY, NOW + CHALLENGE_MINUTES + 1)


def test_an_answer_for_another_address_or_challenge_is_refused(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    soft = registered(keys, me)
    asked = keys.signin_options(PARTY, NOW, None)
    with pytest.raises(PasskeyError, match="couldn't be checked"):
        keys.signin(asked["flow"], soft.get(asked["options"], origin="https://evil.example"), PARTY, NOW)
    other = keys.signin_options(PARTY, NOW, None)
    swapped = keys.signin_options(PARTY, NOW, None)
    with pytest.raises(PasskeyError, match="couldn't be checked"):
        keys.signin(other["flow"], soft.get(swapped["options"]), PARTY, NOW)


def test_a_removed_or_unknown_passkey_signs_nobody_in(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    soft = registered(keys, me)
    assert keys.remove(me.id, keys.of(me.id)[0].id) and keys.of(me.id) == []
    asked = keys.signin_options(PARTY, NOW, None)
    with pytest.raises(PasskeyError, match="doesn't know that passkey"):
        keys.signin(asked["flow"], soft.get(asked["options"]), PARTY, NOW)
    assert not keys.remove(me.id, "made-up")


def test_registration_is_for_the_account_it_was_started_for(made: tuple[Passkeys, Account]) -> None:
    keys, me = made
    other = keys.accounts.add("someone@example.com", "someone", "Someone", "UTC", NOW)
    asked = keys.registration_options(me, PARTY, NOW)
    with pytest.raises(PasskeyError, match="another account"):
        keys.register(
            other, asked["flow"], SoftKey(PARTY.origin, PARTY.rp_id).create(asked["options"]), "x", PARTY, NOW
        )
