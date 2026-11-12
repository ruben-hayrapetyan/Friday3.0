"""Answers Friday can't use, from every service it reads by API, and the ways a request itself fails (integrations/
base.py): an answer in a shape the service's documentation doesn't promise, or not JSON at all, is said as the
service's own odd answer ("answer"), never a crash or a to-do made from half of it; a service that can't be reached
is "down"; a connector made without its token says where to make one; and a cursor that never ends stops."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from friday.integrations import asana, canvas, github, google_tasks, jira, linear, notion, outlook, sync, trello
from friday.integrations.base import ConnectorError, Http, pages
from friday.planner.store import load_settings
from tests.commands.helpers import new_app
from tests.integrations import (
    fake_asana,
    fake_canvas,
    fake_github,
    fake_google_tasks,
    fake_jira,
    fake_linear,
    fake_microsoft,
    fake_notion,
    fake_ticktick,
    fake_trello,
)
from tests.integrations.kit import Harness
from tests.integrations.odd import odd

INBOX = "/project/inbox/data"  # the Inbox by its alias, as TickTick takes it
NOT_JSON = b"<html><body>Service Unavailable</body></html>"

ODD: list[tuple[Harness, str, Any, str, str]] = [
    (fake_asana.HARNESS, "/users/me", {"data": []}, "check", "answer about you"),
    (fake_asana.HARNESS, "/users/me", NOT_JSON, "check", "answered with something Friday can't read"),
    (fake_asana.HARNESS, "/tasks", {"data": {"gid": "1"}}, "read", "list of tasks"),
    (fake_canvas.HARNESS, "/users/self", [], "check", "answer about you"),
    (fake_canvas.HARNESS, "/planner/items", {"errors": [{"message": "x"}]}, "read", "list came back"),
    (fake_canvas.HARNESS, "/planner/items", NOT_JSON, "read", "answered with something Friday can't read"),
    (fake_github.HARNESS, "/user", {"login": ""}, "check", "answer about you"),
    (fake_github.HARNESS, "/search/issues", {"items": None}, "read", "search came back"),
    (fake_google_tasks.HARNESS, "/users/@me/lists", [], "check", "Google Tasks answered in a shape"),
    (fake_jira.HARNESS, "/myself", ["Maria"], "check", "answer about you"),
    (fake_jira.HARNESS, "/search/jql", {"issues": None}, "read", "list of issues"),
    (fake_linear.HARNESS, "/graphql", [], "check", "Linear answered in a shape"),
    (fake_linear.HARNESS, "/graphql", {"data": None}, "read", "Linear answered in a shape"),
    (fake_microsoft.HARNESS, "/me", [], "check", "answer about you"),
    (fake_microsoft.HARNESS, "/me/todo/lists", {"value": None}, "read", "list came back"),
    (fake_notion.HARNESS, "/search", [], "read", "list of shared databases"),
    (fake_ticktick.HARNESS, "/project", {"projects": []}, "read", "lists came back"),
    (fake_ticktick.HARNESS, INBOX, {"tasks": None}, "read", "“Inbox” came back"),
    (fake_trello.HARNESS, "/members/me", [], "check", "answer about you"),
    (fake_trello.HARNESS, "/members/me/cards", {"cards": []}, "read", "list of cards"),
]


@pytest.mark.parametrize(("h", "path", "answer", "call", "words"), ODD,
                         ids=[f"{h.kind}-{call}-{path}-{type(a).__name__}" for h, path, a, call, _ in ODD])  # fmt: skip
def test_an_answer_in_a_shape_friday_doesnt_know_is_said_in_words(
    h: Harness, path: str, answer: Any, call: str, words: str
) -> None:
    fake = h.fake(h.token)
    h.add(fake, "Pay rent", "2026-10-22")
    connector = sync.CONNECTORS[h.kind](h.token, h.fields, odd(fake, path, answer))
    with pytest.raises(ConnectorError, match=words) as said:
        getattr(connector, call)()
    assert said.value.problem == "answer"
    assert h.token not in str(said.value)


def test_a_linear_error_friday_has_no_words_for_is_said_with_linears_own() -> None:
    fake = fake_linear.FakeLinear(fake_linear.HARNESS.token)
    error = {"errors": [{"message": "Argument Validation Error", "extensions": {"code": "INVALID_INPUT"}}]}
    connector = linear.Linear(fake_linear.HARNESS.token, {}, odd(fake, "/graphql", error, status=400))
    with pytest.raises(ConnectorError, match="Linear refused the request: Argument Validation Error") as said:
        connector.check()
    assert said.value.problem == "answer"


def test_outlook_saying_no_mailbox_or_an_odd_inbox_is_said_in_words() -> None:
    fake = fake_microsoft.FakeGraph("")
    nobody = {"displayName": "Maria", "mail": None, "userPrincipalName": "maria"}
    with pytest.raises(ConnectorError, match="didn't say which mailbox"):
        outlook.GraphMailService(fake_microsoft.TOKENS, {}, odd(fake, "/me", nobody)).check()
    reader = outlook.GraphMailService(fake_microsoft.TOKENS, {}, odd(fake, "/me/mailFolders/inbox/messages", {}))
    with pytest.raises(ConnectorError, match="list of mail came back in a shape"):
        reader.message_ids("newer_than:2d", 50)


Make = Callable[[], object]
NO_TOKEN: list[tuple[str, Make, str]] = [
    ("asana", lambda: asana.Asana("  "), "asana.com"),
    ("canvas", lambda: canvas.Canvas("", {"site": "canvas.cornell.edu"}), "Account → Settings"),
    ("github", lambda: github.GitHub(""), "github.com/settings/personal-access-tokens"),
    ("jira", lambda: jira.Jira("", {"site": "acme", "email": "maria@acme.test"}), "id.atlassian.com"),
    ("jira-email", lambda: jira.Jira("tok", {"site": "acme", "email": "maria"}), "the email you sign in to Jira"),
    ("linear", lambda: linear.Linear(" "), "linear.app"),
    ("notion", lambda: notion.Notion(""), "notion.so"),
    ("google_tasks", lambda: google_tasks.GoogleTasks("", {}), "Sign in with Google first"),
]


@pytest.mark.parametrize(("make", "words"), [(m, w) for _, m, w in NO_TOKEN], ids=[k for k, _, _ in NO_TOKEN])
def test_a_connector_without_its_token_says_where_to_make_one(make: Make, words: str) -> None:
    with pytest.raises(ConnectorError, match=words) as said:
        make()
    assert said.value.problem == "token"


def test_a_service_that_cant_be_reached_is_down_and_says_to_check_the_internet() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    http = Http("Asana", "https://app.asana.com/api/1.0", {}, httpx.MockTransport(unreachable))
    with pytest.raises(ConnectorError, match="Friday couldn't reach Asana: check the internet connection") as said:
        http.json("GET", "/users/me")
    assert said.value.problem == "down"


def test_a_cursor_that_never_ends_stops_after_its_most_pages() -> None:
    asked: list[str | None] = []

    def fetch(cursor: str | None) -> tuple[list[Any], str | None]:
        asked.append(cursor)
        return [len(asked)], "again"  # always another page

    assert list(pages(fetch, most=4)) == [1, 2, 3, 4]
    assert asked == [None, "again", "again", "again"]


PAGED: list[tuple[Harness, Callable[[], Any]]] = [
    (fake_canvas.HARNESS, lambda: fake_canvas.FakeCanvas(fake_canvas.HARNESS.token, page_size=1)),
    (
        fake_google_tasks.HARNESS,
        lambda: fake_google_tasks.FakeGoogleTasks(fake_google_tasks.HARNESS.token, page_size=1),
    ),
    (fake_microsoft.HARNESS, lambda: fake_microsoft.FakeGraph("", page_size=1)),
]


@pytest.mark.parametrize(("h", "make"), PAGED, ids=[h.kind for h, _ in PAGED])
def test_a_list_paged_one_by_one_stops_after_a_hundred_pages(h: Harness, make: Callable[[], Any]) -> None:
    fake = make()
    for n in range(103):
        h.add(fake, f"Task {n}", "2026-11-02")
    assert len(sync.CONNECTORS[h.kind](h.token, h.fields, fake.transport).read()) == 100


def connected(app: Any, h: Harness, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, int]:
    fake = h.fake(h.token)
    monkeypatch.setitem(sync.TRANSPORTS, h.kind, fake.transport)
    source = int(app.do("integration_connect", kind=h.kind, token=h.token, fields=h.fields)["source"]["id"])
    app.do("integration_set", id=source, arrival="straight")
    return fake, source


@pytest.mark.parametrize("trouble", ["token gone", "a bug"])
def test_one_integration_that_cant_be_read_stops_none_of_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, trouble: str
) -> None:
    # A connector that can't be made (its token gone from secrets.toml) or that breaks on an answer raised out of
    # the whole sync: every integration read after it, and everything waiting to go back, waited behind it
    app = new_app(tmp_path)
    _, broken = connected(app, fake_trello.HARNESS, monkeypatch)
    fake, _ = connected(app, fake_asana.HARNESS, monkeypatch)
    fake_asana.HARNESS.add(fake, "Pay rent", "2026-10-22")
    if trouble == "token gone":
        sync.forget_token(broken)
    else:
        monkeypatch.setattr(trello.Trello, "read", lambda self: {}["id"])
    sync.sync_all(app.conn, load_settings(app.conn), app.now_utc, asked=True)
    assert [i["title"] for i in app.do("items")] == ["Pay rent"]
    said = next(s for s in app.table("sources") if s["id"] == broken)
    assert said["failures"] == 1
    if trouble == "token gone":
        assert said["last_error"] == "Friday isn't signed in to Trello: press Sign in again"
    else:
        assert "Trello" in said["last_error"] and "reading Trello" in caplog.text
