"""To-dos, events and tags, the whole pipeline (tests/features.toml: items; 24 Nov, the user: "go through every single
functionality of the app and build an extensive test suite ... absolutely nothing can break without our tests flagging
it"): a real `fridayd serve` in its own folder, each command sent over HTTP as the To-do page sends it, and what then
follows read back through the items, the item, the plan and the tags."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("items"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def settled(friday: Friday) -> None:
    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, 600)  # a busy machine replans slowly


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def item(friday: Friday, item_id: int) -> dict:
    return friday.q("item", id=item_id)


def listed(friday: Friday, item_id: int, status: str = "all") -> dict:
    return next(i for i in friday.q("items", status=status) if i["id"] == item_id)


def planned_min(friday: Friday, item_id: int) -> int:
    def minutes(b: dict) -> int:
        start, end = (datetime.fromisoformat(b[k]) for k in ("start", "end"))
        return int((end - start).total_seconds() // 60)

    return sum(minutes(b) for b in item(friday, item_id)["blocks"] if b["state"] is None)


def add(friday: Friday, title: str, **fields: object) -> int:
    return friday.c("add", title=title, **fields)["item"]["id"]


# edit


def test_a_new_length_is_your_estimate_and_the_plan_gives_it_that_much(friday: Friday) -> None:
    essay = add(friday, "Essay draft", duration_min=240, due=f"{day(5)}T17:00")
    settled(friday)
    assert planned_min(friday, essay) >= 240
    out = friday.c("edit", id=essay, duration_min=60)["item"]
    assert (out["duration_min"], out["remaining_min"]) == (60, 60)
    settled(friday)
    assert 60 <= planned_min(friday, essay) < 240  # the plan follows: not the old four hours


def test_editing_title_notes_and_importance_reads_back_everywhere(friday: Friday) -> None:
    task = add(friday, "Old title", duration_min=30)
    friday.c("edit", id=task, title="New title", notes="bring the charger", importance=3)
    got = item(friday, task)["item"]
    assert (got["title"], got["notes"], got["importance"]) == ("New title", "bring the charger", 3)
    assert [i["title"] for i in friday.q("items", text="New title")] == ["New title"]
    assert friday.q("items", text="Old title") == []


def test_no_due_date_takes_its_deadline_away_too(friday: Friday) -> None:
    task = add(friday, "Problem set 3", duration_min=90, due=f"{day(3)}T17:00", firmness="hard")
    assert listed(friday, task)["firmness"] == "hard"
    out = friday.c("edit", id=task, due=None)["item"]
    assert (out["due"], out["firmness"]) == (None, "none")
    out = friday.c("edit", id=task, due=f"{day(4)}T12:00")["item"]
    assert out["due"] == f"{day(4)}T12:00"


def test_an_event_moved_is_drawn_at_its_new_time(friday: Friday) -> None:
    d = day(2)
    talk = add(friday, "Career talk", when="fixed", start=f"{d}T15:00", end=f"{d}T16:00")
    friday.c("edit", id=talk, start=f"{d}T17:00", end=f"{d}T18:30")
    fixed = {f["id"]: f for f in friday.q("plan", start=f"{d}T00:00", end=f"{d}T23:59")["fixed"]}
    assert (fixed[talk]["start"], fixed[talk]["end"]) == (f"{d}T17:00", f"{d}T18:30")
    settled(friday)
    on_that_day = [b for b in friday.q("plan", start=f"{d}T00:00", end=f"{d}T23:59")["blocks"] if not b["fixed"]]
    assert not [b for b in on_that_day if b["start"] < f"{d}T18:30" and b["end"] > f"{d}T17:00"]


def test_a_projects_new_tag_goes_to_its_steps(friday: Friday) -> None:
    friday.c("area_add", name="History")
    friday.c("area_add", name="Art")
    friday.c("area_add", name="Design")
    project = add(friday, "Museum report", preset="Project", area="History")
    step = add(friday, "Visit the museum", duration_min=60, parent_id=project)
    own = add(friday, "Sketch the hall", duration_min=30, parent_id=project, area="Design")
    friday.c("edit", id=project, area="Art")
    assert listed(friday, step)["area"] == "Art"  # had the project's tag: follows
    assert listed(friday, own)["area"] == "Design"  # tagged otherwise: keeps its own
    friday.c("edit", id=project, area="History")
    assert listed(friday, step)["area"] == "History"
    assert listed(friday, own)["area"] == "Design"


def test_edit_refuses_what_isnt_there_and_from_date_on_what_doesnt_repeat(friday: Friday) -> None:
    task = add(friday, "One-off", duration_min=30)
    said = refused(friday, "edit", id=task, from_date=day(1), title="x")
    assert said["field"] == "from_date" and "doesn't repeat" in said["message"]
    refused(friday, "edit", id=999999, title="nothing")
    assert listed(friday, task)["title"] == "One-off"  # refused: unchanged


# done, drop, reopen


def test_done_then_reopen_plans_it_again(friday: Friday) -> None:
    task = add(friday, "Read paper", duration_min=60, due=f"{day(4)}T17:00")
    settled(friday)
    assert planned_min(friday, task) >= 60
    friday.c("done", id=task)
    assert listed(friday, task, "done")["status"] == "done"
    assert task not in {i["id"] for i in friday.q("items")}  # todo only by default
    settled(friday)
    assert planned_min(friday, task) == 0
    out = friday.c("reopen", id=task)["item"]
    assert out["status"] == "todo"
    assert listed(friday, task, "todo")["status"] == "todo"
    settled(friday)
    assert planned_min(friday, task) >= 60


def test_a_dropped_one_reopened_is_back_and_done_refuses_it_while_dropped(friday: Friday) -> None:
    task = add(friday, "Call the bank", duration_min=15)
    friday.c("drop", id=task)
    assert listed(friday, task)["status"] == "dropped"
    said = refused(friday, "done", id=task)
    assert "dropped" in said["message"]
    friday.c("reopen", id=task)
    assert listed(friday, task)["status"] == "todo"
    friday.c("done", id=task)
    assert "done already" in refused(friday, "done", id=task)["message"]


def test_reopening_a_step_of_a_finished_project_opens_the_project(friday: Friday) -> None:
    project = add(friday, "Lab project", preset="Project")
    one = add(friday, "Collect data", duration_min=30, parent_id=project)
    two = add(friday, "Write it up", duration_min=30, parent_id=project)
    friday.c("done", id=one)
    friday.c("done", id=two)
    assert listed(friday, project)["status"] == "done"  # its last step done: the project too
    friday.c("reopen", id=two)
    assert listed(friday, two)["status"] == "todo" and listed(friday, project)["status"] == "todo"
    assert listed(friday, one)["status"] == "done"


def test_the_time_it_took_is_kept_and_reopen_takes_the_completion_back(friday: Friday) -> None:
    task = add(friday, "Quiz review", duration_min=45)
    friday.c("done", id=task, actual_min=50)
    assert "actual_min" in str(refused(friday, "done", id=add(friday, "x", duration_min=5), actual_min=-1))
    friday.c("reopen", id=task)
    friday.c("done", id=task)  # a completion again, not refused as done twice
    assert listed(friday, task)["status"] == "done"


# depend, undepend


def test_a_wait_orders_the_plan_and_undepend_lets_it_go(friday: Friday) -> None:
    first = add(friday, "Outline", duration_min=60, due=f"{day(6)}T17:00")
    then = add(friday, "Draft", duration_min=60, due=f"{day(6)}T17:00")
    said = friday.c("depend", item_id=then, depends_on_id=first)["message"]
    assert said == f"T{then} waits for T{first}"
    assert listed(friday, then)["waiting_on"] == [first]
    assert item(friday, then)["depends_on"] == [{"depends_on_id": first, "fraction": 1.0, "lag_min": 0}]
    settled(friday)
    outline_end = max(b["end"] for b in item(friday, first)["blocks"])
    assert min(b["start"] for b in item(friday, then)["blocks"]) >= outline_end

    said = friday.c("undepend", item_id=then, depends_on_id=first)["message"]
    assert said == f"T{then} no longer waits for T{first}"
    assert listed(friday, then)["waiting_on"] == [] and item(friday, then)["depends_on"] == []
    said = refused(friday, "undepend", item_id=then, depends_on_id=first)
    assert (said["field"], said["message"]) == ("depends_on_id", f"depends_on_id: T{then} doesn't wait for T{first}")


def test_a_wait_said_again_replaces_its_fraction_and_a_loop_is_refused(friday: Friday) -> None:
    a = add(friday, "Read A", duration_min=60)
    b = add(friday, "Notes on A", duration_min=30)
    friday.c("depend", item_id=b, depends_on_id=a, fraction=0.5)
    friday.c("depend", item_id=b, depends_on_id=a, fraction=0.75, lag_min=30)
    assert item(friday, b)["depends_on"] == [{"depends_on_id": a, "fraction": 0.75, "lag_min": 30}]
    assert "a loop" in refused(friday, "depend", item_id=a, depends_on_id=b)["message"]
    assert "wait for itself" in refused(friday, "depend", item_id=a, depends_on_id=a)["message"]
    assert refused(friday, "depend", item_id=b, depends_on_id=a, fraction=0)["field"] == "fraction"
    friday.c("undepend", item_id=b, depends_on_id=a)
    friday.c("depend", item_id=a, depends_on_id=b)  # the loop's gone with it: now it may
    assert listed(friday, a)["waiting_on"] == [b]


def test_a_wait_on_something_finished_doesnt_hold_it(friday: Friday) -> None:
    a = add(friday, "Buy the book", duration_min=30)
    b = add(friday, "Read the book", duration_min=60)
    friday.c("depend", item_id=b, depends_on_id=a)
    assert listed(friday, b)["waiting_on"] == [a]
    friday.c("done", id=a)
    assert listed(friday, b)["waiting_on"] == []  # unfinished ones only
    friday.c("reopen", id=a)
    assert listed(friday, b)["waiting_on"] == [a]


# area_add, area_edit (and the areas list)


def test_a_tag_renamed_renames_its_items_and_the_rules_that_name_it(friday: Friday) -> None:
    chem = friday.c("area_add", name="Chem", color="green")
    assert {"name": "Chem", "color": "green", "archived": False}.items() <= chem.items()
    task = add(friday, "Titration lab", duration_min=60, area="Chem")
    rules = friday.q("settings")["rules"]
    rules.append({"type": "time_preference", "name": "you:chem mornings", "weight": 2, "scope": {"area": "Chem"},
                  "params": {"start": "08:00", "end": "12:00"}})  # fmt: skip
    friday.c("settings_set", key="rules", value=rules)
    out = friday.c("area_edit", id=chem["id"], name="Chemistry")
    assert (out["name"], out["color"]) == ("Chemistry", "green")
    assert listed(friday, task)["area"] == "Chemistry"
    after = {r["name"]: r for r in friday.q("settings")["rules"]}
    assert after["you:chem mornings"]["scope"] == {"area": "Chemistry"}
    assert [a["name"] for a in friday.q("areas") if a["id"] == chem["id"]] == ["Chemistry"]
    assert [i["id"] for i in friday.q("items", area="chemistry")] == [task]


def test_a_tag_recolored_and_archived_reads_so_and_unarchived_again(friday: Friday) -> None:
    music = friday.c("area_add", name="Music")
    out = friday.c("area_edit", id=music["id"], color="purple")
    assert (out["color"], out["archived"]) == ("purple", False)
    friday.c("area_edit", id=music["id"], archived=True)
    found = next(a for a in friday.q("areas") if a["id"] == music["id"])
    assert (found["color"], found["archived"]) == ("purple", True)
    friday.c("area_edit", id=music["id"], archived=False)
    assert next(a for a in friday.q("areas") if a["id"] == music["id"])["archived"] is False


def test_area_add_and_edit_refuse_a_name_taken_or_blank_and_a_tag_not_there(friday: Friday) -> None:
    friday.c("area_add", name="Physics")
    bio = friday.c("area_add", name="Biology")
    assert "exists" in refused(friday, "area_add", name="physics")["message"]
    assert "give the tag a name" in refused(friday, "area_add", name="  ")["message"]
    assert "exists" in refused(friday, "area_edit", id=bio["id"], name="PHYSICS")["message"]
    assert "give the tag a name" in refused(friday, "area_edit", id=bio["id"], name="")["message"]
    assert refused(friday, "area_edit", id=999999, name="Nope")["field"] == "id"
    assert friday.c("area_edit", id=bio["id"], name="BIOLOGY")["name"] == "BIOLOGY"  # its own name, recased
    names = [a["name"] for a in friday.q("areas")]
    assert "BIOLOGY" in names and "Biology" not in names and names == sorted(names)


def test_add_refuses_no_title(friday: Friday) -> None:
    said = refused(friday, "add", title="   ", duration_min=30)
    assert said["field"] == "title"
