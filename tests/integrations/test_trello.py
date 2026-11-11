"""Trello (C102), glass box against its stand-in: Friday's own app key with your token in the Authorization header
(never in an address), only the open cards you're on, a card ticked complete or archived in Trello taken as done, its
board said in the notes, done here ticking the due date complete; a Friday without its key says so in words."""

import pytest

from friday.integrations import trello
from friday.integrations.base import ConnectorError
from tests.integrations.fake_trello import HARNESS, KEY, FakeTrello


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
    assert all(HARNESS.token not in str(r.url) and KEY not in str(r.url) for r in fake.requests)
    assert all(r.headers["authorization"].startswith("OAuth oauth_consumer_key=") for r in fake.requests)


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


def test_a_friday_without_its_trello_key_says_so_and_has_no_page_to_send_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRIDAY_TRELLO_KEY")
    monkeypatch.setattr(trello, "APP_KEY", "")
    assert trello.token_page() is None
    with pytest.raises(ConnectorError, match="isn't ready in this copy of Friday"):
        trello.Trello(HARNESS.token)


def test_the_page_asks_trello_for_a_lasting_read_and_write_token_named_friday() -> None:
    page = trello.token_page()
    assert page is not None and page.startswith("https://trello.com/1/authorize?")
    for part in (f"key={KEY}", "name=Friday", "expiration=never", "scope=read%2Cwrite", "response_type=token"):
        assert part in page, part


def test_the_box_asks_the_server_for_the_allow_page(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.commands.helpers import new_app

    app = new_app(tmp_path)
    assert app.do("integration_token_page", kind="trello")["url"] == trello.token_page()
    assert app.do("integration_token_page", kind="todoist")["url"] is None  # its page is fixed: the box has it
    monkeypatch.delenv("FRIDAY_TRELLO_KEY")
    monkeypatch.setattr(trello, "APP_KEY", "")
    assert app.do("integration_token_page", kind="trello")["url"] is None
