"""Late work's last chance (8 Nov: "If math homework becomes overdue, it must be done before sunday"). Glass box: the
reader's wordings, "math homework" as homework for math, the cutoff day from a due, the wall in pruning and in the
allocator's days. Black box through the commands: the rule added in words, then overdue math homework with Friday and
Saturday full goes unplanned rather than onto Sunday, while other overdue homework still goes there; with room, it's
done Friday. The whole system is tests/system/test_late_cutoff_system.py."""

from pathlib import Path

import pytest

from friday.core.rule_late import read_late_cutoff
from friday.core.rule_text import course_and_kind, read, scope_of, sentence, spec
from friday.core.time import format_utc, parse_local, parse_utc, to_utc
from friday.planner.late_cutoff import cutoff_after
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

PRESETS = ["Assignment", "Reading", "Exam prep", "Chore", "Errand"]
SAID = "If math homework becomes overdue, it must be done before sunday"


def utc(local: str) -> int:
    return to_utc(parse_local(local), TZ)


class TestReading:
    @pytest.mark.parametrize(
        ("text", "subject", "rel", "day"),
        [
            (SAID, "math homework", "before", "sun"),
            ("if my essay is late, finish it by friday", "essay", "on", "fri"),
            ("overdue readings have to be finished by Sat.", "readings", "on", "sat"),
            ("math homework can be late but it must be done by sunday", "math homework", "on", "sun"),
            (
                "When chem problem sets get overdue they need to be submitted no later than thursday",
                "chem problem sets",
                "before",
                "thu",
            ),  # fmt: skip
            ("late math hw: done before next monday", "math hw", "before", "mon"),
        ],
    )
    def test_ways_of_saying_it(self, text: str, subject: str, rel: str, day: str) -> None:
        found = read_late_cutoff(text)
        assert found is not None and (found.subject, found.rel, found.days) == (subject, rel, (day,))
        assert read(text) == (found, "Always")

    @pytest.mark.parametrize(
        "text",
        [
            "finish homework before sunday",
            "no work after sunday",
            "math homework is due friday",
            "if late, ok",
            "late night study sessions done by friday",  # a time of night, not lateness (review, 8 Nov)
            "If it is late, done by monday",  # what "it" is isn't said
        ],
    )
    def test_plain_deadlines_and_others_are_not_it(self, text: str) -> None:
        assert read_late_cutoff(text) is None

    def test_its_words_and_its_rule(self) -> None:
        reading, strength = read(SAID)
        assert reading is not None and sentence(reading) == "Overdue math homework is done before Sunday, never later"
        rule = spec(reading, strength, "you:late", [], PRESETS)
        assert rule["type"] == "late_cutoff" and rule["params"] == {"day": "sun", "before": True}
        assert rule["scope"] == {"preset": "Assignment", "title": "math"}


class TestScope:
    @pytest.mark.parametrize(
        ("subject", "scope"),
        [
            ("math homework", {"preset": "Assignment", "title": "math"}),
            ("chem problem sets", {"preset": "Assignment", "title": "chem"}),
            ("history readings", {"preset": "Reading", "title": "history"}),
            ("homework", {"preset": "Assignment"}),
            ("essay", {"title": "essay"}),
        ],
    )
    def test_a_course_and_a_kind(self, subject: str, scope: dict) -> None:
        assert (course_and_kind(subject, [], PRESETS) or scope_of(subject, [], PRESETS)) == scope

    def test_a_tag_and_a_kind(self) -> None:
        assert course_and_kind("school homework", ["School"], PRESETS) == {"preset": "Assignment", "area": "School"}

    def test_other_rules_read_their_subject_as_before(self) -> None:
        """Review (8 Nov): read this way for every rule, it narrowed what existing wordings reached."""
        assert scope_of("math homework", [], PRESETS) == {"title": "math homework"}
        assert course_and_kind("practice exam", [], [*PRESETS, "Exam"]) is None  # a kind of its own


class TestCutoffDay:
    def test_before_sunday_is_the_start_of_the_sunday_after_the_due(self) -> None:
        due = utc("2026-11-05T23:59")  # Thursday
        assert cutoff_after(due, "sun", True, TZ) == utc("2026-11-08T00:00")

    def test_by_sunday_is_the_end_of_it(self) -> None:
        assert cutoff_after(utc("2026-11-05T23:59"), "sun", False, TZ) == utc("2026-11-09T00:00")

    def test_due_on_a_sunday_before_sunday_is_the_next_one_by_sunday_the_same(self) -> None:
        due = utc("2026-11-08T12:00")
        assert cutoff_after(due, "sun", True, TZ) == utc("2026-11-15T00:00")
        assert cutoff_after(due, "sun", False, TZ) == utc("2026-11-09T00:00")

    def test_in_your_time_not_utc(self) -> None:
        due = parse_utc("2026-11-07T03:00Z")  # Friday 10pm in New York, Saturday in UTC
        assert format_utc(cutoff_after(due, "sat", True, TZ)) == format_utc(utc("2026-11-07T00:00"))  # not a week on


