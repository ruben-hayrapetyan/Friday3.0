"""Copies and the review of what came in, through the whole of Friday (tests/features.toml: checking; 24 Nov, the user:
"build an extensive test suite"): a real `fridayd serve`, the Mac app's post of its calendars over HTTP, the sync job
bringing their deadlines into the Inbox, and each command of Check sent as its page sends it; what you'd then see read
back the same way: the copies found, the one kept with the others' time, ties moved, the list to go over."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local

MAC = {"X-Friday-Client": "mac"}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("checking_pipeline"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def due(days: int, hour: int = 17) -> str:
    return local((datetime.now(ZoneInfo(TZ)) + timedelta(days=days)).replace(hour=hour, minute=0, second=0))


def add(friday: Friday, title: str, **fields: Any) -> int:
    fields = {"duration_min": 60, "due": due(5)} | fields
    return friday.c("add", title=title, **fields)["item"]["id"]


def groups(friday: Friday, key: str) -> list[dict]:
    return [g for g in friday.q("duplicates")["groups"] if g["key"] == key]


def item(friday: Friday, item_id: int) -> dict:
    return friday.q("item", id=item_id)


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def yesterday(hour: int) -> datetime:
    return datetime.now(ZoneInfo(TZ)).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=1)


# Copies


def test_copies_by_their_words_are_found_with_the_one_with_time_logged_kept(friday: Friday) -> None:
    first, second = add(friday, "Psych WA7 draft"), add(friday, "psych  WA7 Draft")
    add(friday, "Psych WA8 draft")  # another number: another task
    start = yesterday(10)
    friday.c("log", id=second, start=local(start), end=local(start + timedelta(minutes=30)))
    (group,) = groups(friday, "psych wa 7 draft")
    assert group["keep"] == second and [i["id"] for i in group["items"]] == [first, second]
    assert friday.q("duplicates")["sources"][str(second)] == "you"


def test_merging_keeps_one_with_the_others_time_and_undo_brings_it_back(friday: Friday) -> None:
    (group,) = groups(friday, "psych wa 7 draft")
    keep, drop = group["items"][0]["id"], group["keep"]  # keep the one without the time: it moves over
    answer = friday.http.post("/api/c/duplicates_merge", json={"groups": [{"keep": keep, "drop": [drop]}]})
    assert answer.status_code == 200, answer.text
    assert answer.json()["result"]["message"] == "Removed 1 copy; one of each kept"
    assert groups(friday, "psych wa 7 draft") == []
    assert item(friday, keep)["item"]["done_min"] == 30 and item(friday, drop)["item"]["status"] == "dropped"
    assert item(friday, drop)["item"]["done_min"] == 0
    friday.c("undo", command_id=answer.json()["command_id"])
    assert len(groups(friday, "psych wa 7 draft")) == 1
    assert item(friday, drop)["item"]["done_min"] == 30 and item(friday, drop)["item"]["status"] == "todo"


def test_several_groups_merge_at_once_and_the_count_is_said(friday: Friday) -> None:
    a = [add(friday, "Lab 4 prelab") for _ in range(3)]
    b = [add(friday, "Reading response 2") for _ in range(2)]
    said = friday.c("duplicates_merge", groups=[{"keep": a[0], "drop": a[1:]}, {"keep": b[1], "drop": [b[0]]}])
    assert said["message"] == "Removed 3 copies; one of each kept"
    assert [item(friday, i)["item"]["status"] for i in (*a, *b)] == ["todo", "dropped", "dropped", "dropped", "todo"]
    assert groups(friday, "lab 4 prelab") == [] and groups(friday, "reading response 2") == []


def test_a_copy_cant_be_both_kept_and_removed(friday: Friday) -> None:
    one, two = add(friday, "Essay outline"), add(friday, "essay outline")
    said = refused(friday, "duplicates_merge", groups=[{"keep": one, "drop": [one, two]}])
    assert said["field"] == "keep" and "can't be both kept and removed" in said["message"]
    assert {item(friday, i)["item"]["status"] for i in (one, two)} == {"todo"}  # nothing done
    assert len(groups(friday, "essay outline")) == 1
    assert refused(friday, "duplicates_merge", groups=[{"keep": one}])["detail"][0]["loc"][-1] == "drop"  # no list


def test_a_removed_copys_ties_move_to_the_kept_one_and_its_pin_goes(friday: Friday) -> None:
    kept, copy = add(friday, "Poster draft"), add(friday, "poster  draft")
    outline, final = add(friday, "Poster sketch"), add(friday, "Poster print", due=due(7))
    friday.c("depend", item_id=copy, depends_on_id=outline)
    friday.c("depend", item_id=final, depends_on_id=copy)
    tomorrow = (datetime.now(ZoneInfo(TZ)) + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    friday.c("pin", id=copy, start=local(tomorrow), end=local(tomorrow + timedelta(hours=1)))
    friday.c("duplicates_merge", groups=[{"keep": kept, "drop": [copy]}])
    assert [d["depends_on_id"] for d in item(friday, kept)["depends_on"]] == [outline]
    assert [d["depends_on_id"] for d in item(friday, final)["depends_on"]] == [kept]
    assert item(friday, copy)["depends_on"] == []
    assert not [b for b in friday.q("plan")["blocks"] if b["item_id"] == copy and b.get("pinned")]


def test_ones_you_say_arent_the_same_stop_being_asked_but_a_third_is_asked(friday: Friday) -> None:
    ids = [add(friday, "Weekly reading"), add(friday, "weekly reading")]
    assert friday.c("not_duplicates", ids=ids)["message"] == "Kept apart"
    assert groups(friday, "weekly reading") == []
    third = add(friday, "Weekly Reading")
    (group,) = groups(friday, "weekly reading")
    assert [i["id"] for i in group["items"]] == [*ids, third]
    assert {item(friday, i)["item"]["status"] for i in ids} == {"todo"}  # kept apart, not changed


def test_different_tags_or_dues_days_apart_arent_copies_but_one_with_neither_can_be(friday: Friday) -> None:
    friday.c("area_add", name="CHEM 2090")
    friday.c("area_add", name="MATH 1920")
    chem = add(friday, "HW 12", area="CHEM 2090", due=due(3))
    add(friday, "hw 12", area="MATH 1920", due=due(3))
    add(friday, "HW 12", area="CHEM 2090", due=due(6))  # its tag, three days later: the next one
    assert groups(friday, "homework 12") == []
    untagged = add(friday, "Hw 12", due=due(3, hour=9))
    (group,) = groups(friday, "homework 12")
    assert {i["id"] for i in group["items"]} == {chem, untagged}


def test_events_and_repeats_arent_copies(friday: Friday) -> None:
    start = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    for _ in range(2):
        friday.c("add", title="Office hours", when="fixed", start=local(start), end=local(start + timedelta(hours=1)))
    friday.c("series_add", title="Stretch", every="mon,tue,wed,thu,fri", duration_min=15)
    assert groups(friday, "office hours") == [] and groups(friday, "stretch") == []


def test_merging_something_not_there_is_refused_and_changes_nothing(friday: Friday) -> None:
    keep, copy = add(friday, "Unique thing"), add(friday, "unique thing")
    said = refused(friday, "duplicates_merge", groups=[{"keep": keep, "drop": [copy, 987_654]}])
    assert said["field"] == "id" and "T987654" in said["message"]
    assert {item(friday, i)["item"]["status"] for i in (keep, copy)} == {"todo"}  # one change: all of it or none
    assert len(groups(friday, "unique thing")) == 1


# Going over what came in


def mac_sync(friday: Friday, events: list[dict[str, Any]]) -> None:
    now = datetime.now(ZoneInfo(TZ))
    calendars = [{"id": "home", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}]
    body = {"calendars": calendars, "events": events, "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=body)
    assert answer.status_code == 200, answer.text


def deadline(eid: str, title: str, days: int) -> dict[str, Any]:
    at = (datetime.now(ZoneInfo(TZ)) + timedelta(days=days)).replace(hour=23, minute=59, second=0, microsecond=0)
    return {"id": eid, "calendar": "home", "title": title, "start": at.isoformat(), "end": at.isoformat()}


def waiting(friday: Friday, origins: set[str]) -> list[dict]:
    found = [s for s in friday.q("inbox")["suggestions"] if s["origin"] in origins]
    return found if len(found) == len(origins) else []


@pytest.fixture(scope="module")
def brought_in(friday: Friday) -> dict[str, int]:
    """Three deadlines from the Mac's Home calendar ("PS 3 due" read as the task PS 3), accepted from the Inbox, and
    one typed by hand: by title."""
    titles = {"PS 3", "PS 4", "Lab 2"}
    mac_sync(friday, [deadline("d3", "PS 3 due", 4), deadline("d4", "PS 4 due", 2), deadline("l2", "Lab 2 due", 6)])
    for s in friday.until(lambda: waiting(friday, {"PS 3 due", "PS 4 due", "Lab 2 due"})):
        assert s["source"] == "Home"
        friday.c("suggestion_accept", id=s["id"])
    found = {i["title"]: i["id"] for i in friday.q("items") if i["title"] in titles}
    assert set(found) == titles
    found["mine"] = add(friday, "Typed by hand", due=due(1))
    return found


def test_before_review_again_nothing_is_under_way(friday: Friday, brought_in: dict[str, int]) -> None:
    assert friday.q("to_review") == {"items": [], "sources": {}, "started": False}


def test_review_again_lists_what_came_from_calendars_soonest_due_first(friday: Friday, brought_in: dict) -> None:
    assert friday.c("review_again")["message"] == "3 tasks to go over"
    out = friday.q("to_review")
    assert [i["id"] for i in out["items"]] == [brought_in[t] for t in ("PS 4", "PS 3", "Lab 2")]
    assert brought_in["mine"] not in {i["id"] for i in out["items"]}  # what you typed isn't gone over
    assert set(out["sources"].values()) == {"Home"} and out["started"] is True


def test_reviewed_kept_leaves_the_list_and_stays_planned(friday: Friday, brought_in: dict[str, int]) -> None:
    said = friday.c("reviewed", ids=[brought_in["PS 4"]])
    assert said["message"] == "Kept 1 task"
    ids = [i["id"] for i in friday.q("to_review")["items"]]
    assert ids == [brought_in["PS 3"], brought_in["Lab 2"]]
    assert item(friday, brought_in["PS 4"])["item"]["status"] == "todo"


def test_reviewed_removed_takes_them_off_your_list(friday: Friday, brought_in: dict[str, int]) -> None:
    gone = [brought_in["PS 3"], brought_in["Lab 2"]]
    assert friday.c("reviewed", ids=gone, keep=False)["message"] == "Removed 2 tasks"
    assert {item(friday, i)["item"]["status"] for i in gone} == {"dropped"}
    assert friday.q("to_review") == {"items": [], "sources": {}, "started": False}
    assert not {i["id"] for i in friday.q("items")} & set(gone)


def test_review_again_once_more_lists_only_whats_still_open(friday: Friday, brought_in: dict[str, int]) -> None:
    assert friday.c("review_again")["message"] == "1 task to go over"
    assert [i["id"] for i in friday.q("to_review")["items"]] == [brought_in["PS 4"]]
    friday.c("done", id=brought_in["PS 4"])  # finished meanwhile: not to go over any more
    assert friday.q("to_review")["items"] == [] and friday.q("to_review")["started"] is False
    assert friday.c("review_again")["message"] == "0 tasks to go over"


def test_reviewed_needs_its_ids(friday: Friday, brought_in: dict[str, int]) -> None:
    assert refused(friday, "reviewed", keep=False)
    assert refused(friday, "not_duplicates", ids="all")
