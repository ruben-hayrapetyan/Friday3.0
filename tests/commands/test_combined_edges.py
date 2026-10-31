"""Edge cases of the combined Friday's planning ports (COMBINED.md 25, 41, 50, 53, 55, 56), beyond the examples in
test_personal_planning.py: what each does not do, as much as what it does."""

import json
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def blocks_of(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def planned_minutes(app: App, item_id: int) -> int:
    def minute(t: str) -> int:
        return int(t[8:10]) * 1440 + int(t[11:13]) * 60 + int(t[14:16])

    return sum(minute(e) - minute(s) for s, e in blocks_of(app, item_id))


def timed(app: App, n: int, minutes: int, actual: int, area: str = "CS 2110", preset: str = "Assignment") -> None:
    for i in range(n):
        item = app.do("add", title=f"{area} past {i}", area=area, preset=preset, due="2026-10-30T23:59",
                      duration_min=minutes)["item"]  # fmt: skip
        app.do("done", id=item["id"], actual_min=actual)


# The learned cushion (41)


def test_no_cushion_from_fewer_than_five_timings(app: App) -> None:
    timed(app, 4, 60, 120)
    new = app.do("add", title="CS 2110 next", area="CS 2110", preset="Assignment", due="2026-10-23T23:59",
                 duration_min=60)["item"]  # fmt: skip
    assert new["cushion"] == 1.0


def test_running_under_never_shortens_your_estimate(app: App) -> None:
    timed(app, 6, 120, 60)
    new = app.do("add", title="CS 2110 next", area="CS 2110", preset="Assignment", due="2026-10-23T23:59",
                 duration_min=120)["item"]  # fmt: skip
    assert new["cushion"] == 1.0
    replan(app.conn, app.now_utc)
    assert planned_minutes(app, new["id"]) == 120


def test_the_cushion_is_capped_at_twice_your_estimate(app: App) -> None:
    timed(app, 6, 60, 240)
    new = app.do("add", title="CS 2110 next", area="CS 2110", preset="Assignment", due="2026-10-23T23:59",
                 duration_min=60)["item"]  # fmt: skip
    assert new["cushion"] == 2.0


def test_the_cushion_belongs_to_its_tag(app: App) -> None:
    timed(app, 6, 60, 90, area="CS 2110")
    other = app.do("add", title="MATH 2940 HW 9", area="MATH 2940", preset="Assignment", due="2026-10-23T23:59",
                   duration_min=60)["item"]  # fmt: skip
    assert other["cushion"] == 1.0


def test_friday_s_own_guess_gets_no_cushion(app: App) -> None:
    timed(app, 6, 60, 90)
    guessed = app.do("add", title="CS 2110 next", area="CS 2110", preset="Assignment", due="2026-10-23T23:59")["item"]
    assert guessed["cushion"] == 1.0


# Pointless if late (50)


def test_work_with_no_due_is_never_pointless_late(app: App) -> None:
    prep = app.do("add", title="General review", preset="Exam prep", duration_min=60, firmness="none")["item"]
    assert prep["pointless_late"] is False


def test_title_patterns_in_settings_make_work_pointless_late(app: App) -> None:
    app.do("settings_set", key="pointless_late", value={"kinds": ["Exam prep"], "titles": ["housing form"]})
    form = app.do("add", title="Submit housing form", due="2026-10-20T12:00", duration_min=30)["item"]
    other = app.do("add", title="Submit essay", due="2026-10-20T12:00", duration_min=30)["item"]
    assert form["pointless_late"] and not other["pointless_late"]


def test_a_broken_title_pattern_matches_nothing(app: App) -> None:
    app.do("settings_set", key="pointless_late", value={"titles": ["(unclosed"]})
    item = app.do("add", title="anything (unclosed", due="2026-10-20T12:00", duration_min=30)["item"]
    assert item["pointless_late"] is False


def test_switching_exam_prep_off_in_settings(app: App) -> None:
    app.do("settings_set", key="pointless_late", value={"kinds": []})
    prep = app.do("add", title="Quiz prep", preset="Exam prep", due="2026-10-20T12:00", duration_min=60)["item"]
    assert prep["pointless_late"] is False


def test_pointless_late_work_that_can_t_fit_is_left_off_not_planned_late(app: App) -> None:
    app.do("add", title="Class", when="fixed", start="2026-10-19T09:00", end="2026-10-19T11:45")
    prep = app.do("add", title="Quiz prep", preset="Exam prep", due="2026-10-19T12:00", duration_min=120)["item"]
    replan(app.conn, app.now_utc)
    assert all(end <= "2026-10-19T12:00" for _, end in blocks_of(app, prep["id"]))
    assert planned_minutes(app, prep["id"]) <= 15


# Exam prep due at its exam (50)


def test_exam_prep_ignores_an_exam_more_than_three_days_before_its_due(app: App) -> None:
    app.do("add", title="MATH 2940 Quiz 3", when="fixed", start="2026-10-19T14:00", end="2026-10-19T15:00")
    prep = app.do("add", title="MATH 2940 quiz prep", preset="Exam prep", due="2026-10-23T23:59",
                  duration_min=120)["item"]  # fmt: skip
    replan(app.conn, app.now_utc)
    assert any(end > "2026-10-19T14:00" for _, end in blocks_of(app, prep["id"]))


def test_exam_prep_ignores_another_course_s_exam(app: App) -> None:
    app.do("add", title="CHEM 2090 Prelim", when="fixed", start="2026-10-21T10:00", end="2026-10-21T11:30")
    prep = app.do("add", title="MATH 2940 prelim prep", preset="Exam prep", due="2026-10-21T23:59",
                  duration_min=120)["item"]  # fmt: skip
    app.do("add", title="Fill", when="fixed", start="2026-10-19T09:00", end="2026-10-21T12:00")
    replan(app.conn, app.now_utc)
    assert blocks_of(app, prep["id"]) and all(start >= "2026-10-21T12:00" for start, _ in blocks_of(app, prep["id"]))


def test_exam_prep_is_due_at_the_first_of_two_exams(app: App) -> None:
    app.do("add", title="MATH 2940 Quiz 3", when="fixed", start="2026-10-21T10:00", end="2026-10-21T10:30")
    app.do("add", title="MATH 2940 Quiz 4", when="fixed", start="2026-10-22T10:00", end="2026-10-22T10:30")
    prep = app.do("add", title="MATH 2940 quiz prep", preset="Exam prep", due="2026-10-22T23:59",
                  duration_min=60)["item"]  # fmt: skip
    replan(app.conn, app.now_utc)
    assert all(end <= "2026-10-21T10:00" for _, end in blocks_of(app, prep["id"]))


# Parts of a set (53)


def test_parts_due_on_different_days_are_not_tied(app: App) -> None:
    a = app.do("add", title="PS 7 odds", preset="Assignment", due="2026-10-21T23:59", duration_min=60)["item"]
    b = app.do("add", title="PS 7 evens", preset="Assignment", due="2026-10-22T23:59", duration_min=60)["item"]
    snapshot = take_snapshot(app.conn, app.now_utc)
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    problem = build_problem(build_input(snapshot))
    assert problem.items[f"item:{a['id']}"].depends_on == () and problem.items[f"item:{b['id']}"].depends_on == ()


def test_three_parts_go_in_their_numbers_order(app: App) -> None:
    ids = {}
    for n in (10, 9, 8):
        ids[n] = app.do("add", title=f"Psych ch {n}", preset="Reading", due="2026-10-22T23:59", duration_min=45)[
            "item"
        ]["id"]
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert [d.key for d in problem.items[f"item:{ids[9]}"].depends_on] == [f"item:{ids[8]}"]
    assert [d.key for d in problem.items[f"item:{ids[10]}"].depends_on] == [f"item:{ids[9]}"]
    assert problem.items[f"item:{ids[8]}"].depends_on == ()


def test_parts_you_tied_yourself_are_left_as_you_tied_them(app: App) -> None:
    a = app.do("add", title="PS 7 odds", preset="Assignment", due="2026-10-22T23:59", duration_min=60)["item"]
    b = app.do("add", title="PS 7 evens", preset="Assignment", due="2026-10-22T23:59", duration_min=60)["item"]
    app.do("depend", item_id=b["id"], depends_on_id=a["id"])  # evens after odds, against the title order
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert [d.key for d in problem.items[f"item:{b['id']}"].depends_on] == [f"item:{a['id']}"]
    assert problem.items[f"item:{a['id']}"].depends_on == ()


# Guessed kinds (55)


def test_an_explicit_kind_or_tag_is_never_overwritten(app: App) -> None:
    item = app.do("add", title="MATH 2940 HW 7", preset="Reading", area="Math", due="2026-10-22T23:59")["item"]
    assert (item["preset"], item["area"]) == ("Reading", "Math")


def test_events_are_never_given_a_kind_or_tag_by_their_title(app: App) -> None:
    event = app.do("add", title="MATH 2940 Prelim", when="fixed", start="2026-10-21T19:30", end="2026-10-21T21:00")
    assert event["item"]["area"] is None


def test_the_add_box_shows_the_guess(app: App) -> None:
    fields = app.do("parse", text="MATH 2940 HW 7 due fri")["fields"]
    assert (fields["preset"], fields["area"]) == ("Assignment", "MATH 2940")


# Events search (C4)


def test_dropped_events_are_not_found(app: App) -> None:
    gone = app.do("add", title="Cancelled talk", when="fixed", start="2026-10-21T18:00", end="2026-10-21T19:00")
    app.do("drop", id=gone["item"]["id"])
    assert app.do("events", text="talk") == []


def test_events_search_keeps_to_its_limit(app: App) -> None:
    for n in range(5):
        app.do("add", title=f"Meeting {n}", when="fixed", start=f"2026-10-2{n}T18:00", end=f"2026-10-2{n}T19:00")
    assert len(app.do("events", text="meeting", limit=3)) == 3


# Import (24)


def test_import_with_neither_file_says_so(app: App, tmp_path: Path) -> None:
    with pytest.raises(FieldError, match="found neither"):
        app.do("import_personal", todos_path=str(tmp_path / "nope.json"), categories_path=str(tmp_path / "nope2.json"))


def test_import_skips_empty_titles_and_keeps_existing_categories(app: App, tmp_path: Path) -> None:
    (tmp_path / "t.json").write_text(json.dumps([{"id": "Z", "title": "  ", "horizon": "shortTerm"}]))
    (tmp_path / "c.json").write_text(json.dumps({"categories": [{"name": "X", "color": "red", "pattern": "x"}]}))
    app.do("settings_set", key="categories", value={"categories": [{"name": "Mine", "color": "blue", "pattern": "m"}]})
    out = app.do("import_personal", todos_path=str(tmp_path / "t.json"), categories_path=str(tmp_path / "c.json"))
    assert out["message"] == "Imported 0 tasks from Todo List"
    assert [c["name"] for c in app.do("settings")["categories"]["categories"]] == ["Mine"]


# Skips (56)


def test_no_skips_are_offered_when_nothing_is_late(app: App) -> None:
    app.do("add", title="Poker night", when="fixed", start="2026-10-19T19:00", end="2026-10-19T23:00")
    app.do("add", title="Essay", preset="Assignment", due="2026-10-22T23:59", duration_min=60)
    replan(app.conn, app.now_utc)
    assert app.do("triage")["options"] == []


def test_events_after_the_late_work_is_due_are_not_offered(app: App) -> None:
    app.do("add", title="Club meeting", when="fixed", start="2026-10-19T09:00", end="2026-10-19T23:00")
    app.do("add", title="Poker night", when="fixed", start="2026-10-20T19:00", end="2026-10-20T23:00")
    app.do("add", title="Problem set", preset="Assignment", due="2026-10-19T23:00", duration_min=120)
    replan(app.conn, app.now_utc)
    assert "Poker night" not in [o["skip_title"] for o in app.do("triage")["options"]]


def test_a_rating_from_the_ai_wins_over_the_title(app: App) -> None:
    app.do("add", title="Robotics", when="fixed", start="2026-10-19T09:00", end="2026-10-19T23:00")
    app.do("add", title="Problem set", preset="Assignment", due="2026-10-19T23:00", duration_min=120)
    app.conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'event_ratings', ?)",
        [json.dumps({"robotics": {"level": "required", "reason": "team relies on you"}})],
    )
    replan(app.conn, app.now_utc)
    assert "Robotics" not in [o["skip_title"] for o in app.do("triage")["options"]]


