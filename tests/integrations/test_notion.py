"""Notion (C101), glass box against its stand-in: which shared databases are to-do lists, what says done in each
(a checkbox, or Notion's Status and its Complete group), which date is the due and which number the length, a range
due at its end, a time in a workspace zone, nothing shared said in words, done and opened again through a Status.
And the sync's own part: a due with an offset or in UTC is put on your clock (Todoist's fixed-zone times too)."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.integrations import notion, sync
from friday.integrations.base import ConnectorError
from friday.integrations.sync import local_due
from tests.commands.helpers import new_app
from tests.integrations.contract import World
from tests.integrations.fake_notion import HARNESS, ME, STATUS, FakeNotion, notion_date, rich


def connector(fake: FakeNotion, lists: dict[str, bool] | None = None) -> notion.Notion:
    return notion.Notion(HARNESS.token, {"lists": lists or {}}, fake.transport)


@pytest.fixture
def fake() -> FakeNotion:
    return FakeNotion(HARNESS.token, shared=("ds-tasks", "ds-projects", "ds-reading"))


def test_only_shared_databases_that_say_done_are_read_each_its_own_way(fake: FakeNotion) -> None:
    lists = {t.name: t for t in connector(fake).lists()}
    assert set(lists) == {"Tasks", "Projects"}  # the reading list has nothing that says done
    tasks, projects = lists["Tasks"], lists["Projects"]
    assert (tasks.title, tasks.done.kind, tasks.due, tasks.length) == ("Name", "checkbox", "Due", ("Estimate (min)", 1))
    assert projects.done == notion.Done("Status", "status", ("Done", "Dropped"), "Not started")
    assert projects.due == "Deadline" and projects.length == ("Hours", 60)  # Deadline over Kickoff, by its name


def test_check_names_the_workspace_and_its_lists_or_says_how_to_share_one(fake: FakeNotion) -> None:
    assert connector(fake).check() == "Maria's Notion, 2 to-do lists: choose which in its box"
    fake.shared = []
    said = connector(fake).check()
    assert said.startswith("Maria's Notion, with no to-do list Friday can see yet") and "Connections" in said
    with pytest.raises(ConnectorError, match="can't see a to-do list") as error:
        connector(fake).read()
    assert error.value.problem == "access"


def test_open_pages_only_with_their_due_length_and_list(fake: FakeNotion) -> None:
    fake.add("Write the report", "2026-10-22", 90)
    done = fake.add("Old thing", "2026-10-01")
    fake.pages[done]["properties"]["Done"]["checkbox"] = True
    fake.add("Ship v2", hours=1.5, date={"start": "2026-10-20", "end": "2026-10-30", "time_zone": None},
             source="ds-projects")  # fmt: skip
    fake.add("Abandoned", "2026-10-25", source="ds-projects", status=3)  # Dropped: in the Complete group
    fake.add("Plan launch", "2026-10-23T17:00", source="ds-projects", status=1)
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Write the report", "Ship v2", "Plan launch"}
    assert (found["Write the report"].due, found["Write the report"].minutes) == ("2026-10-22", 90)
    assert found["Ship v2"].due == "2026-10-30" and found["Ship v2"].minutes == 90  # a range: due at its end
    assert found["Plan launch"].due == "2026-10-23T17:00-04:00"
    assert found["Plan launch"].notes == "In Notion: Projects" and found["Plan launch"].url.startswith(
        "https://www.notion.so/"
    )


def test_a_time_kept_with_its_zone_is_read_in_that_zone() -> None:
    assert notion.due_of({"start": "2026-11-20T09:00:00.000", "end": None, "time_zone": "Europe/Paris"}) == (
        "2026-11-20T09:00+01:00"
    )
    assert notion.due_of({"start": "2026-11-20T14:00:00.000Z", "end": None}) == "2026-11-20T14:00+00:00"
    assert notion.due_of(None) is None and notion.due_of({"start": None}) is None


def test_done_and_opened_again_through_a_status(fake: FakeNotion) -> None:
    page = fake.add("Plan launch", "2026-10-23", source="ds-projects", status=1)
    connector(fake).write(f"ds-projects/{page}", "done")
    assert fake.pages[page]["properties"]["Status"]["status"]["name"] == "Done"
    connector(fake).write(f"ds-projects/{page}", "reopen")
    assert fake.pages[page]["properties"]["Status"]["status"]["name"] == "Not started"
    assert fake.writes() == [f"PATCH /pages/{page}"] * 2


def test_a_page_deleted_in_notion_since_is_left_alone(fake: FakeNotion) -> None:
    page = fake.add("Gone", "2026-10-23")
    fake.pages[page]["in_trash"] = True
    connector(fake).write(f"ds-tasks/{page}", "done")
    assert fake.writes() == []


def test_a_list_unshared_since_is_said_when_its_page_is_ticked(fake: FakeNotion) -> None:
    page = fake.add("Write", "2026-10-23")
    fake.shared = ["ds-projects"]
    with pytest.raises(ConnectorError):
        connector(fake).write(f"ds-tasks/{page}", "done")


@pytest.mark.parametrize(("names", "found"), [
    ({"Due date": "date"}, "Due date"), ({"do_date": "date", "Created on": "date"}, "do_date"),
    ({"When": "date"}, "When"), ({"Start": "date", "End": "date"}, None), ({"Anything": "date"}, "Anything"),
])  # fmt: skip
def test_the_due_is_the_date_named_like_one_else_the_only_date(names: dict[str, str], found: str | None) -> None:
    assert notion.named({n: {"type": t} for n, t in names.items()}, "date", notion.DUE_NAMES) == found


def test_a_status_without_a_complete_option_doesnt_make_a_to_do_list() -> None:
    status = {"options": STATUS["options"][:2], "groups": [g | {"option_ids": []} if g["name"] == "Complete" else g
                                                          for g in STATUS["groups"]]}  # fmt: skip
    assert (
        notion.todo_list({"id": "x", "properties": {"T": {"type": "title"}, "S": {"type": "status", "status": status}}})
        is None
    )


def test_notion_is_asked_in_its_current_version_and_nothing_else(fake: FakeNotion) -> None:
    fake.add("Task", notion_date("2026-10-22")["start"])
    connector(fake).read()
    assert {r.headers["notion-version"] for r in fake.requests} == {notion.VERSION}


@pytest.mark.parametrize(("due", "local"), [
    ("2026-10-23T21:00Z", "2026-10-23T17:00"),  # Todoist's fixed-zone time
    ("2026-10-23T17:00-04:00", "2026-10-23T17:00"), ("2026-10-23T23:00+02:00", "2026-10-23T17:00"),
    ("2026-10-23T17:00", "2026-10-23T17:00"), ("2026-10-23", "2026-10-23"), (None, None),
])  # fmt: skip
def test_a_due_with_an_offset_is_put_on_your_clock(due: str | None, local: str | None) -> None:
    assert local_due(due, "America/New_York") == local


def test_a_page_is_known_with_its_list_so_a_list_switched_off_can_let_go_of_its_own(fake: FakeNotion) -> None:
    page = fake.add("Write", "2026-10-23")
    assert [r.external_id for r in connector(fake).read()] == [f"ds-tasks/{page}"]
    assert connector(fake, {"ds-tasks": False}).read() == []


def test_a_team_list_starts_off_and_then_brings_only_your_pages() -> None:
    fake = FakeNotion(HARNESS.token, shared=("ds-tasks", "ds-team"))
    lists = {t.name: t for t in connector(fake).lists()}
    assert lists["Team board"].people == "Assignee" and lists["Team board"].team and not lists["Tasks"].team
    fake.add("Mine", "2026-10-23", source="ds-team", people=[ME, "u-sam"])
    fake.add("Sam's", "2026-10-23", source="ds-team", people=["u-sam"])
    fake.add("No one's", "2026-10-23", source="ds-team")
    assert connector(fake).read() == []  # off until you switch it on
    assert [r.title for r in connector(fake, {"ds-team": True}).read()] == ["Mine"]


def test_with_an_integration_secret_a_shared_team_list_is_read_whole() -> None:
    """A workspace's integration has no "you" to assign to: you shared that list with it on purpose."""
    fake = FakeNotion(HARNESS.token, shared=("ds-team",), personal=False)
    fake.add("Sam's", "2026-10-23", source="ds-team", people=["u-sam"])
    assert [r.title for r in connector(fake, {"ds-team": True}).read()] == ["Sam's"]


