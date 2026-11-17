"""A project's templates follow whether you're in school, as its kinds do (17 Nov: "students should not get the same
options as non-students"): a student's Essay and Presentation; out of school a Report, a Presentation and an Event.
Yours once you save or delete one, whichever you are."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)


def templates(app: App) -> list[str]:
    return list(app.do("settings")["templates"])


def out_of_school(app: App) -> None:
    app.do("settings_set", key="school", value=False)


def test_a_student_has_an_essay_and_a_presentation(app: App) -> None:
    assert templates(app) == ["Essay", "Presentation"]


def test_out_of_school_the_templates_are_works(app: App) -> None:
    out_of_school(app)
    assert templates(app) == ["Report", "Presentation", "Event"]
    made = app.do("template_apply", template="Event", title="Team offsite", hours=8)["item"]["id"]
    [project] = [p for p in app.do("projects") if p["item"]["id"] == made]
    assert [c["title"] for c in project["children"]] == ["Plan", "Book", "Invite", "Final checks"]
    assert abs(sum(c["duration_min"] for c in project["children"]) - 480) <= 15 * 4  # each step in quarter hours
    assert all(c["preset"] not in {"Assignment", "Reading", "Exam prep"} for c in project["children"])


def test_a_template_you_saved_keeps_your_list_whichever_you_are(app: App) -> None:
    made = app.do("add", title="Grant", preset="Project", duration_min=600)["item"]["id"]
    app.do("add", title="Budget", duration_min=120, parent_id=made)
    app.do("template_save", project_id=made, name="Grant")
    out_of_school(app)
    assert templates(app) == ["Essay", "Presentation", "Grant"]
