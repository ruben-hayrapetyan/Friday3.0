"""GitHub (C106), glass box against its stand-in: the open issues assigned to you and the pull requests whose review
is asked of you, nobody else's, a milestone's day as the due, a review titled as one, pages followed; read only."""

import pytest

from friday.integrations import github
from tests.integrations.fake_github import HARNESS, FakeGitHub


def connector(fake: FakeGitHub) -> github.GitHub:
    return github.GitHub(HARNESS.token, {}, fake.transport)


def test_your_issues_and_the_reviews_asked_of_you() -> None:
    fake = FakeGitHub(HARNESS.token)
    fake.add("Checkout fails on Safari", "2026-10-23")
    fake.add("Sam's issue", assignee="sam")
    fake.add("Your own PR", pr=True)  # assigned to you, but a pull request: not an issue, no review asked
    fake.add("Add dark mode", pr=True, assignee="sam", reviewer="maria-l", repo="acme/web")
    fake.add("Someone else's review", pr=True, assignee="sam", reviewer="lee")
    closed = fake.add("Closed one")
    fake.items[closed]["state"] = "closed"
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Checkout fails on Safari", "Review: Add dark mode"}
    bug = found["Checkout fails on Safari"]
    assert (bug.due, bug.notes, bug.url) == ("2026-10-23", "On GitHub: acme/shop#1, v2.0",
                                             "https://github.com/acme/shop/issues/1")  # fmt: skip
    assert found["Review: Add dark mode"].notes == "On GitHub: acme/web#4"


def test_every_page_is_followed() -> None:
    fake = FakeGitHub(HARNESS.token, page_size=7)
    for n in range(30):
        fake.add(f"Issue {n}")
    assert len(connector(fake).read()) == 30


def test_it_is_read_only_and_asks_in_githubs_current_version() -> None:
    fake = FakeGitHub(HARNESS.token)
    assert connector(fake).check() == "@maria-l"
    assert not github.GitHub.caps.two_way and github.GitHub.caps.kind == "Work task"
    with pytest.raises(AssertionError, match="read only"):
        connector(fake).write("1", "done")
    assert {r.headers["accept"] for r in fake.requests} == {"application/vnd.github+json"}
