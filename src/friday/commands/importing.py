"""Bringing in the two apps Friday replaces, once (COMBINED.md 24): Todo List's open tasks and Chroma's categories.

The server runs on your Mac (COMBINED.md 2), so it reads their files where they are. Tasks keep their title, due
date and list (short or long term); a reading is a Reading, an assignment an Assignment and an email a quick Errand,
the rest are read by their titles like anything you add. Each task is brought in once, however often you run it;
categories only when you have none yet. It is one command, so one Undo takes it all back.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from friday.api.commands import AddInput, Changed, ImportPersonalInput, SettingsSetInput
from friday.commands.items import add
from friday.commands.registry import Ctx, command
from friday.commands.settings import settings_set
from friday.core.items import FieldError
from friday.core.time import format_local, to_local
from friday.planner.store import kv_get

TODOS = Path("~/Documents/Todo List/todos.json")
CATEGORIES = Path("~/Library/Application Support/Chroma/categories.json")


@command("import_personal", affects_plan=True)
def import_personal(ctx: Ctx, inp: ImportPersonalInput) -> Changed:
    """Todo List's open tasks and Chroma's categories, once."""
    todos_file = Path(inp.todos_path or TODOS).expanduser()
    categories_file = Path(inp.categories_path or CATEGORIES).expanduser()
    if not todos_file.exists() and not categories_file.exists():
        raise FieldError("todos_path", f"found neither {todos_file} nor {categories_file}")
    seen = set(kv_get(ctx.conn, "imported_todos", [], ctx.user_id))
    added = 0
    if todos_file.exists():
        for task in json.loads(todos_file.read_text()):
            if task.get("isDone") or task.get("id") in seen or not (task.get("title") or "").strip():
                continue
            add(ctx, AddInput(**task_fields(ctx, task)))
            seen.add(task["id"])
            added += 1
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "imported_todos"}, {"value": json.dumps(sorted(seen))})
    rules = 0
    if categories_file.exists() and not ctx.settings["categories"].categories:
        rules = import_categories(ctx, json.loads(categories_file.read_text()))
    parts = [f"{added} task{'' if added == 1 else 's'} from Todo List"] + (
        [f"{rules} categories from Chroma"] if rules else []
    )
    return Changed(message="Imported " + " and ".join(parts))


def task_fields(ctx: Ctx, task: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {"title": task["title"].strip(), "long_term": task.get("horizon") == "longTerm"}
    if task.get("dueDate"):
        moment = datetime.fromisoformat(task["dueDate"].replace("Z", "+00:00"))
        fields["due"] = format_local(to_local(int(moment.timestamp() // 60), ctx.tz))
    bucket = task.get("bucket")
    if bucket == "readings" and "Reading" in ctx.settings["presets"]:
        fields["preset"] = "Reading"
    elif bucket == "assignments" and "Assignment" in ctx.settings["presets"]:
        fields["preset"] = "Assignment"
    elif bucket == "emails" and "Errand" in ctx.settings["presets"]:
        fields |= {"preset": "Errand", "duration_min": 15}
    return fields


def import_categories(ctx: Ctx, data: dict[str, Any]) -> int:
    categories = [
        {k: c[k] for k in ("name", "slug", "color", "pattern", "note") if c.get(k) is not None}
        for c in data.get("categories", [])
    ]
    found = data.get("filter")
    rule = {"label": found["label"], "pattern": found["pattern"], "except": found.get("except", [])} if found else None
    settings_set(ctx, SettingsSetInput(key="categories", value={"categories": categories, "filter": rule}))
    return len(categories)
