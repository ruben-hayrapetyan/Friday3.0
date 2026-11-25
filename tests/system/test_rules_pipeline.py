"""Rules in your words (tests/features.toml: rules), the whole pipeline: a real `fridayd serve`, each rule command sent
over HTTP as the Rules page and the Inbox send it, and what follows read back the same way: a sentence read before
it's saved (and nothing saved), a rule deleted (and the plan without it), what a bent rule clashes with, the night's
clashes in the Inbox, and your answer to "Which should win?"."""

import json
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from friday.commands.rules import find_clashes
from friday.core.db import connect
from tests.system.test_beat_plan_system import TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("rules"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def heavy(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    """Sixty hours due in five days: the plan has to bend rules (a day's limit, fewer longer sessions) every day."""
    server = Friday(tmp_path_factory.mktemp("rules-heavy"))
    try:
        due = (datetime.now(ZoneInfo(TZ)) + timedelta(days=5)).strftime("%Y-%m-%dT23:59")
        for n in range(12):
            server.c("add", title=f"problem set {n}", duration_min=300, due=due)
        planned(server)
        yield server
    finally:
        server.stop()


def planned(friday: Friday) -> None:
    """The worker's plan has caught up with every change so far."""
    friday.c("replan")
    friday.until(lambda: (s := friday.q("status"))["plan_generation"] is not None
                 and s["plan_generation"] >= s["generation"])  # fmt: skip


def rules(friday: Friday) -> dict[str, dict]:
    return {r["name"]: r for r in friday.q("rules")}


def mine(friday: Friday) -> dict[str, str]:
    """Your own rules: sentence → name."""
    return {r["sentence"]: r["name"] for r in friday.q("rules") if r["source"] == "you"}


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


def minutes(blocks: list[dict]) -> int:
    span = lambda b: datetime.fromisoformat(b["end"][:16]) - datetime.fromisoformat(b["start"][:16])  # noqa: E731
    return sum(int(span(b).total_seconds() // 60) for b in blocks)


def refused(friday: Friday, verb: str, query: bool = False, **body: object) -> dict:
    answer = friday.http.get(f"/api/q/{verb}", params=body) if query else friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


# rule_read: a sentence read as a rule, nothing saved


def test_rule_read_reads_a_sentence_and_saves_nothing(friday: Friday) -> None:
    before = friday.q("rules")
    out = friday.q("rule_read", text="no work after 9pm")
    assert (out["sentence"], out["strength"], out["effect"]) == (
        "No work after 9pm",
        "Prefer",
        "Friday avoids those hours",
    )
    assert out["reading"]["kind"] == "window" and out["reading"]["at"] == "21:00"
    assert out["conflicts"] == [] and out["also"] == [] and out["starts_over"] is False
    assert friday.q("rules") == before  # only read, never added
    assert all(e["command"] != "rule_add" for e in friday.q("log_list", limit=20))


def test_rule_read_says_must_as_always(friday: Friday) -> None:
    assert friday.q("rule_read", text="I must not work after 10pm")["strength"] == "Always"


def test_rule_read_of_something_that_isnt_a_rule_says_so(friday: Friday) -> None:
    out = friday.q("rule_read", text="make me a sandwich")
    assert out["reading"] is None and out["sentence"] == ""
    assert out["effect"] == "Friday can’t read that as a rule yet."


def test_rule_read_with_your_own_fields_overrides_the_words(friday: Friday) -> None:
    out = friday.q("rule_read", text="I prefer eating lunch before 1pm", overrides='{"at": "12:30", "days": ["sat"]}')
    assert out["sentence"] == "Lunch before 12:30pm on Sat"
    assert out["reading"]["days"] == ["sat"]


def test_rule_read_of_several_stretches_is_a_rule_for_each(friday: Friday) -> None:
    out = friday.q("rule_read", text="no work 7:10-7:20 and 7:30-7:40")
    assert [out["sentence"], *(a["sentence"] for a in out["also"])] == [
        "No work between 7:10am and 7:20am",
        "No work between 7:30am and 7:40am",
    ]


def test_rule_read_refuses_fields_that_arent_json(friday: Friday) -> None:
    said = refused(friday, "rule_read", query=True, text="no work after 6pm", overrides="{at: 6}")
    assert said == {"field": "overrides", "message": "overrides: not JSON"}


def test_rule_read_names_the_rules_a_new_one_contradicts_but_not_the_one_being_edited(friday: Friday) -> None:
    friday.c("rule_add", text="deep work in the morning")
    name = mine(friday)["Deep work between 8am and 12pm"]
    (conflict,) = friday.q("rule_read", text="no work before noon")["conflicts"]
    assert conflict["other"] == name and conflict["other_sentence"] == "Deep work between 8am and 12pm"
    assert conflict["why"] == "together they leave no time for deep work"
    # editing that very rule: it isn't at odds with itself, and another kind of rule starts over in its place
    edited = friday.q("rule_read", text="no work before noon", editing=name)
    assert edited["conflicts"] == [] and edited["starts_over"] is True
    assert edited["replaces"] == "Deep work between 8am and 12pm"
    friday.c("rule_remove", name=name)


def test_rule_read_says_which_events_a_rule_about_events_finds(friday: Friday) -> None:
    text = "climbing club only if i'm ahead"
    assert "No event has those words in its title yet" in friday.q("rule_read", text=text)["effect"]
    start = f"{day(3)}T18:00"
    friday.c("add", title="Climbing Club", when="fixed", start=start, end=f"{day(3)}T20:00")
    assert "Matches Climbing Club" in friday.q("rule_read", text=text)["effect"]


# rule_remove: a rule deleted, and the plan without it


def test_rule_remove_deletes_your_rule_and_the_plan_follows(friday: Friday) -> None:
    friday.c("rule_add", text="no work after 6pm", strength="Always")
    name = mine(friday)["No work after 6pm"]
    tomorrow = day(1)
    task = friday.c("add", title="Evening reading", duration_min=120, firmness="hard", release=f"{tomorrow}T18:00",
                    due=f"{tomorrow}T23:00")["item"]["id"]  # fmt: skip
    planned(friday)
    assert task in {i["item_id"] for i in friday.q("status")["late_items"]}  # Always: no evening for it at all
    assert friday.c("rule_remove", name=name)["message"] == "Deleted"
    assert name not in rules(friday)
    assert name not in {r["name"] for r in friday.q("settings")["rules"]}
    planned(friday)
    assert task not in {i["item_id"] for i in friday.q("status")["late_items"]}  # the evening is open again
    blocks = friday.q("item", id=task)["blocks"]
    assert minutes(blocks) == 120 and all(
        f"{tomorrow}T18:00" <= b["start"] < b["end"] <= f"{tomorrow}T23:00" for b in blocks
    )


def test_rule_remove_of_a_built_in_rule_and_undo_brings_it_back(friday: Friday) -> None:
    order = list(rules(friday))
    answer = friday.http.post("/api/c/rule_remove", json={"name": "daily_load"})
    assert answer.status_code == 200, answer.text
    assert "daily_load" not in rules(friday)
    friday.c("undo", command_id=answer.json()["command_id"])
    assert list(rules(friday)) == order  # back, in its place


def test_rule_remove_refuses_the_deadline_rules(friday: Friday) -> None:
    for name in ("late_work", "late_tasks", "quota"):
        said = refused(friday, "rule_remove", name=name)
        assert said == {"field": "name", "message": "name: deadlines are what Friday plans around, so this rule stays"}
        assert name in rules(friday)


def test_rule_remove_refuses_a_rule_that_isnt_there(friday: Friday) -> None:
    before = list(rules(friday))
    assert refused(friday, "rule_remove", name="you:nothing") == {
        "field": "name",
        "message": "name: no rule named you:nothing",
    }
    assert list(rules(friday)) == before


# rule_win: "Which should win?"


def test_rule_win_says_which_wins_and_the_rules_page_shows_it(friday: Friday) -> None:
    said = friday.c("rule_win", winner="late_night", loser="chunk_cost")["message"]
    assert said == "“Wind down before bed” wins over “Fewer, longer sessions”"
    now = rules(friday)
    assert now["late_night"]["wins_over"] == ["chunk_cost"] and now["chunk_cost"]["gives_way_to"] == ["late_night"]


def test_rule_win_a_new_answer_for_the_same_two_replaces_the_old(friday: Friday) -> None:
    friday.c("rule_win", winner="late_night", loser="chunk_cost")
    friday.c("rule_win", winner="chunk_cost", loser="late_night")
    now = rules(friday)
    assert now["chunk_cost"]["wins_over"] == ["late_night"] and now["late_night"]["gives_way_to"] == ["chunk_cost"]
    assert now["late_night"]["wins_over"] == [] and now["chunk_cost"]["gives_way_to"] == []


def test_rule_win_answers_go_when_one_of_the_rules_is_deleted(friday: Friday) -> None:
    friday.c("rule_add", text="keep saturday mornings free")
    name = mine(friday)["Keep Sat 8am–12pm free"]
    friday.c("rule_win", winner=name, loser="deep_run")
    assert rules(friday)["deep_run"]["gives_way_to"] == [name]
    friday.c("rule_remove", name=name)
    assert rules(friday)["deep_run"]["gives_way_to"] == []
    friday.c("rule_add", text="keep saturday mornings free")  # added again: its old answer doesn't come back
    assert rules(friday)[mine(friday)["Keep Sat 8am–12pm free"]]["wins_over"] == []


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"winner": "late_night", "loser": "late_night"}, "loser", "a rule can't win over itself"),
        ({"winner": "nonsense", "loser": "late_night"}, "winner", "no rule named nonsense"),
        ({"winner": "late_night", "loser": "nonsense"}, "loser", "no rule named nonsense"),
        ({"winner": "late_work", "loser": "late_night"}, "winner", "late_work isn't a rule that can give way"),
    ],
)
def test_rule_win_refuses_what_cant_be_answered(friday: Friday, body: dict, field: str, message: str) -> None:
    before = rules(friday)["late_night"]
    assert refused(friday, "rule_win", **body) == {"field": field, "message": f"{field}: {message}"}
    after = rules(friday)["late_night"]
    assert (after["wins_over"], after["gives_way_to"]) == (before["wins_over"], before["gives_way_to"])