class TestWalls:
    def test_pruning_and_the_allocator_leave_out_the_time_after(self, tmp_path: Path) -> None:
        from friday.planner.build import build_problem
        from friday.planner.prepare import build_input
        from friday.planner.snapshot import take_snapshot

        app = overdue_math(tmp_path, busy=False)
        app.do("rule_add", text=SAID)
        problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc, 1)))
        (math,) = [i for i in problem.items.values() if i.title.startswith("Math")]
        assert math.cutoff_utc == utc("2026-11-08T00:00")
        grid = problem.grid
        assert math.allowed and all(int(grid.start[s]) < math.cutoff_utc for s in math.allowed)
        (other,) = [i for i in problem.items.values() if i.title.startswith("Chem")]
        assert other.cutoff_utc is None and any(int(grid.start[s]) >= utc("2026-11-08T00:00") for s in other.allowed)


def overdue_math(tmp_path: Path, busy: bool) -> App:
    """Friday 6 Nov, 9am: Math 1920 HW10 (3 h) was due last night, and so was a Chem problem set; with `busy`, a trip
    fills Friday and Saturday."""
    app = new_app(tmp_path, now="2026-11-06T09:00", horizon_days=7)
    for title in ("Math 1920 HW10", "Chem 2090 Problem Set 9"):
        app.do("add", title=title, preset="Assignment", duration_min=180, due="2026-11-05T23:59")
    if busy:
        app.do("add", text="Trip", when="fixed", start="2026-11-06T09:00", end="2026-11-07T23:59")
    return app


def planned(app: App, prefix: str) -> list[tuple[int, int]]:
    ids = {r["id"] for r in app.table("items") if r["title"].startswith(prefix)}
    found = [b for b in app.table("blocks") if b["item_id"] in ids]
    return sorted((parse_utc(b["start_utc"]), parse_utc(b["end_utc"])) for b in found)


SUNDAY = utc("2026-11-08T00:00")


def test_with_friday_and_saturday_full_it_is_left_off_rather_than_put_on_sunday(tmp_path: Path) -> None:
    (tmp_path / "without").mkdir()
    (tmp_path / "with").mkdir()
    without = overdue_math(tmp_path / "without", busy=True)
    replan(without.conn, without.now_utc)
    assert planned(without, "Math") and planned(without, "Math")[0][0] >= SUNDAY  # as before: Sunday, late
    app = overdue_math(tmp_path / "with", busy=True)
    app.do("rule_add", text=SAID)
    replan(app.conn, app.now_utc)
    assert planned(app, "Math") == []  # its last chance has no room: not on Sunday
    assert planned(app, "Chem")[0][0] >= SUNDAY  # other overdue homework isn't covered


def test_with_room_it_is_done_before_sunday(tmp_path: Path) -> None:
    app = overdue_math(tmp_path, busy=False)
    app.do("rule_add", text=SAID)
    replan(app.conn, app.now_utc)
    blocks = planned(app, "Math")
    assert sum(b - a for a, b in blocks) >= 180 and all(b <= SUNDAY for _, b in blocks)


def test_the_rules_page_says_what_it_does_and_moving_it_after_names_the_wall(tmp_path: Path) -> None:
    app = overdue_math(tmp_path, busy=False)
    said = app.do("rule_read", text=SAID)
    assert said["reading"]["kind"] == "late_cutoff" and said["strength"] == "Always"
    assert "never on a later day" in said["effect"]
    app.do("rule_add", text=SAID)
    replan(app.conn, app.now_utc)
    rules = [r for r in app.do("settings")["rules"] if r["type"] == "late_cutoff"]
    assert [r["reason"] for r in rules] == ["Overdue math homework is done before Sunday, never later"]
    ids = {r["id"] for r in app.table("items") if r["title"].startswith("Math")}
    block = next(b for b in app.table("blocks") if b["item_id"] in ids)
    from friday.core.time import format_local, to_local

    key = f"T{block['item_id']}@{format_local(to_local(parse_utc(block['start_utc']), TZ))}"
    answer = app.do("why_not", key=key, start="2026-11-08T14:00")
    assert "Past the last day it can be done late" in (answer["wall"] or "")


def test_switched_off_it_no_longer_holds(tmp_path: Path) -> None:
    app = overdue_math(tmp_path, busy=True)
    app.do("rule_add", text=SAID)
    rules = app.do("settings")["rules"]
    off = [r | {"enabled": False} if r["type"] == "late_cutoff" else r for r in rules]
    app.do("settings_set", key="rules", value=off)
    replan(app.conn, app.now_utc)
    assert planned(app, "Math")[0][0] >= SUNDAY