# Other ways (25)


def test_no_other_ways_for_an_empty_week(app: App) -> None:
    replan(app.conn, app.now_utc)
    assert app.do("other_ways")["ways"] == []


def test_a_picked_way_lapses_after_a_week(app: App) -> None:
    app.do("other_way_pick", weights={"energy": 3.0}, seed=1, rule_totals={})
    snapshot = take_snapshot(app.conn, app.now_utc)
    assert snapshot.cold_once
    assert next(r for r in snapshot.settings["rules"] if r.name == "energy").weight == 3.0
    later = take_snapshot(app.conn, app.now_utc + 8 * 1440)
    assert next(r for r in later.settings["rules"] if r.name == "energy").weight == 1.0


def test_the_cold_start_is_used_once(app: App) -> None:
    app.do("add", title="Essay", preset="Assignment", due="2026-10-22T23:59", duration_min=60)
    app.do("other_way_pick", weights={}, seed=1, rule_totals={})
    replan(app.conn, app.now_utc)
    assert not take_snapshot(app.conn, app.now_utc).cold_once


def test_a_way_is_described_by_what_it_gains_and_gives_up() -> None:
    from friday.commands.ways import difference

    rules = ("weekends", "chunk_cost", "late_night", "energy")
    mine = {"weekends": 500, "chunk_cost": 300, "late_night": 0, "energy": 50}
    other = {"weekends": 100, "chunk_cost": 200, "late_night": 400, "energy": 50}
    assert difference(mine, other, rules) == "Freer weekends, fewer, longer sittings; but more late-night work"
    assert difference(mine, mine, rules) == "Much the same, arranged differently"
    assert difference(mine, {**mine, "late_night": 10}, rules) == "Arranged differently; but more late-night work"


