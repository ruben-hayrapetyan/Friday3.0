"""What Friday learns (tests/features.toml: learning: questions, compare_answer, proposal_answer, checkin, learn_apply,
learn_reject, learn_reset, learn_order, learning), the whole pipeline (24 Nov, the user: "go through every single
functionality of the app and build an extensive test suite"): a real `fridayd serve` whose hourly job draws today's
questions about tomorrow from a week of work (in its folder before it first starts, so its first pass finds it), the
questions answered over HTTP as the evening review asks them, the review submitted, and what Friday then suggests,
asks and plans with read back. The tests run in order on one server."""

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from friday.commands.registry import run
from friday.core.db import connect
from friday.server.app import wall_clock
from tests.system.test_beat_plan_system import REPO, TZ, Friday, local

NOW = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
TOMORROW = (NOW + timedelta(days=1)).replace(hour=0, minute=0)
LATE = "you:no-work-after-11pm"
EARLY = "you:no-work-before-7am"


def seeded(folder: Any) -> Friday:
    """A Friday with a week of work and tomorrow's lecture already in it when it first starts."""
    data = folder / "data"
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")} | {"FRIDAY_DATA_DIR": str(data)}
    init = [sys.executable, "-m", "friday.server.main", "--data-dir", str(data), "init", "--timezone", TZ]
    subprocess.run(init, cwd=REPO, env=env, check=True, capture_output=True)
    conn = connect(data / "friday.db")
    for n, (title, hours) in enumerate((("Essay", 3), ("Problem set", 2), ("Reading", 2), ("Lab report", 3))):
        due = local(TOMORROW + timedelta(days=2 + n, hours=17))
        run(
            conn,
            "add",
            {"title": title, "duration_min": hours * 60, "due": due},
            now_utc=wall_clock(),
            provisional=False,
        )
    start = TOMORROW + timedelta(hours=10)
    lecture = {"title": "Lecture", "when": "fixed", "start": local(start), "end": local(start + timedelta(hours=1))}
    run(conn, "add", lecture, now_utc=wall_clock(), provisional=False)
    conn.close()
    return Friday(folder)


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = seeded(tmp_path_factory.mktemp("learning"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def asked(friday: Friday) -> list[dict[str, Any]]:
    """Today's questions, once the job has drawn them."""
    return friday.until(lambda: friday.q("questions")["comparisons"], timeout=120)


def refused(friday: Friday, command: str, /, **body: Any) -> dict[str, Any]:
    answer = friday.http.post(f"/api/c/{command}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def item_id(friday: Friday, title: str) -> int:
    return next(i["id"] for i in friday.q("items", status="all") if i["title"] == title)


def test_01_nothing_is_learned_at_first(friday: Friday) -> None:
    out = friday.q("learning")
    assert (out["mode"], out["version"], out["multipliers"], out["suggested"]) == ("suggest", 0, {}, None)
    assert (out["comparisons"], out["drags"], out["digest"], out["order"]) == (0, 0, [], None)
    assert out["progress"] == {"lengths": {"have": 0, "need": 5}, "order": {"have": 0, "need": 4}}
    assert out["proposals"] == {"pending": None, "accepted": [], "refused": []}


def test_02_a_yes_to_nothing_proposed_is_refused(friday: Friday) -> None:
    said = refused(friday, "proposal_answer", kind="rule", name="fri_sat:late:any", yes=True)
    assert said == {"field": "name", "message": "name: nothing was proposed"}


def test_03_the_job_asks_up_to_three_questions_about_tomorrow(friday: Friday, asked: list[dict[str, Any]]) -> None:
    assert 1 <= len(asked) <= 3 and len({q["id"] for q in asked}) == len(asked)
    ten = TOMORROW + timedelta(hours=10)
    lecture = [{"title": "Lecture", "start": local(ten), "end": local(ten + timedelta(hours=1))}]
    for q in asked:
        assert q["day"] == TOMORROW.date().isoformat()
        assert q["fixed"] == lecture  # each version is drawn around what can't move
        assert q["a"] != q["b"]  # two different days to choose between
        titles = {b["title"] for b in q["a"] + q["b"]}
        assert titles <= {"Essay", "Problem set", "Reading", "Lab report"} and titles
    out = friday.q("questions")
    assert (out["proposal"], out["wall"], out["checkin"]) == (None, None, False)


def test_04_an_answer_to_no_question_is_refused(friday: Friday, asked: list[dict[str, Any]]) -> None:
    said = refused(friday, "compare_answer", id=9999, answer="a")
    assert said == {"field": "id", "message": "id: no comparison 9999"}
    said = refused(friday, "compare_answer", id=asked[0]["id"], answer="c")
    assert said["detail"][0]["loc"] == ["body", "answer"]
    assert [q["id"] for q in friday.q("questions")["comparisons"]] == [q["id"] for q in asked]


def test_05_a_skipped_question_goes_and_teaches_nothing(friday: Friday, asked: list[dict[str, Any]]) -> None:
    assert len(asked) == 3, "the job draws three a day (learn.questions_per_day)"
    assert friday.c("compare_answer", id=asked[0]["id"], answer="skip")["message"] == "Skipped"
    assert asked[0]["id"] not in {q["id"] for q in friday.q("questions")["comparisons"]}
    assert friday.q("learning")["comparisons"] == 0


def test_06_an_answer_counts_but_waits_for_the_review(friday: Friday, asked: list[dict[str, Any]]) -> None:
    assert friday.c("compare_answer", id=asked[1]["id"], answer="a")["message"] == "Thanks"
    assert [q["id"] for q in friday.q("questions")["comparisons"]] == [asked[2]["id"]]
    out = friday.q("learning")
    assert (out["comparisons"], out["suggested"], out["version"]) == (1, None, 0)


def test_07_nothing_suggested_cant_be_applied_or_turned_down(friday: Friday) -> None:
    for name in ("learn_apply", "learn_reject"):
        said = refused(friday, name, version=1)
        assert said == {"field": "version", "message": "version: no suggested profile version 1"}
    assert friday.q("learning")["version"] == 0


def test_08_the_review_fits_the_answers_into_a_suggestion(friday: Friday) -> None:
    friday.c("rule_add", text="no work after 11pm", strength="Always")
    friday.c("rule_add", text="no work before 7am", strength="Always")
    essay = item_id(friday, "Essay")
    late = (NOW - timedelta(days=2)).replace(hour=23, minute=15)  # inside "no work after 11pm"
    friday.c("log", id=essay, start=local(late), end=local(late + timedelta(minutes=30)))
    early = (NOW - timedelta(days=3)).replace(hour=5, minute=0)  # inside "no work before 7am"
    friday.c("log", id=essay, start=local(early), end=local(early + timedelta(minutes=30)))
    assert friday.c("review_submit")["message"].startswith("Reviewed ")
    out = friday.q("learning")
    assert out["suggested"] is not None and out["suggested"]["version"] == 1
    assert out["version"] == 0 and out["multipliers"] == {}  # suggest mode: nothing is used before your yes
    expected = [
        f"{'Raise' if c['to'] > c['from'] else 'Lower'} {c['rule'].replace('_', ' ')} ×{c['to'] / c['from']:.1f}"
        for c in out["suggested"]["changes"]
        if c["from"]
    ]
    assert out["digest"][: len(expected)] == expected


def test_09_work_inside_a_never_rule_asks_whether_to_keep_it_hard(friday: Friday) -> None:
    wall = friday.q("questions")["wall"]
    assert wall == {
        "rule": LATE,
        "sentence": f"You worked during '{LATE}'. Keep it as a hard rule? (No makes it a strong preference.)",
    }


def test_10_a_suggestion_turned_down_isnt_used_and_cant_be_applied_after(friday: Friday) -> None:
    assert friday.c("learn_reject", version=1)["message"] == "Kept the weights as they were"
    out = friday.q("learning")
    assert (out["suggested"], out["version"], out["multipliers"]) == (None, 0, {})
    assert refused(friday, "learn_apply", version=1)["message"] == "version: no suggested profile version 1"
    assert refused(friday, "learn_reject", version=1)["message"] == "version: no suggested profile version 1"


def test_11_no_to_keeping_a_never_rule_hard_softens_it(friday: Friday) -> None:
    said = friday.c("proposal_answer", kind="wall", name=LATE, yes=False)
    assert said["message"] == "Now a strong preference"
    rules = {r["name"]: r for r in friday.q("settings")["rules"]}
    assert rules[LATE]["params"]["price"] == 10.0
    assert rules[EARLY]["params"]["price"] == "forbid"  # only the one asked about
    assert friday.q("questions")["wall"] is None


def test_12_a_yes_to_a_rule_friday_never_proposed_is_refused(friday: Friday) -> None:
    assert refused(friday, "proposal_answer", kind="rule", name="nope", yes=True) == {
        "field": "name",
        "message": "name: no proposal nope",
    }
    said = refused(friday, "proposal_answer", kind="maybe", name=LATE, yes=True)
    assert said["detail"][0]["loc"] == ["body", "kind"]


def test_13_the_next_review_suggests_again_and_asks_about_the_next_rule(
    friday: Friday, asked: list[dict[str, Any]]
) -> None:
    friday.c("compare_answer", id=asked[2]["id"], answer="b")
    assert friday.q("questions")["comparisons"] == []  # all of today's answered
    friday.c("review_submit")
    out = friday.q("learning")
    assert out["comparisons"] == 2 and out["suggested"]["version"] == 2
    assert friday.q("questions")["wall"]["rule"] == EARLY  # the softened one isn't a "never" any more


def test_14_a_suggestion_applied_is_what_plans_from_now(friday: Friday) -> None:
    assert friday.c("learn_apply", version=2)["message"] == "Applied what Friday learned"
    out = friday.q("learning")
    assert out["version"] == 2 and out["suggested"] is None
    assert out["multipliers"] and all(v > 0 for v in out["multipliers"].values())
    assert refused(friday, "learn_apply", version=2)["message"] == "version: no suggested profile version 2"


def test_15_yes_to_keeping_a_never_rule_hard_keeps_it(friday: Friday) -> None:
    assert friday.c("proposal_answer", kind="wall", name=EARLY, yes=True)["message"] == "Kept as a hard rule"
    rules = {r["name"]: r for r in friday.q("settings")["rules"]}
    assert rules[EARLY]["params"]["price"] == "forbid" and rules[LATE]["params"]["price"] == 10.0
    assert friday.q("questions")["wall"] is None


def test_16_starting_the_weights_over_puts_back_the_ones_you_set(friday: Friday) -> None:
    before = friday.q("learning")["multipliers"]
    assert friday.c("learn_reset", module="weights")["message"] == "Reset weights"
    out = friday.q("learning")
    assert out["version"] == 3 and set(out["multipliers"]) == set(before)
    assert all(v == 1.0 for v in out["multipliers"].values())
    assert out["comparisons"] == 2  # your answers stay; only the weights start over
    assert refused(friday, "learn_reset", module="moods")["detail"][0]["loc"] == ["body", "module"]


def test_17_a_check_in_is_asked_only_while_state_inference_is_on(friday: Friday) -> None:
    assert friday.q("questions")["checkin"] is False
    learn = friday.q("settings")["learn"]
    friday.c("settings_set", key="learn", value=learn | {"state_inference": "on"})
    assert friday.q("questions")["checkin"] is True
    assert refused(friday, "checkin", state="grumpy")["detail"][0]["loc"] == ["body", "state"]
    assert friday.q("questions")["checkin"] is True
    assert friday.c("checkin", state="tired")["message"] == "Noted: tired"
    assert friday.q("questions")["checkin"] is False  # once a day
    assert friday.c("checkin", state="motivated")["message"] == "Noted: motivated"  # a change of mind is kept
    friday.c("settings_set", key="learn", value=learn)


def test_18_a_kind_planned_first_from_now(friday: Friday) -> None:
    said = friday.c("learn_order", first="Reading", then="Assignment", use=True)
    assert said["message"] == "Reading is planned ahead of Assignment from now"
    assert friday.q("settings")["kind_order"] == ["Reading", "Assignment"]
    friday.c("learn_order", first="Exam prep", then="Assignment", use=True)
    assert friday.q("settings")["kind_order"] == ["Reading", "Exam prep", "Assignment"]  # just ahead of it


def test_19_an_order_turned_down_changes_nothing(friday: Friday) -> None:
    said = friday.c("learn_order", first="Assignment", then="Reading", use=False)
    assert said["message"] == "Friday won't suggest Assignment before Reading again"
    assert friday.q("settings")["kind_order"] == ["Reading", "Exam prep", "Assignment"]
    assert refused(friday, "learn_order", first="Reading", then="Assignment")["detail"][0]["loc"] == ["body", "use"]


def test_20_lengths_learn_from_what_you_timed_and_finished(friday: Friday) -> None:
    for n, title in enumerate(("Problem set", "Reading")):
        task = item_id(friday, title)
        start = (NOW - timedelta(days=1 + n)).replace(hour=14, minute=0)
        friday.c("log", id=task, start=local(start), end=local(start + timedelta(minutes=50)))
        friday.c("done", id=task)
    assert friday.q("learning")["progress"]["lengths"] == {"have": 2, "need": 5}
    untimed = friday.c("add", title="Email the TA", duration_min=15, due=local(TOMORROW + timedelta(hours=12)))
    friday.c("done", id=untimed["item"]["id"])  # done without a time: nothing to learn a length from
    assert friday.q("learning")["progress"]["lengths"]["have"] == 2


def test_21_starting_everything_over_keeps_your_answers_and_order(friday: Friday) -> None:
    assert friday.c("learn_reset")["message"] == "Reset all"
    out = friday.q("learning")
    assert out["version"] == 4 and all(v == 1.0 for v in out["multipliers"].values())
    assert out["proposals"] == {"pending": None, "accepted": [], "refused": []}
    assert out["durations"] is None and out["energy"] is None
    assert out["comparisons"] == 2 and friday.q("settings")["kind_order"] == ["Reading", "Exam prep", "Assignment"]


def test_22_a_block_you_move_is_an_answer_your_version_won(friday: Friday) -> None:
    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up)
    lab = item_id(friday, "Lab report")
    block = next(b for b in friday.q("plan")["blocks"] if b["item_id"] == lab)
    moved = TOMORROW + timedelta(hours=15)  # after the lecture, well before its due
    if local(moved) == block["start"]:
        moved += timedelta(hours=1)
    friday.c("pin", id=lab, start=local(moved), from_start=block["start"], from_end=block["end"])
    out = friday.until(lambda: (o := friday.q("learning"))["drags"] and o, timeout=120)
    assert (out["drags"], out["comparisons"]) == (1, 2)  # a move counts apart from the questions answered
