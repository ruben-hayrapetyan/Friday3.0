"""Birthdays asked for as a list, the whole system, with an AI that isn't Claude (8 Nov: "make sure all of the
refinements that we are doing for claude apply to the other model providers as well"): a real `fridayd serve` asking
the stand-in model on this Mac (tests/fake_ollama.py), Mira's birthday already yearly. The model is told how a
birthday is made and that Mira's is there; its Mira is refused, its Remy offered, and Remy's, from midnight to
11:59pm as it gave it, is the whole day once applied and leaves the day's work to plan."""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_ai_system import Friday, Ollama

TZ = "America/New_York"


@pytest.fixture(scope="module")
def system(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, Ollama, str]]:
    ollama = Ollama(["llama3.2:3b"])
    friday = Friday(tmp_path_factory.mktemp("birthdays"), ollama)
    friday.c("local_model_use", name="llama3.2:3b")
    day = str((datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).date())
    friday.c("add", title="Mira's Birthday", when="fixed", start=f"{day}T00:00", end=next_midnight(day),
             every="rrule:FREQ=YEARLY", after=[], before=[], exceptions=[])  # fmt: skip
    answer = {"reply": "Two birthdays.", "actions": [
        {"sentence": "Mira", "command": "add", "input": {"title": "Miras birthday", "when": "fixed",
                                                          "start": f"{day}T00:00", "end": next_midnight(day),
                                                          "every": "rrule:FREQ=YEARLY"}},
        {"sentence": "Remy", "command": "add", "input": {"title": "Remy's Birthday", "when": "fixed",
                                                        "start": f"{day}T00:00", "end": f"{day}T23:59",
                                                        "every": "rrule:FREQ=YEARLY"}},
    ]}  # fmt: skip
    ollama.tell("answer " + json.dumps(answer))
    yield friday, ollama, day
    friday.stop()
    ollama.stop()


def next_midnight(day: str) -> str:
    return f"{datetime.fromisoformat(day).date() + timedelta(days=1)}T00:00"


def test_the_model_is_told_how_and_what_is_there_and_its_repeat_is_refused(
    system: tuple[Friday, Ollama, str],
) -> None:
    friday, ollama, day = system
    out = friday.c("ask_claude", text="Club Bdays: Mira, Remy")
    told = json.loads(ollama.state()["told"])
    assert 'next day\'s "T00:00"' in told[0] and "Club Bdays" in told[1]
    assert '"repeating"' in told[1] and "Mira's Birthday" in told[1] and f"{day}T00:00" in told[1]
    assert [a["error"] for a in out["actions"]] == ["You already have Miras birthday then, repeating", None]


def test_the_one_offered_is_the_whole_day_and_the_days_work_is_planned(system: tuple[Friday, Ollama, str]) -> None:
    friday, _, day = system
    remy = friday.c("ask_claude", text="Remy")["actions"][1]
    friday.c(remy["command"], **remy["input"])
    friday.c("add", title="essay", duration_min=120, release=f"{day}T00:00", due=f"{day}T23:00")
    friday.c("replan")
    plan = friday.q("plan", start=f"{day}T00:00", end=next_midnight(day))
    (birthday,) = [f for f in plan["fixed"] if f["title"] == "Remy's Birthday"]
    assert (birthday["start"], birthday["end"]) == (f"{day}T00:00", next_midnight(day))
    assert [b for b in plan["blocks"] if b["title"] == "essay"]