# Exam focus (38)


def focused(app: App) -> None:
    app.do("settings_set", key="exam_focus", value={"on": True, "days_before": 3})
    app.do("add", title="MATH 2940 Prelim 2", when="fixed", start="2026-10-21T19:30", end="2026-10-21T21:00")


def test_other_courses_wait_until_the_exam_is_over(app: App) -> None:
    focused(app)
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-25T23:59", duration_min=120)[
        "item"
    ]
    replan(app.conn, app.now_utc)
    assert blocks_of(app, essay["id"]) and all(start >= "2026-10-21T21:00" for start, _ in blocks_of(app, essay["id"]))


def test_the_exam_s_own_course_and_its_prep_are_not_held_back(app: App) -> None:
    focused(app)
    hw = app.do("add", title="MATH 2940 HW 8", preset="Assignment", due="2026-10-25T23:59", duration_min=60)["item"]
    replan(app.conn, app.now_utc)
    assert any(start < "2026-10-21T19:30" for start, _ in blocks_of(app, hw["id"]))


def test_work_that_couldn_t_wait_is_done_before_the_exam(app: App) -> None:
    focused(app)
    soon = app.do("add", title="HIST 1200 response", preset="Assignment", due="2026-10-22T12:00", duration_min=120)[
        "item"
    ]
    replan(app.conn, app.now_utc)
    assert any(start < "2026-10-21T19:30" for start, _ in blocks_of(app, soon["id"]))


