"""Todo List's tasks and Chroma's categories, brought in once (COMBINED.md 24)."""

import json
from pathlib import Path

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
