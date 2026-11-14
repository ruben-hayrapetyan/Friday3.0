"""Bringing in the two apps Friday replaces, once (COMBINED.md 24): Todo List's open tasks and Chroma's categories,
and the color Chroma showed each event in.

The server runs on your Mac (COMBINED.md 2), so it reads their files where they are. Tasks keep their title, due
date and list (short or long term); a reading is a Reading, an assignment an Assignment and an email a quick Errand,
the rest are read by their titles like anything you add. Each task is brought in once, however often you run it;
categories only when you have none yet, or only the starter set. It is one command, so one Undo takes it all back.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from friday.api.commands import AddInput, Changed, ChromaColorsInput, ImportPersonalInput, SettingsSetInput
from friday.commands.items import add
from friday.commands.registry import Ctx, command
from friday.commands.settings import settings_set
from friday.core.calendars import STARTER_CATEGORIES, event_key
from friday.core.items import PIGMENTS, FieldError
from friday.core.time import format_local, to_local
from friday.planner.store import kv_get

TODOS = Path("~/Documents/Todo List/todos.json")
CATEGORIES = Path("~/Library/Application Support/Chroma/categories.json")
COLORS = Path("~/Library/Application Support/Chroma/colors.json")


@command("import_personal", affects_plan=True)
def import_personal(ctx: Ctx, inp: ImportPersonalInput) -> Changed:
    """Todo List's open tasks and Chroma's categories, once."""
    todos_file = Path(inp.todos_path or TODOS).expanduser()
    categories_file = Path(inp.categories_path or CATEGORIES).expanduser()
    if not todos_file.exists() and not categories_file.exists():
        raise FieldError("todos_path", f"found neither {todos_file} nor {categories_file}")
    seen = set(kv_get(ctx.conn, "imported_todos", [], ctx.user_id))
    added, skipped = 0, []
    if todos_file.exists():
        for task in listed(todos_file, "todos_path", list):
            if task.get("isDone") or task.get("id") in seen or not (task.get("title") or "").strip():
                continue
            try:
                add(ctx, AddInput(**task_fields(ctx, task)))  # checks its fields before it writes anything
            except (FieldError, ValueError) as error:  # one odd task doesn't stop the others; it's named instead
                skipped.append(f"{task['title'].strip()} ({error})")
                continue
            seen.add(task["id"])
            added += 1
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "imported_todos"}, {"value": json.dumps(sorted(seen))})
    rules = 0
    # The starter set (a new install's) gives way to Chroma's as none did; a set you've changed is yours and stays.
    if categories_file.exists() and ctx.settings["categories"].categories in ((), STARTER_CATEGORIES):
        rules = import_categories(ctx, listed(categories_file, "categories_path", dict))
    parts = [f"{added} task{'' if added == 1 else 's'} from Todo List"] + (
        [f"{rules} categories from Chroma"] if rules else []
    )
    left = f". Left out, to add by hand: {'; '.join(skipped)}" if skipped else ""
    return Changed(message="Imported " + " and ".join(parts) + left)


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
    preset = ctx.settings["presets"].get(fields.get("preset", ""))
    if preset is not None and preset.firmness == "hard" and "due" not in fields:
        fields["firmness"] = "none"  # an assignment with no due date yet, as `add` takes one
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


def listed(path: Path, field: str, shape: type) -> Any:
    """A file's JSON, as the app that wrote it wrote it; one that isn't is said, not a crash (audit, 8 Nov)."""
    try:
        found = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as error:
        raise FieldError(field, f"{path} isn't the file that app keeps (it isn't JSON)") from error
    if not isinstance(found, shape) or (shape is list and not all(isinstance(t, dict) for t in found)):
        what = "the list of tasks it writes" if shape is list else "what it writes"
        raise FieldError(field, f"{path} isn't the file that app keeps (not {what})")
    return found


@command("import_chroma_colors")
def import_chroma_colors(ctx: Ctx, inp: ChromaColorsInput) -> Changed:
    """The color Chroma showed each event in, by the event: its own choice, its calendar's or its category's.
    Chroma's file is only read; reading it again takes in what changed there."""
    colors_file = Path(inp.colors_path or COLORS).expanduser()
    if not colors_file.exists():
        raise FieldError("colors_path", f"found no {colors_file}")
    found = chroma_colors(listed(colors_file, "colors_path", dict))  # a broken file said, not a crash (12 Nov)
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "chroma_colors"}, {"value": json.dumps(found)})
    return Changed(message=f"Brought in Chroma's colors for {len(found)} event{'' if len(found) == 1 else 's'}")


def chroma_colors(stored: dict[str, str]) -> dict[str, str]:
    """Chroma's colors.json, keyed `<calendar>:<event>` (a repeat's one occurrence adds `/RID=<time>`), as pigments by
    the event alone: a whole repeat's color over one occurrence's, Unmarked and unknown names left out."""
    out: dict[str, str] = {}
    for key, color in sorted(stored.items(), key=lambda kv: "/RID=" not in kv[0]):  # whole repeats last, so they win
        if color in PIGMENTS:
            out[event_key(key)] = color
    return out
