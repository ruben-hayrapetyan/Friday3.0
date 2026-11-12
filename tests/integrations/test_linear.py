"""Linear (C104), glass box against its stand-in: the open issues assigned to you (not completed, not canceled, not
someone else's), each with its identifier and team, pages followed; done moves it to its team's first Done state and
opened again to the first Todo; the key bare in the header; GraphQL's errors said in words."""

import httpx
import pytest

from friday.integrations import linear
from friday.integrations.base import ConnectorError
from tests.integrations.fake_linear import HARNESS, STATES, FakeLinear
from tests.integrations.odd import odd


def connector(fake: FakeLinear) -> linear.Linear:
    return linear.Linear(HARNESS.token, {}, fake.transport)


def test_your_open_issues_with_their_identifier_and_team() -> None:
    fake = FakeLinear(HARNESS.token)
    fake.add("Fix the login bug", "2026-10-23", description="Users get logged out")
    fake.add("Someone else's", "2026-10-23", assignee="u-sam")
    fake.add("Shipped", "2026-10-20", state="st-shipped")
    fake.add("Won't do", "2026-10-20", state="st-canceled")
    fake.add("Started", None, state="st-doing")
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Fix the login bug", "Started"}
    bug = found["Fix the login bug"]
    assert (bug.due, bug.url) == ("2026-10-23", "https://linear.app/acme/issue/ENG-1")
    assert bug.notes == "Users get logged out\n\nIn Linear: ENG-1 (Engineering)"


def test_every_page_is_followed() -> None:
    fake = FakeLinear(HARNESS.token, page_size=7)
    for n in range(30):
        fake.add(f"Issue {n}")
    assert len(connector(fake).read()) == 30


def test_done_goes_to_the_first_done_state_and_reopen_to_the_first_todo() -> None:
    fake = FakeLinear(HARNESS.token)
    issue = fake.add("Fix", state="st-review")
    connector(fake).write(issue, "done")
    assert fake.issues[issue]["state"]["name"] == "Done"  # not Shipped: the first by its position
    connector(fake).write(issue, "reopen")
    assert fake.issues[issue]["state"]["name"] == "Todo"
    assert fake.writes() == ["mutation Move"] * 2


def test_the_key_goes_bare_in_the_header_as_linear_asks() -> None:
    fake = FakeLinear(HARNESS.token)
    connector(fake).check()
    assert fake.requests[0].headers["authorization"] == HARNESS.token


def test_graphql_errors_are_said_in_words() -> None:
    fake = FakeLinear(HARNESS.token)
    with pytest.raises(ConnectorError, match="didn't accept the token") as refused:
        linear.Linear("wrong", {}, fake.transport).check()
    assert refused.value.problem == "token"

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"message": "Rate limit exceeded",
                                                     "extensions": {"code": "RATELIMITED"}}]})  # fmt: skip

    with pytest.raises(ConnectorError, match="slow down") as slow:
        linear.Linear(HARNESS.token, {}, httpx.MockTransport(limited)).read()
    assert slow.value.problem == "rate"


def test_a_trackers_issue_is_a_work_task() -> None:
    assert linear.Linear.caps.kind == "Work task"


def test_an_issue_deleted_in_linear_since_has_nothing_left_to_change() -> None:
    fake = FakeLinear(HARNESS.token)
    connector(fake).write("00000000-0000-0000-0000-0000000000ff", "done")
    assert fake.writes() == []


def test_a_team_without_a_done_or_todo_state_is_said_and_nothing_is_moved() -> None:
    fake = FakeLinear(HARNESS.token)
    issue = fake.add("Fix", state="st-doing")
    started = [s for s in STATES if s["type"] == "started"]
    only = {"data": {"issue": {"team": {"states": {"nodes": started}}}}}
    stuck = linear.Linear(HARNESS.token, {}, odd(fake, "/graphql", only, op="States"))
    with pytest.raises(ConnectorError, match="no Done state to move it to"):
        stuck.write(issue, "done")
    with pytest.raises(ConnectorError, match="no Todo state"):
        stuck.write(issue, "reopen")
    assert fake.writes() == []


def test_a_change_linear_doesnt_say_it_saved_is_said() -> None:
    fake = FakeLinear(HARNESS.token)
    issue = fake.add("Fix")
    unsaved = {"data": {"issueUpdate": {"success": False}}}
    with pytest.raises(ConnectorError, match="Linear didn't save the change") as said:
        linear.Linear(HARNESS.token, {}, odd(fake, "/graphql", unsaved, op="Move")).write(issue, "done")
    assert said.value.problem == "answer"
