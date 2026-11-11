"""Trello (C102, C117), glass box against its stand-in: signed in by OAuth 2.0 (a Bearer token, never in an address),
only the open cards you're on, a card ticked complete or archived in Trello taken as done, its board said in the
notes, done here ticking the due date complete; the sign-in asks Atlassian for exactly what Friday needs."""

import pytest

from friday.integrations import trello
from tests.integrations.fake_trello import ACCESS, HARNESS, FakeTrello


def connector(fake: FakeTrello) -> trello.Trello:
    return trello.Trello(HARNESS.token, {}, fake.transport)


def test_only_open_cards_youre_on_come_in_with_their_board_and_due(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeTrello(HARNESS.token)
    fake.add("Draft the post", "2026-10-23T17:00", desc="800 words")
    fake.add("Sam's card", "2026-10-23", board="b2", members=("someone-else",))
    ticked = fake.add("Ticked", "2026-10-22")
    fake.cards[ticked]["dueComplete"] = True
    archived = fake.add("Archived", "2026-10-22")
    fake.cards[archived]["closed"] = True
    fake.add("Sprint task", None, board="b2")
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Draft the post", "Sprint task"}
    assert found["Draft the post"].due == "2026-10-23T21:00:00.000Z"  # UTC, as Trello keeps it: the sync localises
    assert found["Draft the post"].notes == "800 words\n\nOn Trello: Personal"
    assert found["Sprint task"].due is None and found["Sprint task"].notes == "On Trello: Team sprint"
    assert found["Sprint task"].url.startswith("https://trello.com/c/")


def test_the_token_goes_in_the_header_never_in_an_address() -> None:
    fake = FakeTrello(HARNESS.token)
    connector(fake).read()
    assert all(ACCESS not in str(r.url) for r in fake.requests)
    assert {r.headers["authorization"] for r in fake.requests} == {f"Bearer {ACCESS}"}


def test_done_and_opened_again_tick_and_untick_its_due_date() -> None:
    fake = FakeTrello(HARNESS.token)
    card = fake.add("Draft", "2026-10-23")
    connector(fake).write(card, "done")
    assert fake.cards[card]["dueComplete"] is True
    connector(fake).write(card, "reopen")
    assert fake.cards[card]["dueComplete"] is False
    assert fake.writes() == [f"PUT /cards/{card}"] * 2


def test_check_says_whose_trello_it_is() -> None:
    assert connector(FakeTrello(HARNESS.token)).check() == "Maria Lopez"


def test_the_sign_in_asks_atlassian_for_what_friday_needs_and_no_more() -> None:
    p = trello.PROVIDER
    assert p.ready() and p.secret is None  # a public client: PKCE, nothing secret shipped
    assert p.authorize == "https://auth.atlassian.com/authorize" and p.token == "https://auth.atlassian.com/oauth/token"
    assert p.scopes == ("read:board:trello", "write:board:trello", "read:member:trello", "offline_access")