def test_exam_focus_is_off_until_you_ask_for_it(app: App) -> None:
    app.do("add", title="MATH 2940 Prelim 2", when="fixed", start="2026-10-21T19:30", end="2026-10-21T21:00")
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-25T23:59", duration_min=120)[
        "item"
    ]
    app.do("add", title="Fill the week", when="fixed", start="2026-10-21T21:00", end="2026-10-26T00:00")
    replan(app.conn, app.now_utc)
    assert any(start < "2026-10-21T19:30" for start, _ in blocks_of(app, essay["id"]))


def test_an_exam_more_than_the_focus_days_away_holds_nothing_back(app: App) -> None:
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    app.do("settings_set", key="exam_focus", value={"on": True, "days_before": 1})
    app.do("add", title="MATH 2940 Prelim 2", when="fixed", start="2026-10-23T19:30", end="2026-10-23T21:00")
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-26T12:00", duration_min=60)["item"]
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert problem.items[f"item:{essay['id']}"].release_utc in (None, app.now_utc)
    later = build_problem(build_input(take_snapshot(app.conn, app.now_utc + 4 * 1440)))  # Friday morning: focusing
    assert (
        later.items[f"item:{essay['id']}"].release_utc is not None
        and later.items[f"item:{essay['id']}"].release_utc > app.now_utc + 4 * 1440
    )


