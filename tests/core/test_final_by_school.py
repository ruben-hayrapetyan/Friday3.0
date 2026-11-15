"""'final' alone is an exam to someone in school, not to anyone else (15 Nov, the user: "regarding the final exam
thing, it should also depend on whether you marked student or not in your bio"); "final exam" is one either way."""

import sqlite3
from pathlib import Path

import pytest

from friday.core.calendars import STARTER_CATEGORIES, Category, CategorySettings, category_of
from friday.planner.store import load_settings
from tests.commands.helpers import new_app


def exam(title: str, school: bool, categories: tuple[Category, ...] = STARTER_CATEGORIES) -> bool:
    found = category_of(title, CategorySettings(categories=categories, school=school))
    return found is not None and found.slug == "exam"


@pytest.mark.parametrize("title", ["math final", "MATH 1920 Final", "CHEM finals week"])
def test_a_final_is_an_exam_in_school_only(title: str) -> None:
    assert exam(title, school=True) and not exam(title, school=False)


@pytest.mark.parametrize("title", ["final exam", "Final Exam", "AWS certification exam", "Q3 deadline", "midterm"])
def test_an_exam_that_says_so_is_one_either_way(title: str) -> None:
    assert exam(title, school=True) and exam(title, school=False)


def test_a_pattern_you_wrote_is_read_as_written() -> None:
    mine = (Category(name="Exam", slug="exam", color="red", pattern=r"\bfinals?\b"),)
    assert exam("Q4 final", school=False, categories=mine)


def test_the_school_setting_reaches_the_categories(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    conn: sqlite3.Connection = app.conn
    assert load_settings(conn)["categories"].school is True
    app.do("settings_set", key="school", value=False)
    assert load_settings(conn)["categories"].school is False
    assert "school" not in load_settings(conn)["categories"].model_dump()  # never saved with the categories