# Black box: the lists in the box, through the commands


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = FakeNotion(HARNESS.token, shared=("ds-tasks", "ds-projects", "ds-team"))
    monkeypatch.setitem(sync.TRANSPORTS, "notion", fake.transport)
    return World(HARNESS, new_app(tmp_path), fake)


def test_the_box_lists_each_list_with_its_switch_and_what_it_brought(world: World) -> None:
    world.fake.add("Write", "2026-10-22")
    world.fake.add("Plan launch", "2026-10-23", source="ds-projects", status=1)
    world.fake.add("Mine", "2026-10-23", source="ds-team", people=[ME])
    source = world.connect()
    world.sync()
    assert {i["title"] for i in world.items()} == {"Write", "Plan launch"}  # the team's is off until switched on
    assert [c["lists"] for c in world.app.do("integrations")] == [True]
    lists = {t["name"]: t for t in world.app.do("integration_lists", id=source)}
    assert {n: (t["on"], t["team"], t["made"]) for n, t in lists.items()} == {
        "Tasks": (True, False, 1), "Projects": (True, False, 1), "Team board": (False, True, 0),
    }  # fmt: skip
    world.app.do("integration_list_set", id=source, list="ds-team", on=True)
    world.sync()
    assert "Mine" in {i["title"] for i in world.items()}


