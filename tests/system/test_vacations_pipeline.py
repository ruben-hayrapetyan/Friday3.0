"""Breaks (tests/features.toml: vacations), the whole pipeline: a real `fridayd serve` on the real clock, each break
command sent over HTTP as Settings → Breaks, a break day's list and the Inbox send them, and what follows read back
the same way: the calendar's days on a break, repeating events paused in the plan, Off days with no work and Light
days with about their time, a break day's list and ticking things off it, and breaks suggested from your calendar.

Each test uses days of its own, counted from today, so the breaks never overlap one another."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import Friday, zone_for_hour

# about noon now (25 Nov): before the 4am day start the plan reaches a day less far, and these tests' break days fall at
# its end (tests/commands/test_horizon_before_day_start.py, kept failing: the user held the change back)
TZ = zone_for_hour(12)


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("vacations"))
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"timezone": TZ})
    yield server
    server.stop()


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


def said(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%a}, {d:%b} {d.day}"


def planned(friday: Friday) -> None:
    friday.c("replan")
    friday.until(lambda: (s := friday.q("status"))["plan_generation"] is not None
                 and s["plan_generation"] >= s["generation"])  # fmt: skip


def blocks_on(friday: Friday, iso: str, item_id: int | None = None) -> list[dict]:
    nxt = (date.fromisoformat(iso) + timedelta(days=1)).isoformat()
    found = friday.q("plan", start=f"{iso}T04:00", end=f"{nxt}T04:00")["blocks"]
    return [b for b in found if item_id is None or b["item_id"] == item_id]


def minutes(blocks: list[dict]) -> int:
    span = lambda b: datetime.fromisoformat(b["end"][:16]) - datetime.fromisoformat(b["start"][:16])  # noqa: E731
    return sum(int(span(b).total_seconds() // 60) for b in blocks)


def breaks(friday: Friday) -> dict[int, dict]:
    return {v["id"]: v for v in friday.q("vacations")["vacations"]}


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def status(friday: Friday) -> dict:
    return friday.q("status")


def task(friday: Friday, title: str, length: int, release: str, due: str) -> int:
    return friday.c("add", title=title, duration_min=length, release=release, due=due, firmness="hard")["item"]["id"]


# vacations, vacation_add


def test_vacations_is_empty_on_a_new_friday(friday: Friday) -> None:
    assert friday.q("vacations") == {"vacations": []}


def test_vacation_add_keeps_your_defaults_and_the_calendar_marks_its_days(friday: Friday) -> None:
    first, last = day(20), day(22)
    out = friday.c("vacation_add", name="Fall break", start=first, end=last)
    made = out["vacation"]
    assert out["message"] == f"Fall break added, {said(first)} – {said(last)}"
    assert (made["name"], made["start"], made["end"], made["days"], made["mode"]) == (
        "Fall break",
        first,
        last,
        3,
        "light",
    )
    assert (made["work_min"], made["plan_meals"], made["plan_repeating"], made["keep_sleep"]) == (
        120,
        False,
        False,
        False,
    )
    assert made["pause"]["repeating"] == "all" and made["own"] == []
    assert breaks(friday)[made["id"]] == made
    days = {d["date"]: d["vacation"] for d in friday.q("calendar", start=day(19), days=5)["days"]}
    assert days[day(19)] is None and days[day(23)] is None
    assert [days[day(n)]["day_n"] for n in (20, 21, 22)] == [1, 2, 3]
    assert {days[day(n)]["name"] for n in (20, 21, 22)} == {"Fall break"}


def test_vacation_add_with_no_name_is_a_break_and_what_it_sets_itself_is_its_own(friday: Friday) -> None:
    made = friday.c("vacation_add", name="  ", start=day(25), end=day(26), mode="off", work_min=60, plan_meals=True)
    v = made["vacation"]
    assert (v["name"], v["mode"], v["work_min"], v["plan_meals"]) == ("Break", "off", 60, True)
    assert v["own"] == ["plan_meals", "work_min"]  # the rest follows your defaults


def test_vacation_add_follows_your_defaults_when_they_change(friday: Friday) -> None:
    made = friday.c("vacation_add", name="Default follower", start=day(50), end=day(50))["vacation"]
    friday.c("settings_set", key="breaks", value={**friday.q("settings")["breaks"], "work_min": 45})
    assert breaks(friday)[made["id"]]["work_min"] == 45
    friday.c("settings_set", key="breaks", value={**friday.q("settings")["breaks"], "work_min": 120})


def test_vacation_add_refuses_one_that_ends_before_it_starts(friday: Friday) -> None:
    before = breaks(friday)
    said_ = refused(friday, "vacation_add", name="Oops", start=day(40), end=day(38))
    assert said_ == {"field": "end", "message": "end: a break ends on or after the day it starts"}
    assert breaks(friday) == before


def test_vacation_add_refuses_days_already_on_a_break_by_its_name(friday: Friday) -> None:
    before = breaks(friday)
    out = refused(friday, "vacation_add", name="Trip", start=day(22), end=day(24))
    assert out["field"] == "start"
    assert out["message"] == f"start: those days are already on Fall break ({said(day(20))} – {said(day(22))})"
    assert breaks(friday) == before


@pytest.mark.parametrize(
    ("more", "field"),
    [({"work_min": 10}, "work_min"), ({"work_min": 2000}, "work_min"), ({"mode": "holiday"}, "mode"),
     ({"name": "x" * 81}, "name"), ({"start": "next week"}, "start")],
)  # fmt: skip
def test_vacation_add_refuses_what_a_break_cant_be(friday: Friday, more: dict, field: str) -> None:
    answer = friday.http.post("/api/c/vacation_add", json={"start": day(44), "end": day(45)} | more)
    assert answer.status_code == 422
    assert [e["loc"][-1] for e in answer.json()["detail"]] == [field]
    assert all(v["start"] != day(44) for v in breaks(friday).values())


# the plan on a break: repeats paused, Off and Light days


def test_a_break_pauses_a_repeating_event_and_deleting_it_brings_it_back(friday: Friday) -> None:
    friday.c("add", title="Shift", when="fixed", start=f"{day(1)}T10:00", end=f"{day(1)}T16:00", every="day")
    made = friday.c("vacation_add", name="Shift break", start=day(2), end=day(3))["vacation"]

    def shift(iso: str) -> tuple[int, list[int], dict]:
        nxt = (date.fromisoformat(iso) + timedelta(days=1)).isoformat()
        plan = friday.q("plan", start=f"{iso}T04:00", end=f"{nxt}T04:00")
        event = next(f for f in plan["fixed"] if f["title"] == "Shift")
        return event["id"], plan["paused"], event

    on, paused, event = shift(day(2))
    assert on in paused and event["left_out"] == "paused"
    before, paused, event = shift(day(1))
    assert before not in paused and event.get("left_out") != "paused"  # the day before the break: as usual
    assert friday.c("vacation_delete", id=made["id"])["message"] == "Shift break deleted"
    on, paused, event = shift(day(2))
    assert on not in paused and event.get("left_out") != "paused"
    # a break that keeps the repeat leaves it be
    series = next(r["id"] for r in friday.q("series_list") if r["title"] == "Shift")
    kept = friday.c("vacation_add", name="Shift kept", start=day(2), end=day(3),
                    pause={"repeating": "all", "series_kept": [series]})["vacation"]  # fmt: skip
    on, paused, _ = shift(day(2))
    assert on not in paused
    friday.c("vacation_delete", id=kept["id"])
    friday.c("series_delete", id=series)  # the other tests' days without six hours of shift


def test_an_off_break_plans_no_work_and_work_due_inside_is_done_before(friday: Friday) -> None:
    friday.c("vacation_add", name="Off days", start=day(5), end=day(6), mode="off")
    report = task(friday, "Off report", 180, f"{day(1)}T04:00", f"{day(6)}T17:00")
    planned(friday)
    assert blocks_on(friday, day(5)) == [] and blocks_on(friday, day(6)) == []
    blocks = friday.q("item", id=report)["blocks"]
    assert minutes(blocks) == 180 and all(b["end"] <= f"{day(5)}T04:00" for b in blocks)
    assert report not in {i["item_id"] for i in status(friday)["late_items"]}


def test_a_light_break_keeps_a_day_to_about_its_time(friday: Friday) -> None:
    friday.c("vacation_add", name="Light days", start=day(8), end=day(9), work_min=60)
    for n in range(6):
        task(friday, f"light reading {n}", 60, f"{day(8)}T04:00", f"{day(9)}T23:00")
    planned(friday)
    assert 0 < minutes(blocks_on(friday, day(8))) <= 60
    assert 0 < minutes(blocks_on(friday, day(9))) <= 60


# vacation_day, vacation_tick


@pytest.fixture(scope="module")
def listed(friday: Friday) -> dict[str, int]:
    """A Light break on days 11 and 12 with a small thing on the first and a big one over both."""
    friday.c("vacation_add", name="List break", start=day(11), end=day(12))
    rent = task(friday, "Pay rent", 15, f"{day(11)}T04:00", f"{day(11)}T23:00")
    big = task(friday, "Long reading", 360, f"{day(11)}T04:00", f"{day(12)}T23:00")
    planned(friday)
    return {"rent": rent, "big": big}


def things(friday: Friday, iso: str) -> dict[int, dict]:
    return {t["item_id"]: t for t in friday.q("vacation_day", date=iso)["items"]}


def test_vacation_day_lists_things_by_name_without_times(friday: Friday, listed: dict[str, int]) -> None:
    out = friday.q("vacation_day", date=day(11))
    assert out["date"] == day(11) and out["vacation"]["name"] == "List break"
    assert (out["vacation"]["day_n"], out["vacation"]["days"], out["vacation"]["mode"]) == (1, 2, "light")
    found = {t["item_id"]: t for t in out["items"]}
    assert {listed["rent"], listed["big"]} <= set(found)
    rent = found[listed["rent"]]
    assert (rent["title"], rent["ticked"], rent["done"], rent["timed_min"]) == ("Pay rent", False, False, 0)
    assert "start" not in rent and "end" not in rent
    # in the order planned: what the plan puts first comes first
    order = [b["item_id"] for b in blocks_on(friday, day(11))]
    assert [t["item_id"] for t in out["items"]] == list(dict.fromkeys(order))
    days = {d["date"]: d["vacation"] for d in friday.q("calendar", start=day(11), days=1)["days"]}
    assert (days[day(11)]["things"], days[day(11)]["ticked"]) == (len(out["items"]), 0)


def test_vacation_day_of_a_day_not_on_a_break_has_no_list(friday: Friday) -> None:
    assert friday.q("vacation_day", date=day(1)) == {"date": day(1), "vacation": None, "items": []}


def test_vacation_day_refuses_what_isnt_a_date(friday: Friday) -> None:
    assert friday.http.get("/api/q/vacation_day", params={"date": "someday"}).status_code == 422


def test_vacation_tick_finishes_a_small_thing_and_unticking_opens_it(friday: Friday, listed: dict[str, int]) -> None:
    rent = listed["rent"]
    out = friday.c("vacation_tick", date=day(11), item_id=rent)
    assert out["message"] == "Pay rent done"
    assert friday.q("item", id=rent)["item"]["status"] == "done"
    row = things(friday, day(11))[rent]
    assert row["ticked"] is True and row["done"] is True  # still listed, ticked
    days = {d["date"]: d["vacation"] for d in friday.q("calendar", start=day(11), days=1)["days"]}
    assert days[day(11)]["ticked"] == 1
    assert friday.c("vacation_tick", date=day(11), item_id=rent)["message"] == "Pay rent is ticked already"
    assert friday.c("vacation_tick", date=day(11), item_id=rent, ticked=False)["message"] == "Pay rent back on the list"
    assert friday.q("item", id=rent)["item"]["status"] == "todo"
    assert things(friday, day(11))[rent]["ticked"] is False
    again = friday.c("vacation_tick", date=day(11), item_id=rent, ticked=False)
    assert again["message"] == "Pay rent wasn't ticked"


def test_vacation_tick_of_a_bigger_thing_counts_the_days_share(friday: Friday, listed: dict[str, int]) -> None:
    big = listed["big"]
    share = minutes(blocks_on(friday, day(11), big))
    assert share > 0 and blocks_on(friday, day(12), big)  # some of it that day, more the next
    before = friday.q("item", id=big)["item"]["done_min"]
    out = friday.c("vacation_tick", date=day(11), item_id=big)
    assert out["message"] == "Long reading: today's part done"
    item = friday.q("item", id=big)["item"]
    assert item["status"] == "todo" and item["done_min"] == before + share
    assert things(friday, day(11))[big]["ticked"] is True
    friday.c("vacation_tick", date=day(11), item_id=big, ticked=False)
    assert friday.q("item", id=big)["item"]["done_min"] == before  # the share counted is taken back


def test_vacation_tick_refuses_a_day_not_on_a_break(friday: Friday, listed: dict[str, int]) -> None:
    out = refused(friday, "vacation_tick", date=day(1), item_id=listed["rent"])
    assert out == {"field": "date", "message": f"date: {said(day(1))} isn't on a break"}
    assert friday.q("item", id=listed["rent"])["item"]["status"] == "todo"


def test_vacation_tick_refuses_what_isnt_there_or_isnt_open(friday: Friday, listed: dict[str, int]) -> None:
    assert refused(friday, "vacation_tick", date=day(11), item_id=999999) == {
        "field": "item_id",
        "message": "item_id: no such task",
    }
    done = task(friday, "Already done", 15, f"{day(11)}T04:00", f"{day(11)}T23:00")
    friday.c("done", id=done)
    assert refused(friday, "vacation_tick", date=day(11), item_id=done) == {
        "field": "item_id",
        "message": "item_id: Already done isn't open",
    }


# vacation_edit, vacation_delete


def test_vacation_edit_changes_what_you_said_and_keeps_the_rest(friday: Friday) -> None:
    made = friday.c("vacation_add", name="Edit me", start=day(27), end=day(28), work_min=90)["vacation"]
    out = friday.c("vacation_edit", id=made["id"], mode="off", name="Edited")
    assert out["message"] == "Edited changed"
    v = breaks(friday)[made["id"]]
    assert (v["name"], v["mode"], v["start"], v["end"], v["work_min"]) == ("Edited", "off", day(27), day(28), 90)
    friday.c("vacation_edit", id=made["id"], end=day(29))
    assert (breaks(friday)[made["id"]]["end"], breaks(friday)[made["id"]]["days"]) == (day(29), 3)
    days = {d["date"]: d["vacation"] for d in friday.q("calendar", start=day(29), days=1)["days"]}
    assert days[day(29)]["name"] == "Edited" and days[day(29)]["day_n"] == 3


def test_vacation_edit_lets_a_break_follow_your_defaults_again(friday: Friday) -> None:
    made = friday.c("vacation_add", name="Own", start=day(31), end=day(31), work_min=30, keep_sleep=True)["vacation"]
    assert made["own"] == ["keep_sleep", "work_min"]
    friday.c("vacation_edit", id=made["id"], defaults=["work_min"])
    v = breaks(friday)[made["id"]]
    assert (v["work_min"], v["keep_sleep"], v["own"]) == (120, True, ["keep_sleep"])
    friday.c("vacation_edit", id=made["id"], name="")  # a blank name is a break
    assert breaks(friday)[made["id"]]["name"] == "Break"


def test_vacation_edit_refuses_moving_onto_another_break_or_ending_before_it_starts(friday: Friday) -> None:
    made = friday.c("vacation_add", name="Mover", start=day(35), end=day(36))["vacation"]
    out = refused(friday, "vacation_edit", id=made["id"], start=day(21))
    assert out["field"] == "start" and "Fall break" in out["message"]
    out = refused(friday, "vacation_edit", id=made["id"], end=day(34))
    assert out == {"field": "end", "message": "end: a break ends on or after the day it starts"}
    v = breaks(friday)[made["id"]]
    assert (v["start"], v["end"]) == (day(35), day(36))


def test_vacation_edit_and_delete_refuse_a_break_that_isnt_there(friday: Friday) -> None:
    assert refused(friday, "vacation_edit", id=999999, name="x") == {"field": "id", "message": "id: no such break"}
    assert refused(friday, "vacation_delete", id=999999) == {"field": "id", "message": "id: no such break"}


def test_vacation_delete_takes_its_days_off_the_calendar_and_undo_brings_it_back(friday: Friday) -> None:
    made = friday.c("vacation_add", name="Gone", start=day(37), end=day(37))["vacation"]
    answer = friday.http.post("/api/c/vacation_delete", json={"id": made["id"]})
    assert answer.status_code == 200 and answer.json()["result"]["message"] == "Gone deleted"
    assert made["id"] not in breaks(friday)
    assert friday.q("calendar", start=day(37), days=1)["days"][0]["vacation"] is None
    assert friday.q("vacation_day", date=day(37))["vacation"] is None
    friday.c("undo", command_id=answer.json()["command_id"])
    assert breaks(friday)[made["id"]]["name"] == "Gone"
    assert friday.q("calendar", start=day(37), days=1)["days"][0]["vacation"]["name"] == "Gone"


# break_choices


def test_break_choices_offers_repeats_with_their_calendar_and_every_tag(friday: Friday) -> None:
    friday.c("add", title="Seminar", when="fixed", start=f"{day(1)}T12:00", end=f"{day(1)}T13:00", every="mon,wed")
    friday.c("add", title="Flight", when="fixed", start=f"{day(2)}T18:00", end=f"{day(2)}T20:00")
    friday.c("area_add", name="Work")
    found = friday.q("break_choices")
    titles = [s["title"] for s in found["series"]]
    assert "Seminar" in titles and "Flight" not in titles  # a one-off isn't a repeat
    seminar = next(s for s in found["series"] if s["title"] == "Seminar")
    assert seminar["calendar"] == "Friday" and seminar["every"]
    friday_calendar = next(c for c in found["calendars"] if c["name"] == "Friday")
    assert friday_calendar["repeats"] == len([s for s in found["series"] if s["calendar"] == "Friday"])
    assert "Work" in found["tags"]


def test_a_tag_chosen_from_break_choices_waits_until_after_the_break(friday: Friday) -> None:
    assert "Work" in friday.q("break_choices")["tags"]
    friday.c("vacation_add", name="Tag pause", start=day(3), end=day(3), pause={"repeating": "all", "tags": ["Work"]})
    slides = friday.c("add", title="Work slides", duration_min=60, area="Work", release=f"{day(3)}T04:00",
                      due=f"{day(4)}T23:00")["item"]["id"]  # fmt: skip
    planned(friday)
    assert blocks_on(friday, day(3), slides) == []
    assert minutes(blocks_on(friday, day(4), slides)) == 60  # the day after it, before its due


# break_suggestion


def suggested(friday: Friday) -> list[dict]:
    return [d for d in status(friday)["decisions"] if d["kind"] == "break"]


def test_an_all_day_vacation_event_is_suggested_and_taken(friday: Friday) -> None:
    first, end = day(40), day(43)  # all day from the 40th to the 43rd: the 40th to the 42nd
    friday.c("add", title="Vacation in Lisbon", when="fixed", start=f"{first}T00:00", end=f"{end}T00:00")
    (one,) = [d for d in suggested(friday) if d["start"] == first]
    assert (one["end"], one["name"], one["key"]) == (day(42), "Vacation in Lisbon", f"break:{first}:{day(42)}")
    assert one["title"] == f"Vacation in Lisbon, {said(first)} – {said(day(42))}: a break?"
    out = friday.c("break_suggestion", key=one["key"], take=True)
    assert out["message"] == f"Vacation in Lisbon added, {said(first)} – {said(day(42))}"
    (made,) = [v for v in breaks(friday).values() if v["start"] == first]
    assert (made["end"], made["name"], made["mode"]) == (day(42), "Vacation in Lisbon", "light")
    assert all(d["start"] != first for d in suggested(friday))  # taken: not asked again
    assert refused(friday, "break_suggestion", key=one["key"]) == {
        "field": "key",
        "message": "key: that break isn't suggested any more",
    }


def test_a_suggested_break_said_not_to_be_one_isnt_asked_again(friday: Friday) -> None:
    first = day(46)
    friday.c("add", title="Out of office", when="fixed", start=f"{first}T00:00", end=f"{day(47)}T00:00")
    (one,) = [d for d in suggested(friday) if d["start"] == first]
    out = friday.c("break_suggestion", key=one["key"], take=False)
    assert out["message"] == "Not a break: Friday won't ask about it again"
    assert all(d["start"] != first for d in suggested(friday))
    assert all(v["start"] != first for v in breaks(friday).values())


def test_an_ordinary_all_day_event_is_no_break(friday: Friday) -> None:
    friday.c("add", title="Remy's Birthday", when="fixed", start=f"{day(48)}T00:00", end=f"{day(49)}T00:00")
    assert all(d["start"] != day(48) for d in suggested(friday))


def test_break_suggestion_refuses_a_key_never_suggested(friday: Friday) -> None:
    before = breaks(friday)
    assert refused(friday, "break_suggestion", key="break:2020-01-01:2020-01-02")["field"] == "key"
    assert breaks(friday) == before
