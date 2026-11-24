"""Whether work may take an event's time (tests/features.toml: optional_events), the whole pipeline: a real `fridayd
serve`, the event editor's "Can work take its time?" sent over HTTP as `event_optional`, and what it changes read
back the way the app reads it: `event_mode` (the editor), the Rules page's rules, and the plan itself (work that
would be late otherwise takes an optional event's time, and keeps off a kept one)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("optional-events"))
    now = datetime.now(ZoneInfo(TZ))
    # awake for the hours around now, whenever the test runs
    awake = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}"}
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, awake | {"margin_min": 0}))
    yield server
    server.stop()


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def rules_naming(friday: Friday, title: str) -> list[dict]:
    return [r for r in friday.q("rules") if title in r["sentence"]]


def test_an_event_nothing_names_is_kept(friday: Friday) -> None:
    assert friday.q("event_mode", title="Choir practice") == {"mode": "kept", "rule": None, "covered_by": []}


def test_optional_writes_one_rule_in_your_words_and_the_editor_reads_it_back(friday: Friday) -> None:
    said = friday.c("event_optional", title="Gym with Sam", mode="optional")["message"]
    assert "Gym with Sam" in said and "optional" in said.lower()
    mode = friday.q("event_mode", title="Gym with Sam")
    assert mode["mode"] == "optional" and mode["rule"] == said and mode["covered_by"] == []
    (rule,) = rules_naming(friday, "Gym with Sam")
    assert rule["source"] == "you" and rule["type"] == "skippable" and rule["enabled"]
    # the title as written, spaces tidied: the same event
    assert friday.q("event_mode", title="  gym   with sam ")["mode"] == "optional"


def test_only_when_ahead_replaces_optional_rather_than_adding_a_second_rule(friday: Friday) -> None:
    friday.c("event_optional", title="Gym with Sam", mode="optional")
    friday.c("event_optional", title="Gym with Sam", mode="ahead")
    assert friday.q("event_mode", title="Gym with Sam")["mode"] == "ahead"
    assert len(rules_naming(friday, "Gym with Sam")) == 1


def test_kept_takes_the_events_rule_away(friday: Friday) -> None:
    friday.c("event_optional", title="Gym with Sam", mode="optional")
    said = friday.c("event_optional", title="Gym with Sam", mode="kept")["message"]
    assert said == "Gym with Sam: work keeps off it"
    assert friday.q("event_mode", title="Gym with Sam") == {"mode": "kept", "rule": None, "covered_by": []}
    assert rules_naming(friday, "Gym with Sam") == []


def test_a_broader_rule_still_covering_it_is_said_and_left_alone(friday: Friday) -> None:
    friday.c("rule_add", text="choir is optional")
    broad = [r["sentence"] for r in friday.q("rules") if "choir" in r["sentence"].lower()]
    assert len(broad) == 1
    said = friday.c("event_optional", title="Choir with Ana", mode="kept")["message"]
    assert "still covers it" in said and broad[0] in said
    mode = friday.q("event_mode", title="Choir with Ana")
    assert mode["mode"] == "kept" and mode["covered_by"] == broad
    assert [r["sentence"] for r in friday.q("rules") if "choir" in r["sentence"].lower()] == broad  # not changed


def test_no_title_or_a_mode_it_doesnt_know_is_refused(friday: Friday) -> None:
    before = friday.q("rules")
    blank = refused(friday, "event_optional", title="   ", mode="optional")
    assert blank["field"] == "title" and "Give its title" in blank["message"]
    wrong = refused(friday, "event_optional", title="Gym", mode="sometimes")
    assert [e["loc"][-1] for e in wrong["detail"]] == ["mode"]  # the request's own check
    missing = friday.http.get("/api/q/event_mode")
    assert missing.status_code == 422 and [e["loc"][-1] for e in missing.json()["detail"]] == ["title"]
    assert friday.q("rules") == before  # nothing written


def test_the_plan_takes_an_optional_events_time_only_when_work_would_be_late(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    start = now + timedelta(minutes=45 - now.minute % 15)  # on a quarter hour, 30–45 min from now
    end = start + timedelta(hours=3)
    event = friday.c("add", title="Pottery night", when="fixed", start=local(start), end=local(end))["item"]
    # three hours of work due when the event ends: before the event there's under an hour
    task = friday.c("add", title="Lab report", duration_min=180, firmness="hard", due=local(end))["item"]

    def late() -> set[int]:
        friday.c("replan")
        return {i["item_id"] for i in friday.q("status")["late_items"]}

    def over_event() -> int:
        blocks = friday.q("plan", start=local(start), end=local(end))["blocks"]
        return sum(1 for b in blocks if b["item_id"] == task["id"])

    assert task["id"] in late() and over_event() == 0  # kept: work keeps off it, and is late
    friday.c("event_optional", title="Pottery night", mode="optional")
    assert friday.until(lambda: task["id"] not in late())
    assert over_event() > 0  # it took the event's time
    friday.c("event_optional", title="Pottery night", mode="kept")
    assert friday.until(lambda: task["id"] in late())
    assert over_event() == 0
    friday.c("drop", id=task["id"])
    friday.c("drop", id=event["id"])
