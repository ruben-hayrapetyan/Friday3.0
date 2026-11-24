"""The learned lengths and hours switch (tests/features.toml: learned: learn_module), the whole pipeline (24 Nov, the
user: "go through every single functionality of the app and build an extensive test suite"): a real `fridayd serve`,
the switch flipped over HTTP as Insights does, before anything is learned and after; five timed things finished, and
the server's own nightly job (moved to the minute just gone, so it runs now) learning their lengths. The tests run in
order on one server."""

import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday, local

NOW = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("learned"))
    yield server
    server.stop()


def refused(friday: Friday, command: str, /, **body: Any) -> dict[str, Any]:
    answer = friday.http.post(f"/api/c/{command}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_1_switched_on_before_anything_is_learned_its_kept_for_later(friday: Friday) -> None:
    out = friday.q("learning")
    assert (out["durations"], out["durations_wanted"], out["energy"]) == (None, False, None)
    said = friday.c("learn_module", module="durations", use=True)
    assert said["message"] == "On: Friday adjusts new estimates once it has learned how long things take"
    assert friday.q("learning")["durations_wanted"] is True
    assert friday.q("learning")["durations"] is None  # nothing learned yet: nothing made up


def test_2_switched_off_again_before_anything_is_learned(friday: Friday) -> None:
    assert friday.c("learn_module", module="durations", use=False)["message"] == "Off"
    assert friday.q("learning")["durations_wanted"] is False


def test_3_the_good_and_bad_hours_switch_says_its_own_words(friday: Friday) -> None:
    said = friday.c("learn_module", module="energy", use=True)
    assert said["message"] == "On: Friday uses your good and bad hours once it has learned them"
    assert friday.q("learning")["energy"] is None
    assert friday.q("learning")["durations_wanted"] is False  # the other switch stays as it was
    assert friday.c("learn_module", module="energy", use=False)["message"] == "Off"


def test_4_only_the_two_modules_and_a_yes_or_no(friday: Friday) -> None:
    assert refused(friday, "learn_module", module="moods", use=True)["detail"][0]["loc"] == ["body", "module"]
    assert refused(friday, "learn_module", module="durations")["detail"][0]["loc"] == ["body", "use"]
    assert friday.q("learning")["durations_wanted"] is False


@pytest.fixture(scope="module")
def learned(friday: Friday) -> dict[str, Any]:
    """Five readings timed and finished over the last days, then the night's job run now: lengths learned."""
    friday.c("learn_module", module="durations", use=True)  # wanted before it's learned: in use once it is
    for n in range(5):
        task = friday.c("add", title=f"Chapter {n + 1} reading", duration_min=60, preset="Reading")["item"]["id"]
        start = (NOW - timedelta(days=n + 1)).replace(hour=14, minute=0)
        friday.c("log", id=task, start=local(start), end=local(start + timedelta(minutes=40 + 5 * n)))
        friday.c("done", id=task)
    assert friday.q("learning")["progress"]["lengths"] == {"have": 5, "need": 5}
    began = datetime.now(ZoneInfo(TZ))
    time.sleep(61 - began.second)  # into a minute that began after the server's first night job
    jobs = friday.q("settings")["jobs"]
    tonight = datetime.now(ZoneInfo(TZ)).strftime("%H:%M")
    friday.c("settings_set", key="jobs", value=jobs | {"nightly_replan_at": tonight})
    out = friday.until(lambda: friday.q("learning")["durations"], timeout=150)
    friday.c("settings_set", key="jobs", value=jobs)
    return out


def test_5_once_learned_what_you_switched_on_is_in_use(friday: Friday, learned: dict[str, Any]) -> None:
    assert learned["n"] == 5 and learned["in_use"] is True
    assert friday.q("learning")["durations_wanted"] is True


def test_6_stopped_and_used_again_once_learned(friday: Friday, learned: dict[str, Any]) -> None:
    said = friday.c("learn_module", module="durations", use=False)
    assert said["message"] == "Stopped using learned durations"
    out = friday.q("learning")
    assert out["durations"]["in_use"] is False and out["durations"]["n"] == 5 and out["durations_wanted"] is False
    assert friday.c("learn_module", module="durations", use=True)["message"] == "Using learned durations"
    assert friday.q("learning")["durations"]["in_use"] is True


def test_7_starting_lengths_over_forgets_them(friday: Friday, learned: dict[str, Any]) -> None:
    assert friday.c("learn_reset", module="durations")["message"] == "Reset durations"
    assert friday.q("learning")["durations"] is None
    said = friday.c("learn_module", module="durations", use=True)  # back to waiting for something learned
    assert said["message"].startswith("On: Friday adjusts new estimates")