# rule_clash: what a bent rule is up against, planned afresh


def test_rule_clash_names_another_rule_on_the_days_it_bends(heavy: Friday) -> None:
    every = rules(heavy)
    bent = [n for n, r in every.items() if r["violated"] and n not in ("late_work", "late_tasks", "quota")]
    assert bent, "sixty hours in five days bends no rule"
    for name in bent:
        out = heavy.q("rule_clash", name=name)
        assert out["rule"] == name and out["sentence"] == every[name]["sentence"]
        if out["other"] is None:
            assert out["days"] == [] and out["said"] == ""
            continue
        assert out["other"] in every and out["other"] != name
        assert out["other_sentence"] == every[out["other"]]["sentence"]
        assert out["days"] and all(day(0) <= d <= day(14) for d in out["days"])
        assert f"clashes with “{out['other_sentence']}”: " in out["said"]
        assert out["said"].endswith(f"{out['because'][1:]}." + (" Which should win?" if out["ask"] else ""))
    # Whether a bent rule clashes with another depends on the hour it's planned at (24 Nov: none did at 4pm, here and
    # on debian): each answer is checked above, clashing or not; that one clashes is rule_clashes' test's to show.


def test_rule_clash_of_a_deadline_or_a_kept_rule_is_nothing(heavy: Friday) -> None:
    out = heavy.q("rule_clash", name="late_work")
    assert (out["other"], out["days"], out["sentence"]) == (None, [], "Deadlines come first")
    every = rules(heavy)
    kept = [
        n for n, r in every.items() if r["enabled"] and not r["violated"] and r["effect"] == "Kept throughout this plan"
    ]
    assert kept, "every rule bent"
    assert heavy.q("rule_clash", name=kept[0])["other"] is None  # nothing to trade: no plan made afresh needed


