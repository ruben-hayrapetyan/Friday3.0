"""personal's planning behaviours in m16's engine (COMBINED.md 49–55): late tasks counted and priced by the square,
work pointless once late never planned after its due, exam prep due at its exam, and parts of a set in order."""

from pathlib import Path

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


def blocks_of(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def test_exam_prep_is_never_planned_after_its_due(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    prep = app.do("add", title="Chem quiz prep", preset="Exam prep", due="2026-10-19T10:00", duration_min=180)
    essay = app.do("add", title="Essay draft", preset="Assignment", due="2026-10-19T10:00", duration_min=180)
    replan(app.conn, app.now_utc)
    assert prep["item"]["pointless_late"] and not essay["item"]["pointless_late"]
    assert all(end <= "2026-10-19T10:00" for _, end in blocks_of(app, prep["item"]["id"]))
    assert any(end > "2026-10-19T10:00" for _, end in blocks_of(app, essay["item"]["id"]))  # late, but still done


def test_your_say_on_an_item_wins_over_its_kind(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    prep = app.do("add", title="Chem quiz prep", preset="Exam prep", due="2026-10-19T10:00", duration_min=180)
    edited = app.do("edit", id=prep["item"]["id"], expires=False)["item"]
    assert edited["expires"] is False and not edited["pointless_late"]
    form = app.do("add", title="Housing form", due="2026-10-19T10:00", duration_min=180, expires=True)["item"]
    assert form["pointless_late"]
    replan(app.conn, app.now_utc)
    assert any(end > "2026-10-19T10:00" for _, end in blocks_of(app, prep["item"]["id"]))
    assert all(end <= "2026-10-19T10:00" for _, end in blocks_of(app, form["id"]))


def test_exam_prep_is_due_when_its_courses_exam_starts(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="MATH 2940 Quiz 3", when="fixed", start="2026-10-21T10:10", end="2026-10-21T11:00")
    prep = app.do("add", title="MATH 2940 quiz prep", preset="Exam prep", due="2026-10-21T23:59", duration_min=120)
    replan(app.conn, app.now_utc)
    placed = blocks_of(app, prep["item"]["id"])
    assert placed and all(end <= "2026-10-21T10:10" for _, end in placed)


def test_parts_of_a_set_are_done_one_after_the_other(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    odds = app.do("add", title="PS 7 odds", preset="Assignment", due="2026-10-22T23:59", duration_min=120)["item"]
    evens = app.do("add", title="PS 7 evens", preset="Assignment", due="2026-10-22T23:59", duration_min=120)["item"]
    replan(app.conn, app.now_utc)
    first, second = blocks_of(app, evens["id"]), blocks_of(app, odds["id"])  # "evens" before "odds", by title
    assert first and second and max(end for _, end in first) <= min(start for start, _ in second)


def test_late_tasks_is_a_default_deadline_rule(tmp_path: Path) -> None:
    rules = {r["name"]: r for r in new_app(tmp_path).do("rules")}
    assert (rules["late_tasks"]["sentence"], rules["late_tasks"]["strength"]) == (
        "Fewer tasks late, and none very late",
        "Always",
    )


def test_your_estimate_is_planned_exactly_until_you_consistently_run_over(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    first = app.do("add", title="CS 2110 A1", area="CS 2110", preset="Assignment", due="2026-10-30T23:59",
                   duration_min=60)["item"]  # fmt: skip
    assert first["cushion"] == 1.0
    for n in range(2, 7):
        done = app.do("add", title=f"CS 2110 A{n}", area="CS 2110", preset="Assignment", due="2026-10-30T23:59",
                      duration_min=60)["item"]  # fmt: skip
        app.do("done", id=done["id"], actual_min=90)
    new = app.do("add", title="CS 2110 A7", area="CS 2110", preset="Assignment", due="2026-10-23T23:59",
                 duration_min=60)["item"]  # fmt: skip
    assert new["cushion"] == 1.5 and new["duration_min"] == 60  # your estimate stays yours
    replan(app.conn, app.now_utc)
    planned = sum(
        (int(e[11:13]) * 60 + int(e[14:16])) - (int(s[11:13]) * 60 + int(s[14:16]))
        for s, e in blocks_of(app, new["id"])
    )
    assert planned == 90
    app.do("settings_set", key="estimate", value={"cushion": False})
    assert app.do("item", id=new["id"])["item"]["cushion"] == 1.0
