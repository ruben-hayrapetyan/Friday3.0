"""Jira Cloud (C105), glass box against its stand-in: your site as an Atlassian address only (the token goes nowhere
else), the open issues assigned to you with their key and project, a paging token handed back twice stopping the
paging, done and opened again through the workflow's own transitions; and connecting with your site and email,
which are kept, the email beside the token never in the command log."""

from pathlib import Path

import pytest

from friday.integrations import jira, sync
from friday.integrations.base import ConnectorError
from tests.commands.helpers import new_app
from tests.integrations.fake_jira import EMAIL, HARNESS, FakeJira


def connector(fake: FakeJira) -> jira.Jira:
    return jira.Jira(HARNESS.token, HARNESS.fields, fake.transport)


@pytest.mark.parametrize(("given", "site"), [
    ("acme", "https://acme.atlassian.net"), ("ACME.atlassian.net", "https://acme.atlassian.net"),
    ("https://acme.atlassian.net/jira/software/projects/SHOP/boards/1", "https://acme.atlassian.net"),
    ("acme.atlassian.net.evil.example", "https://acme.atlassian.net"),  # only ever Atlassian's own address
])  # fmt: skip
def test_your_site_becomes_its_atlassian_address(given: str, site: str) -> None:
    assert jira.site_of(given) == site


@pytest.mark.parametrize("given", ["", "jira.mycompany.com", "https://evil.example/acme.atlassian"])
def test_a_site_that_isnt_atlassian_cloud_is_refused_in_words(given: str) -> None:
    with pytest.raises(ConnectorError, match="yourteam.atlassian.net"):
        jira.site_of(given)


def test_your_open_issues_with_their_key_and_project() -> None:
    fake = FakeJira(HARNESS.token)
    fake.add("Redesign checkout", "2026-10-23")
    fake.add("Someone else's", "2026-10-23", assignee="557058:sam")
    fake.add("Finished", "2026-10-20", status="done")
    fake.add("Started", None, status="doing")
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Redesign checkout", "Started"}
    checkout = found["Redesign checkout"]
    assert (checkout.due, checkout.notes) == ("2026-10-23", "In Jira: SHOP-1 (Shop redesign)")
    assert checkout.url == "https://acme.atlassian.net/browse/SHOP-1"


def test_every_page_is_followed_and_a_stuck_paging_token_stops() -> None:
    fake = FakeJira(HARNESS.token, page_size=7)
    for n in range(30):
        fake.add(f"Issue {n}")
    assert len(connector(fake).read()) == 30
    stuck = FakeJira(HARNESS.token, page_size=7, stuck_token=True)
    for n in range(30):
        stuck.add(f"Issue {n}")
    assert len(connector(stuck).read()) <= 30 and len(stuck.requests) <= 3  # not round and round forever


def test_done_and_opened_again_go_through_the_workflow() -> None:
    fake = FakeJira(HARNESS.token)
    issue = fake.add("Fix", status="doing")
    connector(fake).write(issue, "done")
    assert fake.issues[issue]["status"] == "done"
    connector(fake).write(issue, "reopen")
    assert fake.issues[issue]["status"] == "reopened"  # its To Do-category status, by the workflow's own step
    assert fake.writes() == [f"POST /issue/{issue}/transitions"] * 2


def test_connecting_keeps_site_and_email_and_logs_neither(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeJira(HARNESS.token)
    monkeypatch.setitem(sync.TRANSPORTS, "jira", fake.transport)
    app = new_app(tmp_path)
    given = {"site": "https://acme.atlassian.net/browse/SHOP-1", "email": f" {EMAIL} ", "other": "x"}
    out = app.do("integration_connect", kind="jira", token=HARNESS.token, fields=given)
    assert "Maria Lopez on acme.atlassian.net" in out["message"]
    (source,) = app.table("sources")
    assert '"site": "https://acme.atlassian.net"' in source["config"] and f'"email": "{EMAIL}"' in source["config"]
    assert '"other"' not in source["config"]
    assert EMAIL not in str(app.table("command_log")) and HARNESS.token not in str(app.table("sources"))