def test_a_list_switched_off_keeps_its_to_dos_as_they_are_and_never_takes_them_as_done(world: World) -> None:
    world.fake.add("Plan launch", "2026-10-23", source="ds-projects", status=1)
    source = world.connect()
    world.sync()
    world.app.do("integration_list_set", id=source, list="ds-projects", on=False, keep=True)
    world.sync()
    world.sync()
    assert [i["title"] for i in world.items()] == ["Plan launch"], "a list switched off was taken as done"
    world.fake.pages[next(iter(world.fake.pages))]["properties"]["Project"]["title"] = rich("Plan the launch")
    world.app.do("integration_list_set", id=source, list="ds-projects", on=True)
    world.sync()
    assert [i["title"] for i in world.items()] == ["Plan the launch"], "switched back on, not in step again"


def test_a_list_switched_off_can_take_its_to_dos_with_it_and_undo_brings_them_back(world: World) -> None:
    world.fake.add("Plan launch", "2026-10-23", source="ds-projects", status=1)
    world.fake.add("Write", "2026-10-22")
    source = world.connect()
    world.sync()
    out = world.app.full("integration_list_set", payload={"id": source, "list": "ds-projects", "on": False,
                                                          "keep": False}, provisional=False)  # fmt: skip
    world.sync()
    assert [i["title"] for i in world.items()] == ["Write"]
    world.app.do("undo", command_id=out.command_id)
    assert {i["title"] for i in world.items()} == {"Write", "Plan launch"}


def test_a_service_without_lists_has_nothing_to_choose(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.integrations.fake_todoist import HARNESS as TODOIST

    monkeypatch.setitem(sync.TRANSPORTS, "todoist", TODOIST.fake(TODOIST.token).transport)
    out = world.app.do("integration_connect", kind="todoist", token=TODOIST.token)
    assert out["source"]["lists"] is False
    with pytest.raises(FieldError, match="no lists"):
        world.app.do("integration_lists", id=out["source"]["id"])
    with pytest.raises(FieldError, match="no lists"):
        world.app.do("integration_list_set", id=out["source"]["id"], list="x", on=False)