def test_rule_clash_refuses_a_rule_that_isnt_there(heavy: Friday) -> None:
    said = refused(heavy, "rule_clash", query=True, name="nonsense")
    assert said == {"field": "name", "message": "name: no rule named nonsense"}


# rule_clashes: the night's clashes, in the Inbox, while they stand


def overnight(friday: Friday) -> int:
    """The nightly job (server/jobs.py `clashes`), on this Friday's own database: what each bent rule clashes with."""
    conn = connect(str(friday.folder / "data" / "friday.db"))
    try:
        found = find_clashes(conn, int(time.time() // 60))
        conn.commit()
        return found
    finally:
        conn.close()


def kept_clashes(friday: Friday, clashes: dict) -> None:
    """What the nightly job keeps, as it keeps it (kv `rule_clashes`): a clash Friday can't be relied on to find on
    any clock, put there to see what the Inbox does with it."""
    conn = connect(str(friday.folder / "data" / "friday.db"))
    try:
        conn.execute(
            "INSERT INTO kv (user_id, key, value) VALUES (1, 'rule_clashes', ?) "
            "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
            [json.dumps(clashes)],
        )
        conn.commit()
    finally:
        conn.close()


def test_rule_clashes_is_empty_before_the_first_night(heavy: Friday) -> None:
    assert heavy.q("rule_clashes") == []


def test_rule_clashes_lists_what_the_night_found_that_your_answer_decides(heavy: Friday) -> None:
    overnight(heavy)
    every = rules(heavy)
    for out in heavy.q("rule_clashes"):
        assert out["ask"] is True and out["said"].endswith("Which should win?")
        assert every[out["rule"]]["violated"] and every[out["rule"]]["enabled"] and every[out["other"]]["enabled"]
        assert out["sentence"] == every[out["rule"]]["sentence"]
        assert out["other_sentence"] == every[out["other"]]["sentence"]


def test_rule_clashes_leaves_out_what_isnt_asked_and_what_you_answered(heavy: Friday) -> None:
    today = day(0)
    asks = {"other": "chunk_cost", "days": [today], "because": "Keeping it splits problem set 1", "ask": True}
    says = {"other": "daily_load", "days": [today], "because": "Keeping it ends today later", "ask": False}
    kept_clashes(heavy, {"daily_load": asks, "chunk_cost": says})
    every = rules(heavy)
    assert every["daily_load"]["violated"] and every["chunk_cost"]["violated"]  # both bent by sixty hours
    (asked,) = heavy.q("rule_clashes")
    assert (asked["rule"], asked["other"], asked["ask"]) == ("daily_load", "chunk_cost", True)
    said = "it clashes with “Fewer, longer sessions”: keeping it splits problem set 1. Which should win?"
    assert asked["said"] == f"{asked['when']}: {said}" and asked["when"]
    heavy.c("rule_win", winner="daily_load", loser="chunk_cost")
    assert heavy.q("rule_clashes") == []  # answered: not asked again
    assert rules(heavy)["daily_load"]["wins_over"] == ["chunk_cost"]


def test_rule_clashes_leaves_out_a_clash_with_a_rule_you_switched_off(heavy: Friday) -> None:
    today = day(0)
    kept_clashes(
        heavy, {"daily_load": {"other": "late_night", "days": [today], "because": "It ends later", "ask": True}}
    )
    assert [c["other"] for c in heavy.q("rule_clashes")] == ["late_night"]
    answer = heavy.http.post("/api/c/rule_set", json={"name": "late_night", "enabled": False})
    assert answer.status_code == 200, answer.text
    assert heavy.q("rule_clashes") == []
    heavy.c("undo", command_id=answer.json()["command_id"])
    assert [c["other"] for c in heavy.q("rule_clashes")] == ["late_night"]
    heavy.c("rule_remove", name="late_night")  # deleted: gone from the Inbox too
    assert heavy.q("rule_clashes") == []


# preview_weights: the plan with rules weighed differently, switched off or replaced, tried and nothing saved (Rules
# and Insights' "what if"), posted as the page posts it


def preview(friday: Friday, **body: object) -> dict:
    answer = friday.http.post("/api/q/preview_weights", json=body)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_preview_tries_rules_off_weighed_or_replaced_and_saves_nothing(heavy: Friday) -> None:
    generation, totals, plan_id = heavy.q("status")["generation"], heavy.q("rule_totals"), heavy.q("status")["plan_id"]
    keys = {b["key"] for b in heavy.q("plan", start=f"{day(0)}T00:00", end=f"{day(7)}T00:00")["blocks"]}
    assert totals.get("daily_load", 0) > 0  # sixty hours in five days bends the day's limit
    off = preview(heavy, off=["daily_load"])
    assert off["rule_totals_before"] == totals and off["rule_totals_after"].get("daily_load", 0) == 0
    heavier = preview(heavy, weights={"daily_load": 5.0})
    assert heavier["rule_totals_before"] == totals
    # a whole list in place of yours: tomorrow forbidden all day, so nothing of the plan is left tomorrow
    rules_now = heavy.q("settings")["rules"]
    weekday = datetime.fromisoformat(day(1)).strftime("%a").lower()
    never = {"days": [weekday], "start": "00:00", "end": "23:59", "price": "forbid"}
    tried = preview(heavy, rules=[*rules_now, {"type": "time_preference", "name": "e2e_no_tomorrow", "params": never}])
    assert tried["moved"] or tried["removed"]
    after = [start for m in tried["moved"] for start, _ in m["after"]] + [b["start"] for b in tried["added"]]
    assert not [t for t in after if t.startswith(day(1))], after
    # nothing of it saved: no change counted, your rules as they were, and no plan saved by a preview (the worker's
    # own re-plan as the clock passes a block may save one meanwhile: 25 Nov, on a busy debian it did)
    assert heavy.q("status")["generation"] == generation and heavy.q("settings")["rules"] == rules_now
    if heavy.q("status")["plan_id"] == plan_id:
        assert heavy.q("rule_totals") == totals
        assert {b["key"] for b in heavy.q("plan", start=f"{day(0)}T00:00", end=f"{day(7)}T00:00")["blocks"]} == keys


def test_a_preview_with_a_rule_that_isnt_one_is_refused(heavy: Friday) -> None:
    bad = [{"type": "daily_load", "name": "x", "params": {"threshold": "lots"}}]
    answer = heavy.http.post("/api/q/preview_weights", json={"rules": bad})
    assert answer.status_code == 422 and answer.json()["field"] == "rules", answer.text
    answer = heavy.http.post("/api/q/preview_weights", json={"weights": {"daily_load": "lots"}})
    assert answer.status_code == 422, answer.text
