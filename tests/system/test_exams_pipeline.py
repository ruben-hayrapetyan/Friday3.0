"""Exams and their prep, the whole pipeline (tests/features.toml: exams; 24 Nov, the user: "go through every single
functionality of the app and build an extensive test suite ... absolutely nothing can break without our tests flagging
it"): a real `fridayd serve` in its own folder, exams and the work that prepares for them added over HTTP as the
Projects & exams page adds them, and what the page reads back: each exam's prep, done and left, when the prep is
planned to finish against the exam, its focus days, and what the exam focus rule gives an exam of a name."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("exams"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def settled(friday: Friday) -> None:
    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, 600)  # a busy machine replans slowly


def exam(friday: Friday, title: str, d: str, start: str = "09:00", end: str = "11:00", **more: object) -> int:
    return friday.c("add", title=title, preset="Exam", start=f"{d}T{start}", end=f"{d}T{end}", **more)["item"]["id"]


def exams(friday: Friday) -> dict[int, dict]:
    return {e["item"]["id"]: e for e in friday.q("exams")}


def focus_for(friday: Friday, title: str) -> int | None:
    return friday.q("exam_focus_for", title=title)["days"]


def test_an_exam_with_nothing_preparing_for_it_says_so_and_a_lecture_isnt_one(friday: Friday) -> None:
    alone = exam(friday, "CHEM 2090 Prelim 1", day(9))
    lecture = friday.c("add", title="CHEM 2090 Lecture", when="fixed", start=f"{day(9)}T13:00",
                       end=f"{day(9)}T14:00")["item"]["id"]  # fmt: skip
    found = exams(friday)
    assert found[alone]["status"] == "no_prep" and found[alone]["prep"] == []
    assert (found[alone]["done_min"], found[alone]["remaining_min"], found[alone]["planned_finish"]) == (0, 0, None)
    assert lecture not in found


def test_exams_come_soonest_first(friday: Friday) -> None:
    later = exam(friday, "PHYS 1112 Final", day(12))
    sooner = exam(friday, "PHYS 1112 Midterm", day(4))
    order = [e["item"]["id"] for e in friday.q("exams")]
    assert order.index(sooner) < order.index(later)


def test_prep_it_waits_on_is_its_prep_planned_before_it_then_ready_once_done(friday: Friday) -> None:
    d = day(5)
    prelim = exam(friday, "MATH 2940 Prelim 2", d, "19:30", "21:00")
    study = friday.c("add", title="Practice prelim", duration_min=90, due=f"{d}T19:30")["item"]["id"]
    friday.c("depend", item_id=prelim, depends_on_id=study)
    got = exams(friday)[prelim]
    assert [p["item"]["id"] for p in got["prep"]] == [study]
    assert got["remaining_min"] == 90 and got["done_min"] == 0
    settled(friday)
    got = friday.until(lambda: (e := exams(friday)[prelim])["status"] == "on_track" and e, 300)
    assert got["planned_finish"] is not None and got["planned_finish"] <= f"{d}T19:30"
    assert got["prep"][0]["planned_finish"] == got["planned_finish"]

    friday.c("done", id=study)
    got = exams(friday)[prelim]
    assert got["status"] == "ready" and got["remaining_min"] == 0
    assert got["done_min"] >= 90  # ticked off: at least its length counts as put in
    friday.c("reopen", id=study)
    assert exams(friday)[prelim]["status"] in ("on_track", "unplanned")  # to do again


def test_exam_prep_for_its_course_due_near_it_is_found_without_a_wait(friday: Friday) -> None:
    d = day(7)
    final = exam(friday, "ECON 1110 Final", d)
    review = friday.c("add", title="ECON 1110 review sheet", preset="Exam prep", duration_min=60,
                      due=f"{d}T09:00")["item"]["id"]  # fmt: skip
    other = friday.c("add", title="HIST 2500 review sheet", preset="Exam prep", duration_min=60,
                     due=f"{d}T09:00")["item"]["id"]  # fmt: skip
    far = friday.c("add", title="ECON 1110 old notes", preset="Exam prep", duration_min=60,
                   due=f"{day(1)}T09:00")["item"]["id"]  # fmt: skip
    prep = [p["item"]["id"] for p in exams(friday)[final]["prep"]]
    assert review in prep
    assert other not in prep  # another course
    assert far not in prep  # due six days before it: not for it


def test_an_event_named_like_an_exam_counts_once_something_prepares_for_it(friday: Friday) -> None:
    d = day(8)
    quiz = friday.c("add", title="BIO 1500 midterm", when="fixed", start=f"{d}T10:00", end=f"{d}T11:00")["item"]["id"]
    assert quiz not in exams(friday)
    notes = friday.c("add", title="Make flash cards", duration_min=30, due=f"{d}T10:00")["item"]["id"]
    friday.c("depend", item_id=quiz, depends_on_id=notes)
    assert [p["item"]["id"] for p in exams(friday)[quiz]["prep"]] == [notes]


def test_prep_with_no_room_before_the_exam_is_late(friday: Friday) -> None:
    d = day(1)
    soon = exam(friday, "CS 3110 Prelim", d, "08:00", "09:30")
    cram = friday.c("add", title="CS 3110 everything", duration_min=1800, firmness="hard",
                    due=f"{d}T08:00")["item"]["id"]  # fmt: skip
    friday.c("depend", item_id=soon, depends_on_id=cram)
    settled(friday)
    got = friday.until(lambda: (e := exams(friday)[soon])["status"] in ("late", "unplanned") and e, 300)
    assert got["remaining_min"] == 1800
    if got["status"] == "late":  # planned past the exam's start, or with no room at all
        assert (got["planned_finish"] or "") > f"{d}T08:00" or got["unfit_min"] > 0


def test_exam_focus_for_follows_the_rule_its_days_and_its_switch(friday: Friday) -> None:
    assert focus_for(friday, "MATH 2940 Prelim 2") is None  # no rule yet
    target = exam(friday, "ENGL 2000 Prelim", day(10))
    assert exams(friday)[target]["focus_from"] is None and exams(friday)[target]["rule_days"] is None
    friday.c("rule_add", text="focus on exams 3 days before")
    assert focus_for(friday, "MATH 2940 Prelim 2") == 3
    assert focus_for(friday, "physics finals") == 3
    assert focus_for(friday, "Final project presentation") is None  # a final project isn't an exam
    assert focus_for(friday, "Dinner with Sam") is None
    got = exams(friday)[target]
    assert (got["focus_days"], got["rule_days"], got["focus_own"]) == (3, 3, False)
    assert got["focus_from"] is not None and got["focus_from"] < f"{day(10)}T09:00"

    friday.c("rule_edit", name="you:exam-focus", overrides={"amount": 1})
    assert focus_for(friday, "MATH 2940 Prelim 2") == 1
    assert exams(friday)[target]["focus_from"] > got["focus_from"]  # a day before, not three
    friday.c("rule_set", name="you:exam-focus", enabled=False)
    assert focus_for(friday, "MATH 2940 Prelim 2") is None
    assert exams(friday)[target]["focus_from"] is None
    friday.c("rule_set", name="you:exam-focus", enabled=True)
    assert focus_for(friday, "MATH 2940 Prelim 2") == 1


def test_an_exams_own_focus_days_beat_the_rules(friday: Friday) -> None:
    quiz = exam(friday, "SPAN 1120 Prelim", day(11))
    friday.c("settings_set", key="exam_focus_each", value={str(quiz): 0})
    got = exams(friday)[quiz]
    assert (got["focus_days"], got["focus_own"]) == (0, True)
    assert got["focus_from"] is not None and got["focus_from"].startswith(day(11))  # its own day, until it
    assert focus_for(friday, "SPAN 1120 Prelim") == got["rule_days"]  # the rule's, its own days aside


def test_exam_focus_for_needs_a_title(friday: Friday) -> None:
    assert friday.http.get("/api/q/exam_focus_for").status_code == 422
