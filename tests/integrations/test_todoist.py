"""Todoist's connector, glass box (C96): how each shape of Todoist task reads, how pages are followed, what's sent.
Written against the fake (tests/integrations/fake_todoist.py), shaped as Doist's own SDK reads Todoist's API v1."""

import httpx
import pytest

from friday.integrations.base import ConnectorError
from friday.integrations.todoist import Todoist, local_minutes, minutes, remote
from tests.integrations.fake_todoist import HARNESS, FakeTodoist

TOKEN = HARNESS.token


def connector(fake: FakeTodoist) -> Todoist:
    return Todoist(TOKEN, {}, fake.transport)


@pytest.mark.parametrize(("due", "read"), [
    ("2026-11-20", "2026-11-20"),
    ("2026-11-20T17:00:00", "2026-11-20T17:00"),
    ("2026-11-20T22:00:00Z", "2026-11-20T22:00Z"),
    ("2026-11-20T17:00:00.000000", "2026-11-20T17:00"),
    (None, None),
])  # fmt: skip
def test_each_shape_of_due_reads_to_the_minute(due: str | None, read: str | None) -> None:
    assert local_minutes(due) == read


def test_a_deadline_stands_in_when_there_is_no_due() -> None:
    task = FakeTodoist(TOKEN)
    task_id = task.add("Report", None, deadline={"date": "2026-11-21", "lang": "en"})
    assert remote(task.tasks[task_id]).due == "2026-11-21"


@pytest.mark.parametrize(("duration", "got"), [
    ({"amount": 45, "unit": "minute"}, 45), ({"amount": 2, "unit": "day"}, 960),
    ({"amount": 0, "unit": "minute"}, None), (None, None), ({"amount": "x", "unit": "minute"}, None),
])  # fmt: skip
def test_a_duration_in_minutes_or_working_days(duration: dict | None, got: int | None) -> None:
    assert minutes(duration) == got


def test_a_task_keeps_its_notes_and_a_link_back_to_it() -> None:
    fake = FakeTodoist(TOKEN)
    task_id = fake.add("  Call the bank  ", "2026-11-20", description="About the card")
    r = remote(fake.tasks[task_id])
    assert r.title == "Call the bank" and r.notes == "About the card"
    assert r.url == f"https://app.todoist.com/app/task/{task_id}"


def test_every_page_is_read_following_the_cursor() -> None:
    fake = FakeTodoist(TOKEN, page_size=2)
    for n in range(5):
        fake.add(f"T{n}", "2026-11-20")
    found = connector(fake).read()
    assert [r.title for r in found] == ["T0", "T1", "T2", "T3", "T4"]
    cursors = [r.url.params.get("cursor") for r in fake.requests if r.url.path.endswith("/tasks")]
    assert cursors == [None, "2", "4"]


def test_done_ones_are_left_out() -> None:
    fake = FakeTodoist(TOKEN)
    fake.add("Open", "2026-11-20")
    fake.tasks[fake.add("Done", "2026-11-20")]["checked"] = True
    assert [r.title for r in connector(fake).read()] == ["Open"]


def test_done_and_reopen_are_the_close_and_reopen_calls() -> None:
    fake = FakeTodoist(TOKEN)
    task_id = fake.add("Pay", "2026-11-20")
    c = connector(fake)
    c.write(task_id, "done")
    c.write(task_id, "reopen")
    assert fake.writes() == [f"POST /tasks/{task_id}/close", f"POST /tasks/{task_id}/reopen"]
    assert all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in fake.requests)


def test_a_token_is_checked_with_one_project_read() -> None:
    fake = FakeTodoist(TOKEN)
    assert connector(fake).check() == "your Todoist"
    assert [r.url.path for r in fake.requests] == ["/api/v1/projects"]
    with pytest.raises(ConnectorError) as refused:
        Todoist("wrong", {}, fake.transport).check()
    assert refused.value.problem == "token"


def test_no_token_is_said_with_where_to_get_one() -> None:
    with pytest.raises(ConnectorError, match="app.todoist.com/app/settings/integrations/developer"):
        Todoist("  ")


def test_an_answer_in_the_wrong_shape_is_said_not_crashed_on() -> None:
    weird = httpx.MockTransport(lambda request: httpx.Response(200, json=["not", "a", "page"]))
    with pytest.raises(ConnectorError) as said:
        Todoist(TOKEN, {}, weird).read()
    assert said.value.problem == "answer"


def test_slow_down_keeps_how_long_todoist_asked_to_wait() -> None:
    fake = FakeTodoist(TOKEN)
    fake.fail_next(429, headers={"retry-after": "42"})
    with pytest.raises(ConnectorError) as said:
        connector(fake).read()
    assert said.value.problem == "rate" and said.value.retry_after_s == 42
