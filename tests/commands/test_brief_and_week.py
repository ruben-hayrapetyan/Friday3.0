"""The morning brief, the weekly look back (in Insights since 27 Oct) and a block settled before the Review.
Notifications, which these tests once lived with, were removed on 27 Oct."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-10-19T08:05", horizon_days=3)


def test_a_settled_block_keeps_its_answer_through_the_review(app: App) -> None:
    item = app.do("add", text="essay due tue 17:00 ~1h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    key = f"T{item}@2026-10-19T09:00"
    app.do("settle", block_key=key, status="partial", share=0.5)
    assert app.do("review")["settled"] == {key: 30}
    app.do("review_submit")
    assert app.do("item", id=item)["item"]["done_min"] == 30


def test_the_brief_names_todays_big_rocks(app: App) -> None:
    app.do("add", text="essay due tue 17:00 ~2h")
    app.do("add", text="lecture at mon 14:00 for 1h")
    replan(app.conn, app.now_utc)
    brief = app.do("brief")
    assert [r["title"] for r in brief["rocks"]] == ["essay"] and len(brief["fixed"]) == 1
    assert brief["text"].startswith(brief["summary"]) and "essay" in brief["text"]


def test_the_week_compares_plan_and_record_by_area_and_scores_deadlines(app: App) -> None:
    app.do("area_add", name="CS")
    item = app.do("add", text="PS1 #CS due mon 17:00 ~1h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.do("log", id=item, start="2026-10-19T09:00", end="2026-10-19T10:30")
    app.at("2026-10-19T11:00").do("done", id=item)
    week = app.do("week_review")
    assert (week["start"], week["end"]) == ("2026-10-19", "2026-10-25")
    assert [(a["area"], a["actual_h"]) for a in week["areas"]] == [("CS", 1.5)]
    assert [(d["title"], d["outcome"]) for d in week["deadlines"]] == [("PS1", "on_time")]
    assert week["moves"] == 1


def test_the_weekly_review_lists_finished_carried_and_coming_and_keeps_a_note(app: App) -> None:
    done = app.do("add", text="PS1 due mon 17:00 ~1h")["item"]["id"]
    app.do("add", text="essay due mon 23:00 ~3h")  # planned today, so it carries over
    app.do("add", title="next essay", due="2026-10-27T17:00", duration_min=60)
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T11:00").do("done", id=done)
    app.do("week_note", week="2026-10-19", feel="Busy", notes="Start essays earlier")
    week = app.do("week_review")
    assert [f["title"] for f in week["finished"]] == ["PS1"]
    assert [c["title"] for c in week["carried"]] == ["essay"]
    assert [c["title"] for c in week["coming"]] == ["next essay"]
    assert week["note"] == {"feel": "Busy", "notes": "Start essays earlier"}


def test_where_the_time_went_names_courses_kinds_and_the_biggest_to_dos(app: App) -> None:
    # 31 Oct: with no tags, one "No tag" row held the whole week and said nothing
    chem = app.do("add", text="Chem 2090 Problem Set 9 due wed 17:00 ~2h")["item"]["id"]
    app.do("add", text="Chem Chapter 13 due thu 17:00 ~1h")
    errand = app.do("add", title="Laundry", preset="Errand", duration_min=60)["item"]["id"]
    app.do("pin", id=chem, start="2026-10-19T09:00", kind="locked")
    app.do("pin", id=errand, start="2026-10-19T13:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.do("log", id=chem, start="2026-10-19T09:00", end="2026-10-19T10:30")
    groups = app.at("2026-10-19T11:00").do("week_review")["groups"]
    rows = {g["name"]: g for g in groups}
    assert rows["Chem"]["by"] == "subject" and rows["Chem"]["actual_h"] == 1.5
    assert rows["Chem"]["items"][0]["title"] == "Chem 2090 Problem Set 9"
    assert rows["Errands"]["by"] == "kind" and rows["Errands"]["preset"] == "Errand"
    assert "No area" not in rows and "No tag" not in rows
