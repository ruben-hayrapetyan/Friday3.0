"""Glass box: the emailed 6-digit code (server/accounts.py; HOSTED.md S4 step 4, H92). Kept only as a hash salted with
its flow; five wrong tries end a code, twenty in an hour end codes for an address; using the code uses its link and
the other way round; an address without an account gets a flow that behaves the same."""

from pathlib import Path

import pytest

from friday.server.accounts import ADDRESS_TRIES, LINK_MINUTES, TYPED_TRIES, Accounts, digest

NOW = 29_000_000
EMAIL = "you@gmail.com"


@pytest.fixture
def accounts(tmp_path: Path) -> Accounts:
    made = Accounts(tmp_path / "accounts.db")
    made.add(EMAIL, "ruben", "Ruben", "America/New_York", NOW)
    return made


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


def test_a_code_is_six_digits_kept_only_as_a_hash_salted_with_its_flow(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code(EMAIL, NOW)
    assert len(code) == 6 and code.isdigit()
    with accounts.connect() as conn:
        (row,) = conn.execute("SELECT * FROM codes").fetchall()
    assert row["hash"] == digest(f"{flow}:{code}") and code not in row["hash"]
    assert row["expires"] == NOW + LINK_MINUTES and row["tries"] == 0


def test_the_right_code_signs_in_once_with_spaces_allowed(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code(EMAIL, NOW, app="friday-test")
    found, app = accounts.redeem_code(flow, f"{code[:3]} {code[3:]}", NOW + 1)  # type: ignore[misc]
    assert found.email == EMAIL and app == "friday-test"
    assert "run out" in str(accounts.redeem_code(flow, code, NOW + 2))


def test_a_code_runs_out_after_fifteen_minutes(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code(EMAIL, NOW)
    assert "run out" in str(accounts.redeem_code(flow, code, NOW + LINK_MINUTES + 1))


def test_wrong_tries_count_down_and_the_fifth_ends_the_code(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code(EMAIL, NOW)
    said = [accounts.redeem_code(flow, wrong(code), NOW) for _ in range(TYPED_TRIES)]
    assert said[0] == "That code isn't right. 4 more tries." and said[3] == "That code isn't right. 1 more try."
    assert said[4] == "That code isn't right."
    assert "run out" in str(accounts.redeem_code(flow, code, NOW))  # even the right one, now


def test_twenty_wrong_tries_in_an_hour_stop_codes_for_the_address(accounts: Accounts) -> None:
    for _ in range(ADDRESS_TRIES // TYPED_TRIES):
        flow, code = accounts.emailed_code(EMAIL, NOW)
        for _ in range(TYPED_TRIES):
            accounts.redeem_code(flow, wrong(code), NOW)
    flow, code = accounts.emailed_code(EMAIL, NOW)
    assert "Too many wrong codes" in str(accounts.redeem_code(flow, code, NOW))
    flow, code = accounts.emailed_code(EMAIL, NOW + 61)  # an hour on
    assert not isinstance(accounts.redeem_code(flow, code, NOW + 61), str)


def test_an_address_without_an_account_behaves_the_same_and_never_signs_in(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code("stranger@example.com", NOW)
    said = [accounts.redeem_code(flow, code, NOW) for _ in range(TYPED_TRIES + 1)]
    assert said[0] == "That code isn't right. 4 more tries." and "run out" in str(said[-1])


def test_the_code_and_its_link_are_one_sign_in(accounts: Accounts) -> None:
    flow, code = accounts.emailed_code(EMAIL, NOW)
    _, token = accounts.email_link(EMAIL, NOW) or (None, "")
    accounts.pair(flow, token)
    assert not isinstance(accounts.redeem_code(flow, code, NOW), str)
    assert accounts.redeem(token, "email", NOW) is None  # the link went with the code
    flow, code = accounts.emailed_code(EMAIL, NOW)
    _, token = accounts.email_link(EMAIL, NOW) or (None, "")
    accounts.pair(flow, token)
    assert accounts.redeem(token, "email", NOW) is not None
    assert "run out" in str(accounts.redeem_code(flow, code, NOW))  # the code went with the link


def test_an_unknown_flow_has_run_out(accounts: Accounts) -> None:
    assert "run out" in str(accounts.redeem_code("made-up", "123456", NOW))
