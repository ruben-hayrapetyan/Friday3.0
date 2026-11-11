"""Asana (C103), glass box against its stand-in: your My tasks in every workspace you're in, nobody else's and no
unassigned ones, a time due before a day due, its projects in the notes, pages followed, done and opened again."""

from friday.integrations import asana
from tests.integrations.fake_asana import HARNESS, FakeAsana


def connector(fake: FakeAsana) -> asana.Asana:
    return asana.Asana(HARNESS.token, {}, fake.transport)


def test_your_open_tasks_from_every_workspace_and_nobody_elses() -> None:
    fake = FakeAsana(HARNESS.token)
    fake.add("Write the brief", "2026-10-23T17:00", notes="For the launch")
    fake.add("Side thing", "2026-10-24", workspace="w2", projects=[])
    fake.add("Sam's task", "2026-10-24", assignee="someone-else")
    fake.add("Nobody's", "2026-10-24", assignee=None)
    done = fake.add("Finished", "2026-10-20")
    fake.tasks[done]["completed"] = True
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Write the brief", "Side thing"}
    assert found["Write the brief"].due == "2026-10-23T21:00:00.000Z"  # due_at over due_on; the sync localises
    assert found["Write the brief"].notes == "For the launch\n\nIn Asana: Launch"
    assert found["Side thing"].due == "2026-10-24" and found["Side thing"].notes == ""
    assert found["Side thing"].url.startswith("https://app.asana.com/")


def test_every_page_is_followed() -> None:
    fake = FakeAsana(HARNESS.token, page_size=7)
    for n in range(30):
        fake.add(f"Task {n:02}", "2026-10-24")
    assert len(connector(fake).read()) == 30


def test_done_and_opened_again_complete_and_uncomplete_it() -> None:
    fake = FakeAsana(HARNESS.token)
    gid = fake.add("Write", "2026-10-24")
    connector(fake).write(gid, "done")
    assert fake.tasks[gid]["completed"] is True
    connector(fake).write(gid, "reopen")
    assert fake.tasks[gid]["completed"] is False
    assert fake.writes() == [f"PUT /tasks/{gid}"] * 2


def test_a_tracker_s_to_do_is_a_work_task_and_check_names_you() -> None:
    assert asana.Asana.caps.kind == "Work task"
    assert connector(FakeAsana(HARNESS.token)).check() == "maria@acme.test"
