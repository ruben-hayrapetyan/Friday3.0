"""A project made of steps (17 Nov, your proposal (h): "projects that are entirely defined by their subtasks and
projects that aren't", told apart by Friday, never by you): its steps are the work, so the project is done when its
last step is, and opens again when one does. A project's length beyond its steps is a step of its own, "More on
<project>", kept by Friday as the steps and the length change: planned and timed like the rest, gone when the steps
cover it. A project with no steps is a to-do like any other."""

import json

from friday.commands.registry import Ctx
from friday.core.db import one, rows
from friday.core.time import UNIT_MIN
from friday.planner.progress import minutes_by_item
from friday.planner.store import kv_get

REST = "project_rest"  # kv: project id → its "More on" step's id, or 0 once you deleted that step (not made again)
SMALLEST_MIN = 15  # less than this left over isn't a step of its own


def rest_of(ctx: Ctx) -> dict[str, int]:
    return dict(kv_get(ctx.conn, REST, {}, ctx.user_id) or {})


def open_steps(ctx: Ctx, project_id: int) -> list[dict]:
    return rows(ctx.conn, "SELECT * FROM items WHERE parent_id = ? AND status = 'todo'", [project_id])


def last_step_finished(ctx: Ctx, item_id: int) -> int | None:
    """The project an item was the last open step of, now that it's done (it's done with it); None otherwise."""
    item = one(ctx.conn, "SELECT parent_id FROM items WHERE id = ?", [item_id])
    if item is None or item["parent_id"] is None:
        return None
    parent = one(ctx.conn, "SELECT * FROM items WHERE id = ?", [item["parent_id"]])
    if parent is None or parent["status"] != "todo" or open_steps(ctx, parent["id"]):
        return None
    return parent["id"]


def project_reopened_by(ctx: Ctx, item_id: int) -> int | None:
    """The finished project a step opened again belongs to: it opens again too."""
    item = one(ctx.conn, "SELECT parent_id FROM items WHERE id = ?", [item_id])
    if item is None or item["parent_id"] is None:
        return None
    parent = one(ctx.conn, "SELECT id, status FROM items WHERE id = ?", [item["parent_id"]])
    return parent["id"] if parent is not None and parent["status"] == "done" else None


def keep_rest(ctx: Ctx, project_id: int) -> None:
    """Make, resize or let go of a project's "More on" step: its length is the project's beyond its other steps."""
    project = one(ctx.conn, "SELECT * FROM items WHERE id = ? AND user_id = ?", [project_id, ctx.user_id])
    rests = rest_of(ctx)
    mine = rests.get(str(project_id))
    if project is None or project["status"] != "todo" or mine == 0:
        return
    steps = rows(ctx.conn, "SELECT * FROM items WHERE parent_id = ? AND status != 'dropped'", [project_id])
    others = [s for s in steps if s["id"] != mine]
    rest = one(ctx.conn, "SELECT * FROM items WHERE id = ?", [mine]) if mine else None
    if rest is not None and rest["status"] == "dropped":  # deleted by you: not made again for this project
        save(ctx, rests | {str(project_id): 0})
        return
    if not others:  # no steps of yours: the project is worked on as a whole, as it always was
        if rest is not None and rest["status"] == "todo" and not logged(ctx, rest["id"]):
            ctx.db.update("items", {"id": rest["id"]}, {"status": "dropped", "updated_utc": ctx.now_text})
            save(ctx, {k: v for k, v in rests.items() if k != str(project_id)})
        return
    # only a length you gave it: a Project's own ten hours are a guess, not more work than its steps
    whole = (project["duration_units"] or 0) * UNIT_MIN if project["duration_source"] == "you" else 0
    left = whole - sum((s["duration_units"] or 0) * UNIT_MIN for s in others)
    if left < SMALLEST_MIN:
        if rest is not None and rest["status"] == "todo":
            kept = logged(ctx, rest["id"])
            if kept:  # time in it stays: it ends at what was done
                ctx.db.update(
                    "items", {"id": rest["id"]}, {"duration_units": round(kept / UNIT_MIN), "updated_utc": ctx.now_text}
                )
            else:
                ctx.db.update("items", {"id": rest["id"]}, {"status": "dropped", "updated_utc": ctx.now_text})
                save(ctx, {k: v for k, v in rests.items() if k != str(project_id)})
        return
    units = max(1, round(left / UNIT_MIN))
    if rest is not None and rest["status"] != "dropped":
        if rest["duration_units"] != units or rest["status"] != "todo":
            change = {"duration_units": units, "status": "todo", "completed_utc": None, "updated_utc": ctx.now_text}
            ctx.db.update("items", {"id": rest["id"]}, change)
        return
    made = ctx.db.insert(
        "items",
        {key: project[key] for key in REST_COPIED if key in project}
        | {
            "title": f"More on {project['title']}",
            "parent_id": project_id,
            "duration_units": units,
            "preset": kind_of(others),
            "status": "todo",
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },  # fmt: skip
    )
    save(ctx, rests | {str(project_id): made})


# What the "More on" step takes from its project: whose it is, its tag, its window and how firm its due is.
REST_COPIED = ("user_id", "area_id", "when_kind", "amount", "release_utc", "due_utc", "firmness", "shape",
               "min_chunk_units", "energy")  # fmt: skip


def kind_of(steps: list[dict]) -> str:
    """The kind most of the project's steps are (an essay's: Assignment), as its "More on" step's."""
    kinds = [s["preset"] for s in steps if s["preset"] and s["preset"] != "Project"]
    return max(set(kinds), key=kinds.count) if kinds else "Assignment"


def logged(ctx: Ctx, item_id: int) -> int:
    return minutes_by_item(ctx.conn, ctx.user_id).get(item_id, 0)


def save(ctx: Ctx, rests: dict[str, int]) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": REST}, {"value": json.dumps(rests)})
