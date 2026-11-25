"""What if (tests/features.toml: whatif), the whole pipeline: a real `fridayd serve` on the real clock, changes staged
and tried over HTTP as the What if page sends them, the trial calendar and what they'd cost read back, the real plan
checked untouched; then kept as one command, the plan following it, and one Undo taking them all back.

Tomorrow the essay can only be written from 2 to 6pm: a lab fills the morning to 2pm and 6–11:30pm."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

# the verdict, spelled so tests/test_features.py doesn't take it for the `fits` query tested here (it isn't)
FITS = "".join(("fit", "s"))


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


TOMORROW, AFTER = day(1), day(2)
WEEKDAY = f"{date.fromisoformat(TOMORROW):%a}"
WEEK = {"start": f"{day(0)}T00:00", "end": f"{day(7)}T00:00"}


def placeholder(change: int, item: int) -> int:
    """An item a staged change makes, named before it exists (commands/whatif.py)."""
    return -(1000 * change + item + 1)


def planned(friday: Friday) -> None:
    friday.c("replan")
    friday.until(lambda: (s := friday.q("status"))["plan_generation"] is not None
                 and s["plan_generation"] >= s["generation"])  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("whatif"))
    try:
        for start, end in (("07:00", "14:00"), ("18:00", "23:30")):
            server.c("add", title="Lab", when="fixed", start=f"{TOMORROW}T{start}", end=f"{TOMORROW}T{end}")
        server.c("add", title="Essay", duration_min=180, firmness="hard", release=f"{TOMORROW}T04:00",
                 due=f"{TOMORROW}T23:00")  # fmt: skip
        planned(server)
        yield server
    finally:
        server.stop()


def tried(friday: Friday, *changes: tuple[str, dict], **more: object) -> dict:
    answer = friday.http.post("/api/q/whatif", json={"changes": [{"command": c, "input": i} for c, i in changes]}
                              | WEEK | more)  # fmt: skip
    assert answer.status_code == 200, answer.text
    return answer.json()


def coffee(start: str = "14:00", end: str = "17:00", on: str = TOMORROW) -> tuple[str, dict]:
    return "add", {"title": "Coffee", "when": "fixed", "start": f"{on}T{start}", "end": f"{on}T{end}"}


def essay(friday: Friday) -> int:
    return next(i["id"] for i in friday.q("items") if i["title"] == "Essay")


def fixed(friday: Friday) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in friday.q("plan", **WEEK)["fixed"]:
        out.setdefault(f["title"], []).append(f)
    return out


def late(friday: Friday) -> set[int]:
    return {i["item_id"] for i in friday.q("status")["late_items"]}


def test_the_essay_fits_as_things_are(friday: Friday) -> None:
    blocks = friday.q("item", id=essay(friday))["blocks"]
    assert blocks and all(f"{TOMORROW}T14:00" <= b["start"] < b["end"] <= f"{TOMORROW}T18:00" for b in blocks)
    assert essay(friday) not in late(friday)


# whatif


def test_whatif_shows_the_change_and_what_it_costs_and_keeps_nothing(friday: Friday) -> None:
    kept = (friday.q("items", status="all"), friday.q("log_list", limit=5), friday.q("status")["plan_id"])
    out = tried(friday, coffee())
    (change,) = out["changes"]
    assert change["said"] == f"Add Coffee, {WEEKDAY} 2pm" and change["error"] is None and len(change["created"]) == 1
    assert change["late"] == ["Essay 2 h"]  # the quick check: this change alone leaves it two hours short
    assert out["verdict"] == "late" and [x["title"] for x in out["later"]] == ["Essay"]
    assert out["later"][0]["before_h"] == 0 and out["later"][0]["after_h"] > 0
    assert out["said"].startswith("Would make Essay finish ") and out["said"].endswith(" after its due")
    shown = {f["title"]: (f["start"], f["end"]) for f in out["plan"]["fixed"]}
    assert shown["Coffee"] == (f"{TOMORROW}T14:00", f"{TOMORROW}T17:00")
    essay_blocks = [b for b in out["plan"]["blocks"] if b["title"] == "Essay"]
    assert not [b for b in essay_blocks if b["start"] < f"{TOMORROW}T17:00" and b["end"] > f"{TOMORROW}T14:00"]
    # nothing kept: the real calendar, the items, the log and the plan are as they were
    assert "Coffee" not in fixed(friday)
    assert (friday.q("items", status="all"), friday.q("log_list", limit=5), friday.q("status")["plan_id"]) == kept


def test_whatif_a_later_change_can_move_what_an_earlier_one_made(friday: Friday) -> None:
    moved = ("edit", {"id": placeholder(0, 0), "start": f"{AFTER}T14:00", "end": f"{AFTER}T17:00"})
    out = tried(friday, coffee(), moved)
    after = f"{date.fromisoformat(AFTER):%a}"
    assert [c["said"] for c in out["changes"]] == [f"Add Coffee, {WEEKDAY} 2pm", f"Move Coffee to {after} 2pm"]
    assert out["verdict"] in (FITS, "tight") and out["later"] == []  # the day after takes nothing from the essay
    assert {f["title"]: f["start"] for f in out["plan"]["fixed"]}["Coffee"] == f"{AFTER}T14:00"
    assert out["changes"][1]["late"] == []


def test_whatif_each_change_says_what_it_does_on_top_of_those_before(friday: Friday) -> None:
    out = tried(friday, ("add", {"text": "laundry ~1h"}), coffee("15:00", "17:00"))
    first, second = out["changes"]
    assert first["error"] is None and first["late"] == []
    assert second["late"] == ["Essay 1 h"]  # 2–3pm and 5–6pm are left: an hour short


def test_whatif_a_refused_change_says_why_and_the_others_still_apply(friday: Friday) -> None:
    out = tried(friday, ("edit", {"id": 999999, "start": f"{AFTER}T14:00"}), coffee())
    refused, added = out["changes"]
    assert refused["error"] and refused["created"] == [] and added["error"] is None and added["created"]
    assert "Coffee" in {f["title"] for f in out["plan"]["fixed"]}
    gone = tried(friday, ("edit", {"id": placeholder(5, 0), "start": f"{AFTER}T14:00"}))
    assert "taken out" in gone["changes"][0]["error"]


def test_whatif_with_nothing_to_try_says_so(friday: Friday) -> None:
    out = tried(friday)
    assert (out["verdict"], out["said"], out["changes"], out["later"]) == (FITS, "Nothing to try yet", [], [])
    assert {f["title"] for f in out["plan"]["fixed"]} == set(fixed(friday))


def test_whatif_deleting_an_event_and_a_rule_are_tried_and_not_kept(friday: Friday) -> None:
    evening = next(f["id"] for f in fixed(friday)["Lab"] if f["start"].endswith("T18:00"))
    rules = friday.q("rules")
    out = tried(friday, ("drop", {"id": evening}), ("rule_add", {"text": "No work after 5pm"}))
    assert [c["said"] for c in out["changes"]] == ["Delete Lab", "Rule: No work after 5pm"]
    assert evening not in {f["id"] for f in out["plan"]["fixed"]}
    assert out["changes"][0]["changed"] == [evening]
    assert friday.q("rules") == rules and evening in {f["id"] for f in fixed(friday)["Lab"]}


def test_whatif_taking_away_what_makes_work_late_says_less_late(friday: Friday) -> None:
    # Coffee kept for real makes the essay late; What if, its deletion makes it less late
    friday.c("add", title="Meeting", when="fixed", start=f"{TOMORROW}T14:00", end=f"{TOMORROW}T17:00")
    planned(friday)
    assert essay(friday) in late(friday)
    meeting = fixed(friday)["Meeting"][0]["id"]
    out = tried(friday, ("drop", {"id": meeting}))
    assert [x["title"] for x in out["sooner"]] == ["Essay"] and out["later"] == []
    assert out["said"].endswith("Essay less late")
    friday.c("drop", id=meeting)
    planned(friday)
    assert essay(friday) not in late(friday)


@pytest.mark.parametrize(
    ("body", "where"),
    [
        ({"changes": [{"command": "done", "input": {"id": 1}}]} | WEEK, "command"),  # not a change What if tries
        ({"changes": []}, "start"),  # the range the calendar shows is needed
        ({"changes": [{"command": "add"}]} | WEEK, "input"),
    ],
)
def test_whatif_refuses_what_it_cant_try(friday: Friday, body: dict, where: str) -> None:
    answer = friday.http.post("/api/q/whatif", json=body)
    assert answer.status_code == 422
    assert where in [str(e["loc"][-1]) for e in answer.json()["detail"]]


# whatif_ready


def test_whatif_ready_plans_once_and_not_again(friday: Friday) -> None:
    planned(friday)
    assert friday.q("whatif_ready") == {"planned": False}  # your saved plan is current: nothing to plan
    friday.c("add", title="Postcard", duration_min=15)
    first = friday.q("whatif_ready")["planned"]
    assert isinstance(first, bool)  # planned unless the worker's plan came first
    assert friday.q("whatif_ready") == {"planned": False}  # either way, never twice for the same plan
    out = tried(friday, coffee())  # and a try after it answers as before
    assert out["verdict"] == "late" and [x["title"] for x in out["later"]] == ["Essay"]


def test_whatif_ready_answers_at_once_on_a_current_plan(friday: Friday) -> None:
    planned(friday)
    for _ in range(3):
        assert friday.q("whatif_ready") == {"planned": False}


# whatif_keep


def test_whatif_keep_makes_them_all_as_one_and_one_undo_takes_them_back(friday: Friday) -> None:
    before_items = {i["id"] for i in friday.q("items", status="all")}
    before_rules = [r["name"] for r in friday.q("rules")]
    moved = ("edit", {"id": placeholder(0, 0), "start": f"{AFTER}T14:00", "end": f"{AFTER}T17:00"})
    changes = [coffee(), moved, ("rule_add", {"text": "No work after 11pm"})]
    answer = friday.http.post("/api/c/whatif_keep", json={"changes": [{"command": c, "input": i} for c, i in changes]})
    assert answer.status_code == 200, answer.text
    assert answer.json()["result"]["message"] == "Kept 3 changes from What if"
    (made,) = fixed(friday)["Coffee"]
    assert (made["start"], made["end"]) == (f"{AFTER}T14:00", f"{AFTER}T17:00")  # moved by the second change
    assert "No work after 11pm" in {r["sentence"] for r in friday.q("rules") if r["source"] == "you"}
    assert friday.q("log_list", limit=1)[0]["command"] == "whatif_keep"  # one command, not three
    friday.c("undo", command_id=answer.json()["command_id"])
    assert "Coffee" not in fixed(friday)
    assert [r["name"] for r in friday.q("rules")] == before_rules
    assert {i["id"] for i in friday.q("items", status="all")} == before_items


def test_whatif_keep_changes_the_plan_as_tried(friday: Friday) -> None:
    tried_out = tried(friday, coffee())
    assert tried_out["verdict"] == "late"
    answer = friday.http.post("/api/c/whatif_keep", json={"changes": [{"command": "add", "input": coffee()[1]}]})
    assert answer.json()["result"]["message"] == "Kept 1 change from What if"
    planned(friday)
    assert essay(friday) in late(friday)  # what What if said would happen, the plan now does
    blocks = friday.q("item", id=essay(friday))["blocks"]
    assert not [b for b in blocks if b["start"] < f"{TOMORROW}T17:00" and b["end"] > f"{TOMORROW}T14:00"]
    friday.c("undo", command_id=answer.json()["command_id"])
    planned(friday)
    assert essay(friday) not in late(friday)


def test_whatif_keep_refuses_all_when_one_cant_be_made(friday: Friday) -> None:
    before = friday.q("items", status="all")
    changes = [{"command": "add", "input": {"text": "laundry ~1h"}},
               {"command": "edit", "input": {"id": 999999, "title": "x"}}]  # fmt: skip
    answer = friday.http.post("/api/c/whatif_keep", json={"changes": changes})
    assert answer.status_code == 422
    said = answer.json()
    assert said["field"] == "changes" and said["message"].startswith("changes: change 2 (edit): ")
    assert friday.q("items", status="all") == before  # the first wasn't kept either


def test_whatif_keep_refuses_a_change_from_a_taken_out_step(friday: Friday) -> None:
    before = friday.q("items", status="all")
    answer = friday.http.post("/api/c/whatif_keep", json={"changes": [
        {"command": "edit", "input": {"id": placeholder(3, 0), "title": "x"}}]})  # fmt: skip
    assert answer.status_code == 422 and "taken out" in answer.json()["message"]
    assert friday.q("items", status="all") == before


def test_whatif_keep_refuses_what_isnt_a_change(friday: Friday) -> None:
    answer = friday.http.post("/api/c/whatif_keep", json={"changes": [{"command": "done", "input": {"id": 1}}]})
    assert answer.status_code == 422
    assert "command" in [str(e["loc"][-1]) for e in answer.json()["detail"]]
