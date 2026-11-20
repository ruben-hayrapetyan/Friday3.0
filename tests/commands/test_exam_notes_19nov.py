"""A user's notes (19 Nov, the second): an exam's prep line and its focus, as the server says them.

1. "Prep runs past the exam: it's planned to finish 18:30" of an exam at 19:00: "this is technically not running past
   the exam (although cutting it close)". Work of the exam's tag you timed ran over, so the plan reserves more than
   your estimate (the learned cushion); the part with no room made the exam late while the rest finished in time. The
   exam now says how much has no room (`unfit_min`); your answer: "Say what doesn't fit".
2. The popup's exam focus said "As your other exams: 5 days before, from your rule" while the exam had none: the rule
   is for exams by their name, and this one's isn't. Each exam now says what the rule gives it (`rule_days`), and
   New exam asks the same of a name (`exam_focus_for`).
Whole system, a scratch Friday on Monday 19 October 2026."""

from pathlib import Path

from friday.commands.exams import unfit_minutes
from friday.core.items import Item
from friday.core.time import format_utc, parse_utc
from tests.commands.helpers import App, new_app


def ran_over(app: App, area: str) -> None:
    """Five of the tag's tasks timed at 75 minutes for an hour each: its estimates are planned 1.25 times."""
    for n in range(5):
        done = app.do("add", title=f"{area} HW {n}", area=area, preset="Assignment", due="2026-10-30T23:59",
                      duration_min=60)["item"]  # fmt: skip
        app.do("done", id=done["id"], actual_min=75)


def tight_exam(tmp_path: Path, busy_until: str) -> tuple[App, dict]:
    app = new_app(tmp_path, now="2026-10-19T12:00")
    ran_over(app, "CHEM 2090")
    exam = app.do("add", title="CHEM 2090 Prelim 3", area="CHEM 2090", preset="Exam", start="2026-10-19T19:00",
                  end="2026-10-19T20:30")["item"]["id"]  # fmt: skip
    if busy_until != "12:00":
        app.do("add", title="Lab", start="2026-10-19T12:00", end=f"2026-10-19T{busy_until}")
    prep = app.do("add", title="CHEM 2090 practice prelim", area="CHEM 2090", preset="Exam prep",
                  due="2026-10-19T19:00", duration_min=240, before=[exam])["item"]  # fmt: skip
    assert prep["cushion"] == 1.25
    app.do("replan")
    [found] = app.do("exams")
    return app, found


def test_the_notes_screenshot_prep_late_yet_planned_to_finish_before_the_exam_says_what_has_no_room(
    tmp_path: Path,
) -> None:
    _, found = tight_exam(tmp_path, "14:00")  # 5h reserved for your 4h; 4h 45m of room before 7pm
    assert found["status"] == "late"
    assert found["planned_finish"] is not None and found["planned_finish"] < "2026-10-19T19:00"  # the screenshot's
    assert found["unfit_min"] == 15


def test_prep_with_room_for_all_of_it_has_nothing_unfit(tmp_path: Path) -> None:
    _, found = tight_exam(tmp_path, "12:00")
    assert (found["status"], found["unfit_min"]) == ("on_track", 0)


def test_unfit_counts_only_minutes_with_no_room_not_minutes_planned_after_an_earlier_due() -> None:
    due = "2026-10-19T03:59Z"
    guide = Item(id=1, title="Study guide", due_utc=due)
    practice = Item(id=2, title="Practice prelim", due_utc="2026-10-19T23:00Z")
    after_due = parse_utc(due) + 30  # its last block ends half an hour after its own due, still before the exam
    late = {1: 1.0, 2: 0.25}  # the guide: 30m after its due and 30m with no room; the practice prelim: 15m no room
    ends = {1: after_due, 2: parse_utc("2026-10-19T22:45Z")}
    assert unfit_minutes([guide, practice], late, ends) == 30 + 15
    assert unfit_minutes([guide], {1: 0.5}, ends) == 0  # only planned after its due: all of it has room
    assert format_utc(after_due) > due


def test_an_exam_says_what_the_rule_gives_it_by_its_name(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    prelim = app.do("add", title="CHEM 2090 Prelim 3", preset="Exam", start="2026-10-23T19:00",
                    end="2026-10-23T20:30")["item"]["id"]  # fmt: skip
    quiz = app.do("add", title="CHEM 2090 Quiz 4", preset="Exam", start="2026-10-24T10:00",
                  end="2026-10-24T11:00")["item"]["id"]  # fmt: skip
    shown = lambda: {e["item"]["id"]: (e["focus_days"], e["rule_days"], e["focus_own"]) for e in app.do("exams")}  # noqa: E731
    assert shown() == {prelim: (None, None, False), quiz: (None, None, False)}  # no rule
    app.do("rule_add", text="focus on exams 5 days before")
    # the rule finds a prelim by its name, not a quiz: "As your other exams" is 5 days for one and none for the other
    assert shown() == {prelim: (5, 5, False), quiz: (None, None, False)}
    each = app.do("settings")["exam_focus_each"]
    app.do("settings_set", key="exam_focus_each", value=each | {str(quiz): 2})
    assert shown()[quiz] == (2, None, True)  # its own days; the rule still gives it none
    assert app.do("exam_focus_for", title="MATH 2940 Prelim 2")["days"] == 5
    assert app.do("exam_focus_for", title="MATH 2940 Quiz 2")["days"] is None
    assert app.do("exam_focus_for", title="")["days"] is None
