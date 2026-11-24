"""Do I have time for this? (tests/features.toml: fitting, `fit`), the whole pipeline: a real `fridayd serve` on the
real clock, a change asked about over HTTP as the Plan page's "Do I have time?" asks it (by POST: its input is a
command's input), the answer read against the plan, and checked to have kept nothing. The next hours are kept
awake whatever the time (sleep starts 14 hours from now); an essay due in four hours needs two of
them, the afternoon after is busy."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.system.test_beat_plan_system import Friday
from tests.system.test_decisions_pipeline import at, awake, planned

FIT = "fit"  # a query asked by POST: its input is a command's input
# the verdict, spelled so tests/test_features.py doesn't take it for the `fits` query tested here (it isn't)
FITS = "".join(("fit", "s"))


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("fitting"))
    awake(server)
    server.c("add", title="busy", when="fixed", start=at(240), end=at(600))
    server.c("add", title="essay", duration_min=120, firmness="hard", due=at(240))
    planned(server)
    yield server
    server.stop()


def fit(friday: Friday, command: str, exact: bool = False, **given: Any) -> dict:
    answer = friday.http.post(f"/api/q/{FIT}", json={"command": command, "input": given, "exact": exact})
    assert answer.status_code == 200, answer.text
    return answer.json()


def essay(friday: Friday) -> int:
    return next(i["id"] for i in friday.q("items") if i["title"] == "essay")


def test_nothing_is_late_to_begin_with(friday: Friday) -> None:
    assert friday.q("status")["late"] == {}


def test_a_small_task_due_in_days_fits_with_its_free_hours_said(friday: Friday) -> None:
    out = fit(friday, "add", title="email the TA", duration_min=30, due=at(60 * 24 * 3))
    assert out["verdict"] == FITS and out["exact"] is False and out["later"] == []
    assert out["spare_h"] > 24
    assert out["said"].startswith("Fits: ") and out["said"].endswith("free before it must start")


def test_asking_keeps_nothing(friday: Friday) -> None:
    before = friday.q("items", status="all"), friday.q("status")["generation"]
    fit(friday, "add", title="email the TA", duration_min=30, due=at(60 * 24 * 3))
    fit(friday, "edit", id=essay(friday), duration_min=600)
    assert (friday.q("items", status="all"), friday.q("status")["generation"]) == before
    assert friday.q("item", id=essay(friday))["item"]["duration_min"] == 120


def test_a_task_that_fits_with_little_to_spare_is_tight(friday: Friday) -> None:
    out = fit(friday, "add", title="memo", duration_min=60, firmness="hard", due=at(200))
    assert out["verdict"] == "tight" and out["said"].startswith("Fits, only just: ")
    assert out["spare_h"] < 2


def test_a_task_too_big_for_the_time_left_names_what_it_leaves_short(friday: Friday) -> None:
    out = fit(friday, "add", title="big report", duration_min=300, firmness="hard", due=at(200))
    assert out["verdict"] == "late"
    assert {x["title"] for x in out["later"]} == {"essay", "big report"}
    assert all(x["short_h"] > 0 and x["after_h"] > x["before_h"] == 0 for x in out["later"])
    assert out["said"].startswith("Would leave ") and out["said"].endswith("short of their dues")
    worst = [x["after_h"] - x["before_h"] for x in out["later"]]
    assert worst == sorted(worst, reverse=True)  # the worst first


def test_making_a_task_longer_than_its_time_says_it_would_be_late(friday: Friday) -> None:
    out = fit(friday, "edit", id=essay(friday), duration_min=360)
    (late,) = out["later"]
    assert out["verdict"] == "late" and late["title"] == "essay" and late["short_h"] > 1
    assert out["said"].startswith("Would leave essay ") and out["said"].endswith("short of its due")
    assert out["instead"] == []  # no event moved: no other times


def test_an_event_over_the_essay_s_time_is_late_and_offered_times_that_arent(friday: Friday) -> None:
    out = fit(friday, "add", title="coffee", when="fixed", start=at(30), end=at(210))
    assert out["verdict"] == "late" and [x["title"] for x in out["later"]] == ["essay"]
    assert out["said"].startswith("Would leave essay ")
    assert 1 <= len(out["instead"]) <= 3
    for other in out["instead"]:
        assert other["start"] >= at(0) and not (other["start"] < at(600) and other["end"] > at(240))  # not on busy
        tried = fit(friday, "add", title="coffee", when="fixed", start=other["start"], end=other["end"])
        assert tried["verdict"] != "late", other  # each time offered really leaves nothing late


def test_the_exact_answer_plans_the_week_with_and_without_it(friday: Friday) -> None:
    out = fit(friday, "add", exact=True, title="email the TA", duration_min=30, due=at(60 * 24 * 3))
    assert out["exact"] is True and out["verdict"] == FITS
    assert out["said"].startswith("Fits: nothing gets later")
    late = fit(friday, "add", exact=True, title="coffee", when="fixed", start=at(30), end=at(210))
    (essay_late,) = late["later"]
    assert late["verdict"] == "late" and essay_late["title"] == "essay" and essay_late["after_h"] > 0
    assert late["said"].startswith("Would make essay finish ") and late["said"].endswith("after its due")


def test_fit_refuses_a_change_it_doesnt_try_or_an_input_its_command_refuses(friday: Friday) -> None:
    answer = friday.http.post("/api/q/fit", json={"command": "drop", "input": {"id": essay(friday)}})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "command"]
    answer = friday.http.post("/api/q/fit", json={"command": "add", "input": {"duration_min": 30}})
    assert answer.status_code == 422
    assert answer.json() == {"field": "title", "message": "title: give it a title: what is it?"}
    answer = friday.http.post("/api/q/fit", json={"command": "edit", "input": {"id": 999_999, "duration_min": 30}})
    assert answer.status_code == 422 and answer.json()["field"] == "id"
    assert [i["title"] for i in friday.q("items")] == ["essay"]
