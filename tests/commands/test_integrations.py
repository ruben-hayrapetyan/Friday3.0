"""The integration commands' own answers (C96, C101): a service Friday doesn't connect to, where a service gives you
its token or whether its sign-in is ready in this copy of Friday, a service that fails while its lists are asked, a
list switched off taking its waiting Inbox entries with it, and an integration that isn't connected."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.integrations import keys, sync
from tests.commands.helpers import App, new_app
from tests.integrations.contract import World
from tests.integrations.fake_notion import HARNESS, FakeNotion


@pytest.fixture(autouse=True)
def no_app_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Friday's app ids only as a test gives them: the keys file (Mac/app_keys.json) is never read."""
    monkeypatch.setattr(keys, "PLACES", [])
    keys.kept.cache_clear()
    for name in ("MICROSOFT", "TRELLO", "TICKTICK", "SLACK"):
        monkeypatch.delenv(f"FRIDAY_{name}_CLIENT_ID", raising=False)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_connecting_a_service_friday_does_not_know_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="Friday doesn't connect to “myspace”") as refused:
        app.do("integration_connect", kind="myspace", token="x")
    assert refused.value.field == "kind" and app.table("sources") == []


def test_the_token_page_of_a_service_friday_does_not_know_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="Friday doesn't connect to “myspace”"):
        app.do("integration_token_page", kind="myspace")


def test_a_service_connected_by_a_token_you_copy_is_ready_with_no_page(app: App) -> None:
    assert app.do("integration_token_page", kind="todoist") == {"url": None, "ready": True}


def test_a_sign_in_is_ready_only_once_this_copy_of_friday_has_the_services_app_id(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert app.do("integration_token_page", kind="trello") == {"url": None, "ready": False}
    assert app.do("integration_token_page", kind="outlook_mail")["ready"] is False  # a mailbox, not an integration
    monkeypatch.setenv("FRIDAY_TRELLO_CLIENT_ID", "trello-stand-in-client")
    monkeypatch.setenv("FRIDAY_MICROSOFT_CLIENT_ID", "00000000-f00d-4000-8000-000000000001")
    assert app.do("integration_token_page", kind="trello") == {"url": None, "ready": True}
    assert app.do("integration_token_page", kind="outlook_mail")["ready"] is True


def test_a_service_with_a_token_page_answers_its_address_or_that_it_is_not_ready(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = "https://example.invalid/allow?key=friday"
    monkeypatch.setattr(sync.CONNECTORS["todoist"], "token_page", lambda: page, raising=False)
    assert app.do("integration_token_page", kind="todoist") == {"url": page, "ready": True}
    monkeypatch.setattr(sync.CONNECTORS["todoist"], "token_page", lambda: None)  # no app key in this copy
    assert app.do("integration_token_page", kind="todoist") == {"url": None, "ready": False}


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = FakeNotion(HARNESS.token, shared=("ds-tasks", "ds-projects"))
    monkeypatch.setitem(sync.TRANSPORTS, "notion", fake.transport)
    return World(HARNESS, new_app(tmp_path), fake)


def test_a_service_that_fails_while_its_lists_are_asked_says_why(world: World) -> None:
    source = world.connect()
    world.fake.fail_next(500, times=5)
    with pytest.raises(FieldError) as refused:
        world.app.do("integration_lists", id=source)
    assert refused.value.field == "id" and str(refused.value)


def test_a_list_switched_off_takes_its_waiting_inbox_entries_with_it(world: World) -> None:
    world.fake.add("Plan launch", "2026-10-23", source="ds-projects", status=1)
    world.fake.add("Write", "2026-10-22")
    source = world.connect(arrival="inbox_first")
    world.sync()
    waiting = [s for s in world.app.table("suggestions") if s["status"] == "pending"]
    assert len(waiting) == 2 and world.app.do("integrations")[0]["waiting"] == 2
    world.app.do("integration_list_set", id=source, list="ds-projects", on=False, keep=True)
    assert world.app.do("integrations")[0]["waiting"] == 1
    assert sorted(s["status"] for s in world.app.table("suggestions")) == ["pending", "superseded"]


def test_an_integration_that_is_not_connected_says_so(app: App) -> None:
    for command, extra in (("integration_set", {"arrival": "straight"}), ("integration_disconnect", {"keep": True})):
        with pytest.raises(FieldError, match="That integration isn't connected"):
            app.do(command, id=99, **extra)
