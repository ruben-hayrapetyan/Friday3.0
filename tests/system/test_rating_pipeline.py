"""Events, the whole pipeline (tests/features.toml: rating; 24 Nov, the user: "go through every single functionality
of the app and build an extensive test suite ... absolutely nothing can break without our tests flagging it"): a real
`fridayd serve` in its own folder, each of an event's choices sent over HTTP as the event's card sends it, and what
then follows read back through the plan, the item, the categories and Triage. Each test works on a day of its own so
the others' work doesn't crowd it."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("rating"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def settled(friday: Friday) -> None:
    """The plan has caught up with every change sent."""

    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, 600)  # a busy machine replans slowly


def event(friday: Friday, title: str, start: str, end: str, **more: object) -> int:
    return friday.c("add", title=title, when="fixed", start=start, end=end, **more)["item"]["id"]


def facts(friday: Friday, item_id: int) -> dict:
    return friday.q("item", id=item_id)["item"]


def blocks_of(friday: Friday, item_id: int) -> list[dict]:
    return friday.q("item", id=item_id)["blocks"]


def late_ids(friday: Friday) -> set[int]:
    return {i["item_id"] for i in friday.q("status")["late_items"]}


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


# event_choice: going, work through it, skip


def test_working_through_an_event_lets_work_into_its_time_and_going_keeps_it_out(friday: Friday) -> None:
    d = day(2)
    workshop = event(friday, "Design workshop", f"{d}T08:00", f"{d}T23:00")
    task = friday.c("add", title="Lab write-up", duration_min=120, firmness="hard", release=f"{d}T08:00",
                    due=f"{d}T20:00")["item"]["id"]  # fmt: skip
    settled(friday)
    assert task in late_ids(friday)  # the whole day is the workshop's: no room
    said = friday.c("event_choice", id=workshop, choice="through")["message"]
    assert said == "Working through Design workshop: Friday can plan work in its time"
    assert facts(friday, workshop)["left_out"] == "through"
    settled(friday)
    inside = [b for b in blocks_of(friday, task) if f"{d}T08:00" <= b["start"] and b["end"] <= f"{d}T20:00"]
    assert inside and task not in late_ids(friday)
    fixed = {f["id"]: f for f in friday.q("plan", start=f"{d}T00:00", end=f"{d}T23:59")["fixed"]}
    assert fixed[workshop]["left_out"] == "through"  # still drawn, as it is

    said = friday.c("event_choice", id=workshop, choice="going")["message"]
    assert said == "Going to Design workshop: work keeps off it"
    assert facts(friday, workshop)["left_out"] is None
    settled(friday)
    assert task in late_ids(friday)
    assert not [b for b in blocks_of(friday, task) if b["start"] < f"{d}T23:00" and b["end"] > f"{d}T08:00"]


def test_skipping_frees_its_time_and_says_skipped_not_through(friday: Friday) -> None:
    d = day(2)
    talk = event(friday, "Guest talk", f"{d}T07:30", f"{d}T08:00")
    said = friday.c("event_choice", id=talk, choice="skip")["message"]
    assert said == "Skipping Guest talk: its time is free"
    assert facts(friday, talk)["left_out"] == "skipped"
    friday.c("event_choice", id=talk, choice="through")
    assert facts(friday, talk)["left_out"] == "through"
    friday.c("event_choice", id=talk, choice="going")
    assert facts(friday, talk)["left_out"] is None


def test_a_free_event_is_worked_through_until_you_say_youre_going(friday: Friday) -> None:
    d = day(4)
    hours = event(friday, "Office hours", f"{d}T15:00", f"{d}T16:00", free=True)
    assert facts(friday, hours)["left_out"] == "free"
    friday.c("event_choice", id=hours, choice="going")
    assert facts(friday, hours)["left_out"] is None  # it takes your time now, in Friday only
    friday.c("event_choice", id=hours, choice="skip")
    assert facts(friday, hours)["left_out"] == "skipped"


def test_event_choice_refuses_a_task_and_a_choice_it_doesnt_have(friday: Friday) -> None:
    task = friday.c("add", title="Not an event", duration_min=30)["item"]["id"]
    assert "isn't an event" in refused(friday, "event_choice", id=task, choice="skip")["message"]
    lecture = event(friday, "Some lecture", f"{day(5)}T10:00", f"{day(5)}T11:00")
    assert "choice" in str(refused(friday, "event_choice", id=lecture, choice="maybe"))  # not one of the three
    refused(friday, "event_choice", id=999999, choice="skip")


# event_hold: an event whose time is for a task


def test_an_events_time_held_for_a_task_gets_that_task_and_letting_go_ends_it(friday: Friday) -> None:
    d = day(1)
    slot = event(friday, "A4dd", f"{d}T10:00", f"{d}T12:00")
    task = friday.c("add", title="CS A4 Design Doc", duration_min=60, due=f"{day(6)}T17:00")["item"]["id"]
    said = friday.c("event_hold", id=slot, task_id=task)["message"]
    assert said == "A4dd's time is for CS A4 Design Doc"
    assert facts(friday, slot)["holds"]["id"] == task
    settled(friday)
    held = friday.until(lambda: facts(friday, slot)["holds"].get("here"), 300)
    assert held[0] == f"{d}T10:00"  # from the event's start
    assert any(b["start"] == f"{d}T10:00" and b["end"] <= f"{d}T12:00" for b in blocks_of(friday, task))

    said = friday.c("event_hold", id=slot)["message"]
    assert said == "A4dd is an event like any other again"
    assert facts(friday, slot)["holds"] is None
    settled(friday)
    assert not [b for b in blocks_of(friday, task) if b["start"] < f"{d}T12:00" and b["end"] > f"{d}T10:00"]


def test_a_finished_task_holds_no_event_and_going_lets_go_of_a_hold(friday: Friday) -> None:
    d = day(3)
    slot = event(friday, "Reading slot", f"{d}T14:00", f"{d}T15:00")
    task = friday.c("add", title="Read chapter 9", duration_min=45)["item"]["id"]
    friday.c("event_hold", id=slot, task_id=task)
    friday.c("event_choice", id=slot, choice="going")  # going: its time isn't the task's any more
    assert facts(friday, slot)["holds"] is None
    friday.c("event_hold", id=slot, task_id=task)
    friday.c("done", id=task)
    assert facts(friday, slot)["holds"] is None  # done: nothing to hold its time for
    assert "isn't a task to do" in refused(friday, "event_hold", id=slot, task_id=task)["message"]


def test_event_hold_refuses_what_isnt_an_event_or_a_task(friday: Friday) -> None:
    d = day(5)
    one = event(friday, "Seminar", f"{d}T09:00", f"{d}T10:00")
    other = event(friday, "Another seminar", f"{d}T11:00", f"{d}T12:00")
    task = friday.c("add", title="Prep notes", duration_min=30)["item"]["id"]
    assert "isn't an event" in refused(friday, "event_hold", id=task, task_id=task)["message"]
    assert refused(friday, "event_hold", id=one, task_id=other)["field"] == "task_id"  # an event isn't a task
    assert facts(friday, one)["holds"] is None


# event_keep: going to an optional event this time


def test_an_optional_event_gives_its_time_to_work_until_you_keep_it(friday: Friday) -> None:
    d = day(3)
    event(friday, "Busy morning", f"{d}T07:30", f"{d}T13:00")
    event(friday, "Busy evening", f"{d}T18:00", f"{d}T23:30")
    gym = event(friday, "Gym with Sam", f"{d}T13:00", f"{d}T18:00")
    essay = friday.c("add", title="Short essay", duration_min=180, firmness="hard", release=f"{d}T07:30",
                     due=f"{d}T18:00")["item"]["id"]  # fmt: skip
    friday.c("event_optional", title="Gym with Sam", mode="optional")

    def gym_on_plan() -> dict:
        return {f["id"]: f for f in friday.q("plan", start=f"{d}T00:00", end=f"{d}T23:59")["fixed"]}[gym]

    settled(friday)
    assert friday.until(lambda: "Short essay" in (gym_on_plan()["gives_way_to"] or ""), 300), gym_on_plan()
    assert essay not in late_ids(friday)

    said = friday.c("event_keep", id=gym)["message"]
    assert said == "Going to Gym with Sam: work keeps off it"
    assert gym_on_plan()["going"] is True and gym_on_plan()["gives_way_to"] is None
    settled(friday)
    assert essay in late_ids(friday)  # no other room before 6pm

    said = friday.c("event_keep", id=gym, going=False)["message"]
    assert said == "Gym with Sam: Friday decides"
    settled(friday)
    given = friday.until(lambda: not gym_on_plan()["going"] and gym_on_plan()["gives_way_to"], 300)
    assert "Short essay" in given
    assert essay not in late_ids(friday)


def test_event_keep_refuses_an_item_that_isnt_there(friday: Friday) -> None:
    refused(friday, "event_keep", id=999999)


# event_category: your category for every event with its title


def test_a_category_you_choose_is_every_such_events_and_none_lets_friday_choose_again(friday: Friday) -> None:
    two = [{"name": "Social", "slug": "social", "color": "graphite", "pattern": "party"},
           {"name": "Study", "slug": "study", "color": "sapgreen", "pattern": "study group"}]  # fmt: skip
    friday.c("settings_set", key="categories", value={**friday.q("settings")["categories"], "categories": two})
    first = event(friday, "Board games night", f"{day(5)}T19:00", f"{day(5)}T21:00")
    assert facts(friday, first)["category_by"] != "you"
    said = friday.c("event_category", id=first, category="Social")["message"]
    assert said == "Board games night is Social now, and events like it follow"
    got = facts(friday, first)
    assert (got["category"], got["category_by"]) == ("Social", "you")
    second = event(friday, "Board games night", f"{day(6)}T19:00", f"{day(6)}T21:00")
    assert (facts(friday, second)["category"], facts(friday, second)["category_by"]) == ("Social", "you")

    friday.c("event_category", id=second, category="Study")  # by title: the first follows too
    assert facts(friday, first)["category"] == "Study"

    said = friday.c("event_category", id=first, category="")["message"]
    assert said == "Board games night has no category now"
    assert facts(friday, first)["category"] is None and facts(friday, second)["category"] is None

    said = friday.c("event_category", id=first)["message"]
    assert said == "Friday chooses Board games night's category again"
    assert facts(friday, first)["category_by"] != "you"


def test_a_category_your_words_find_and_merging_moves_it(friday: Friday) -> None:
    party = event(friday, "End of term party", f"{day(6)}T20:00", f"{day(6)}T23:00")
    assert facts(friday, party)["category"] == "Social"  # "party" is Social's word
    friday.c("category_merge", name="Social", into="Study")
    assert facts(friday, party)["category"] == "Study"
    assert [c["name"] for c in friday.q("settings")["categories"]["categories"]] == ["Study"]


def test_event_category_refuses_a_category_that_isnt_and_a_task(friday: Friday) -> None:
    gig = event(friday, "Open mic", f"{day(4)}T20:00", f"{day(4)}T21:00")
    said = refused(friday, "event_category", id=gig, category="Nonsense")
    assert (said["field"], said["message"]) == ("category", "category: there's no category called Nonsense")
    task = friday.c("add", title="Some task", duration_min=30)["item"]["id"]
    assert "isn't an event" in refused(friday, "event_category", id=task, category="Study")["message"]
    assert facts(friday, gig)["category_by"] != "you"


# event_going: you go to it, so Triage stops offering to skip it


def test_triage_offers_to_skip_an_event_until_you_say_you_go(friday: Friday) -> None:
    d = day(1)
    event(friday, "Salsa club", f"{d}T18:00", f"{d}T21:00")
    event(friday, "Busy afternoon", f"{d}T07:30", f"{d}T18:00")
    report = friday.c("add", title="Lab report", duration_min=180, firmness="hard", release=f"{d}T17:00",
                      due=f"{d}T21:00")["item"]["id"]  # fmt: skip
    settled(friday)
    assert report in late_ids(friday)
    offered = [o["skip_title"] for o in friday.q("triage")["options"]]
    assert "Salsa club" in offered
    said = friday.c("event_going", title="Salsa club")["message"]
    assert said == "Won't suggest skipping Salsa club"
    assert "Salsa club" not in [o["skip_title"] for o in friday.q("triage")["options"]]
    friday.c("event_going", title="salsa club ")  # said again, the same title: no change, no error
    assert "Salsa club" not in [o["skip_title"] for o in friday.q("triage")["options"]]


# 24 Nov: found by this test (ids and titles in one kv list, sorting them crashed); fixed with a list each
def test_going_to_a_free_event_and_saying_you_go_to_another_both_work(friday: Friday) -> None:
    d = day(5)
    free = event(friday, "Drop-in hours", f"{d}T13:00", f"{d}T14:00", free=True)
    friday.c("event_choice", id=free, choice="going")  # an id into `events_going`
    answer = friday.http.post("/api/c/event_going", json={"title": "Movie night"})  # a title into the same list
    assert answer.status_code == 200, answer.text
