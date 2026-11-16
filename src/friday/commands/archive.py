"""Finished projects (the Projects page's Finished shelf): archiving a project marks it done and drops the steps still
open, remembering which, so unarchiving brings back exactly those (the ones you dropped yourself stay dropped). The
shelf lists every finished project, archived or ticked done, with what it took against its steps' lengths. Deleting
one from there drops it and its steps; Undo brings it back, as any command's does."""

import json

from friday.api.commands import Changed, ProjectRef
from friday.api.types import Empty
from friday.api.views import FinishedProject
from friday.commands.fields import require_item
from friday.commands.items import set_status
from friday.commands.registry import Ctx, command, query
from friday.commands.timer import stop_timer
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.time import UNIT_MIN
from friday.planner.progress import minutes_by_item
from friday.planner.store import area_names, kv_get

ARCHIVED = "archived_projects"  # kv, by project id: {"steps": the open steps archiving dropped, "rules": its own}
# Every step under a project, however deep.
DESCENDANTS = (
    "WITH RECURSIVE tree(id) AS (SELECT id FROM items WHERE parent_id = ? "
    "UNION ALL SELECT i.id FROM items i JOIN tree t ON i.parent_id = t.id) "
    "SELECT i.* FROM items i JOIN tree t ON i.id = t.id"
)
FINISHED_SHOWN = 30


def put_rules_away(ctx: Ctx, project_id: int) -> list[dict]:
    from friday.commands.project_options import put_rules_away as away  # it needs require_project from here

    return away(ctx, project_id)


def bring_rules_back(ctx: Ctx, kept: list[dict]) -> None:
    from friday.commands.project_options import bring_rules_back as back

    back(ctx, kept)


def archived(ctx: Ctx) -> dict[str, dict]:
    return dict(kv_get(ctx.conn, ARCHIVED, {}, ctx.user_id) or {})


def save(ctx: Ctx, value: dict[str, dict]) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": ARCHIVED}, {"value": json.dumps(value)})


def require_project(ctx: Ctx, project_id: int) -> str:
    """The project's title; something that isn't a project (no steps and not of the Project kind) is refused."""
    project = require_item(ctx, project_id)
    has_steps = rows(ctx.conn, "SELECT 1 FROM items WHERE parent_id = ? LIMIT 1", [project_id])
    if project.parent_id is not None or not (has_steps or project.preset == "Project"):
        raise FieldError("id", f"{project.title} isn't a project")
    return project.title


def stop_timer_on(ctx: Ctx, item_ids: list[int]) -> None:
    for item_id in item_ids:
        if ctx.conn.execute("SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, item_id]).fetchone():
            stop_timer(ctx, item_id=item_id)  # its time kept, as drop does


@command("project_archive", affects_plan=True)
def project_archive(ctx: Ctx, inp: ProjectRef) -> Changed:
    """Archive a project: it's done, its steps still open are dropped, and it moves to Finished."""
    title = require_project(ctx, inp.id)
    open_steps = [r["id"] for r in rows(ctx.conn, DESCENDANTS, [inp.id]) if r["status"] == "todo"]
    stop_timer_on(ctx, [inp.id, *open_steps])
    for step in open_steps:
        set_status(ctx, step, "dropped")
    set_status(ctx, inp.id, "done", ctx.now_text)
    kept = archived(ctx)
    kept[str(inp.id)] = {"steps": open_steps, "rules": put_rules_away(ctx, inp.id)}
    save(ctx, kept)
    return Changed(message=f"{title} archived")


@command("project_unarchive", affects_plan=True)
def project_unarchive(ctx: Ctx, inp: ProjectRef) -> Changed:
    """Open an archived or finished project again, with the steps archiving dropped."""
    title = require_project(ctx, inp.id)
    kept = archived(ctx)
    was = kept.pop(str(inp.id), {"steps": []})
    steps = was["steps"]
    bring_rules_back(ctx, was.get("rules", []))
    set_status(ctx, inp.id, "todo")
    for step in steps:
        if rows(ctx.conn, "SELECT 1 FROM items WHERE id = ? AND status = 'dropped'", [step]):
            set_status(ctx, step, "todo")
    save(ctx, kept)
    return Changed(message=f"{title} is open again")


@command("project_delete", affects_plan=True)
def project_delete(ctx: Ctx, inp: ProjectRef) -> Changed:
    """Delete a finished project: it and its steps are dropped and leave Finished; the time you put in stays in your
    history, and Undo brings it back."""
    title = require_project(ctx, inp.id)
    steps = [r["id"] for r in rows(ctx.conn, DESCENDANTS, [inp.id]) if r["status"] != "dropped"]
    stop_timer_on(ctx, [inp.id, *steps])
    for step in steps:
        set_status(ctx, step, "dropped")
    set_status(ctx, inp.id, "dropped")
    put_rules_away(ctx, inp.id)  # deleted, its own rules go with it (Undo brings both back)
    kept = archived(ctx)
    if kept.pop(str(inp.id), None) is not None:
        save(ctx, kept)
    return Changed(message=f"{title} deleted")


@query("projects_finished")
def projects_finished(ctx: Ctx, inp: Empty) -> list[FinishedProject]:
    """Finished projects, newest first: what each took against its steps' lengths."""
    done = minutes_by_item(ctx.conn, ctx.user_id)
    areas = area_names(ctx.conn, ctx.user_id)
    found = rows(
        ctx.conn,
        "SELECT * FROM items p WHERE p.user_id = ? AND p.status = 'done' AND p.parent_id IS NULL "
        "AND (p.preset = 'Project' OR EXISTS (SELECT 1 FROM items c WHERE c.parent_id = p.id)) "
        "ORDER BY p.completed_utc DESC, p.id DESC LIMIT ?",
        [ctx.user_id, FINISHED_SHOWN],
    )
    kept = archived(ctx)
    out = []
    for p in found:
        steps = rows(ctx.conn, DESCENDANTS, [p["id"]])
        parents = {s["parent_id"] for s in steps}
        # What it was planned to take: its steps' lengths, those you dropped left out (not the ones archiving
        # dropped, which were still to do); a project with none, its own.
        by_archive = set(kept.get(str(p["id"]), {}).get("steps", []))
        planned = [s for s in steps if (s["status"] != "dropped" or s["id"] in by_archive) and s["id"] not in parents]
        estimate = sum((s["duration_units"] or 0) for s in planned) * UNIT_MIN or (p["duration_units"] or 0) * UNIT_MIN
        out.append(
            FinishedProject(
                id=p["id"],
                title=p["title"],
                area=areas.get(p["area_id"]) if p["area_id"] else None,
                finished=ctx.local(p["completed_utc"]),
                steps=len([s for s in steps if s["id"] not in parents]),
                estimate_min=estimate,
                actual_min=done.get(p["id"], 0) + sum(done.get(s["id"], 0) for s in steps),
            )
        )
    return out