# Split preference (38)


def test_one_go_makes_splitting_cost_more_except_what_you_split_first(app: App) -> None:
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input

    essay = app.do("add", title="Essay", preset="Assignment", due="2026-10-22T23:59", duration_min=180)["item"]
    reading = app.do("add", title="Psych reading", preset="Reading", due="2026-10-22T23:59", duration_min=120)["item"]
    before = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items
    app.do("settings_set", key="sittings", value={"one_go": True, "split_first": ["Assignment"]})
    after = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items
    e, r = f"item:{essay['id']}", f"item:{reading['id']}"
    assert after[e].chunk_cost < before[e].chunk_cost and after[r].chunk_cost > before[r].chunk_cost
    assert 0 <= after[r].chunk_cost <= 1


# Folding one category into another (31 Oct: "remove campus events as a category ... classify all of them under
# social (unless they are meals)")

CATEGORIES = {
    "categories": [
        {"name": "Campus events", "slug": "campus", "color": "yellow", "pattern": "convocation|swim test"},
        {"name": "Social", "slug": "social", "color": "pink", "pattern": "poker|party"},
    ],
    "filter": {"label": "Hidden", "pattern": "office hours", "except": ["campus"]},
}


def category_of(app: App, item_id: int) -> str | None:
    return app.do("item", id=item_id)["item"]["category"]


def test_a_merged_category_takes_its_words_and_its_guessed_events_along_but_not_a_meal(app: App) -> None:
    app.do("settings_set", key="categories", value=CATEGORIES)
    convocation, hockey, dinner = (
        app.do("add", title=title, when="fixed", start=f"2026-10-19T{at}", end=f"2026-10-19T{at[:2]}:45")["item"]["id"]
        for title, at in (("Convocation", "09:00"), ("Hockey Game", "13:00"), ("Club dinner", "18:00"))
    )
    guesses = {"hockey game": {"level": "optional", "category": "Campus events"}}
    guesses["club dinner"] = {"level": "optional", "category": "Campus events"}
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'event_ratings', ?)", [json.dumps(guesses)])
    replan(app.conn, app.now_utc)
    assert category_of(app, hockey) == "Campus events"

    merged = app.full("category_merge", payload={"name": "Campus events", "into": "Social"})
    assert merged.result["message"] == "Campus events joined Social: 1 event moved"
    settings = app.do("settings")["categories"]
    assert [c["name"] for c in settings["categories"]] == ["Social"]
    assert settings["filter"]["except_"] == ["social"]
    assert category_of(app, convocation) == "Social"  # by its words
    assert category_of(app, hockey) == "Social"  # by Claude's guess, moved
    assert category_of(app, dinner) is None  # a meal: asked again, not made Social

    app.do("undo", command_id=merged.command_id)
    assert [c["name"] for c in app.do("settings")["categories"]["categories"]] == ["Campus events", "Social"]
    assert category_of(app, hockey) == "Campus events"


def test_merging_needs_two_categories_that_exist(app: App) -> None:
    app.do("settings_set", key="categories", value=CATEGORIES)
    with pytest.raises(FieldError):
        app.do("category_merge", name="Sports", into="Social")
    with pytest.raises(FieldError):
        app.do("category_merge", name="Social", into="Social")
