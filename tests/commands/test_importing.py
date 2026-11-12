"""Todo List's tasks and Chroma's categories, brought in once (COMBINED.md 24)."""

import json
from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import new_app

TODOS = [
    {"id": "A", "title": "Email professors for research", "bucket": "emails", "horizon": "shortTerm", "isDone": False,
     "dueDate": "2026-11-04T04:59:00Z"},
    {"id": "B", "title": "CS 2110 A5: Graphs", "bucket": "assignments", "horizon": "shortTerm", "isDone": False,
     "dueDate": "2026-10-23T03:59:00Z"},
    {"id": "C", "title": "Learn Rust", "horizon": "longTerm", "isDone": False},
    {"id": "D", "title": "Old essay", "bucket": "assignments", "horizon": "shortTerm", "isDone": True},
    {"id": "E", "title": "Psych ch. 7", "bucket": "readings", "horizon": "shortTerm", "isDone": False},
]  # fmt: skip
CATEGORIES = {
    "categories": [{"name": "Classes", "slug": "class", "color": "blue", "pattern": r"\blec\b"}],
    "filter": {"label": "TA hours", "pattern": "office hours", "except": ["faculty"]},
}


def files(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "todos.json").write_text(json.dumps(TODOS))
    (tmp_path / "categories.json").write_text(json.dumps(CATEGORIES))
    return {"todos_path": str(tmp_path / "todos.json"), "categories_path": str(tmp_path / "categories.json")}


def test_open_tasks_come_in_once_with_their_dues_lists_and_kinds(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    out = app.do("import_personal", **files(tmp_path))
    assert out["message"] == "Imported 4 tasks from Todo List and 1 categories from Chroma"
    items = {i["title"]: i for i in app.do("items")}
    assert set(items) == {"Email professors for research", "CS 2110 A5: Graphs", "Learn Rust", "Psych ch. 7"}
    assert items["Email professors for research"]["due"] == "2026-11-03T23:59"  # 04:59Z is 23:59 in New York
    assert (
        items["Email professors for research"]["preset"],
        items["Email professors for research"]["duration_min"],
    ) == ("Errand", 15)
    assert (items["CS 2110 A5: Graphs"]["preset"], items["CS 2110 A5: Graphs"]["area"]) == ("Assignment", "CS 2110")
    assert items["Psych ch. 7"]["preset"] == "Reading"
    assert items["Learn Rust"]["long_term"] and not items["Psych ch. 7"]["long_term"]
    again = app.do("import_personal", **files(tmp_path))
    assert again["message"] == "Imported 0 tasks from Todo List" and len(app.do("items")) == 4


def test_categories_come_in_only_when_you_have_none(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("import_personal", **files(tmp_path))
    settings = app.do("settings")["categories"]
    assert [c["name"] for c in settings["categories"]] == ["Classes"] and settings["filter"]["label"] == "TA hours"


def test_an_assignment_with_no_due_date_comes_in_without_a_deadline(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    todos = [
        {"id": "S", "title": "CS make study guide", "bucket": "assignments", "horizon": "shortTerm", "isDone": False},
        {"id": "T", "title": "Chem pre lab", "bucket": "assignments", "horizon": "shortTerm", "isDone": False},
    ]  # fmt: skip
    (tmp_path / "todos.json").write_text(json.dumps(todos))
    out = app.do(
        "import_personal", todos_path=str(tmp_path / "todos.json"), categories_path=str(tmp_path / "none.json")
    )
    assert out["message"] == "Imported 2 tasks from Todo List"
    items = {i["title"]: i for i in app.do("items")}
    assert items["Chem pre lab"]["preset"] == "Assignment" and items["Chem pre lab"]["firmness"] == "none"


def test_a_task_that_cant_come_in_is_named_and_the_rest_still_do(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    todos = [
        {"id": "X", "title": "Broken", "dueDate": "next tuesday-ish", "isDone": False},
        {"id": "Y", "title": "Fine", "isDone": False},
    ]
    (tmp_path / "todos.json").write_text(json.dumps(todos))
    paths = {"todos_path": str(tmp_path / "todos.json"), "categories_path": str(tmp_path / "none.json")}
    out = app.do("import_personal", **paths)
    assert out["message"].startswith("Imported 1 task from Todo List. Left out, to add by hand: Broken (")
    assert [i["title"] for i in app.do("items")] == ["Fine"]
    assert app.do("import_personal", **paths)["message"].startswith("Imported 0 tasks")  # Fine isn't added twice


def test_a_file_that_isnt_todo_lists_is_said_not_a_crash(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    none = str(tmp_path / "none.json")
    (tmp_path / "garbled.json").write_text("{not json")
    (tmp_path / "object.json").write_text(json.dumps({"tasks": []}))
    with pytest.raises(FieldError, match="it isn't JSON"):
        app.do("import_personal", todos_path=str(tmp_path / "garbled.json"), categories_path=none)
    with pytest.raises(FieldError, match="not the list of tasks it writes"):
        app.do("import_personal", todos_path=str(tmp_path / "object.json"), categories_path=none)
