"""Projects and the months ahead (DESIGN §6.4, §13.3): projects, load, template_apply, template_save."""

import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from friday.api.commands import (
    AddInput,
    Changed,
    ItemResult,
    LoadInput,
    ReorderInput,
    TemplateApplyInput,
    TemplateSaveInput,
)
from friday.api.types import Empty, ItemOut
from friday.api.views import ProjectOut, WeekLoad
from friday.commands.calendar import dues
from friday.commands.fields import item_out, require_item
from friday.commands.items import add, add_dependency
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.rows import item_from_row
from friday.core.time import UNIT_MIN, format_utc, parse_utc, planning_date
from friday.planner.progress import minutes_by_item, remaining_minutes
from friday.planner.store import current_plan, kv_get


def saved_plan(ctx: Ctx) -> tuple[int | None, dict[str, Any]]:
    saved = current_plan(ctx.conn, ctx.user_id)
    return (saved["id"], json.loads(saved["report"])) if saved else (None, {})


def finishes(ctx: Ctx, remaining: dict[int, int]) -> dict[int, str]:
    """Each item's last planned work: its last block when the plan holds all it has left, else the allocator's last
    day for it, as a date (the allocator plans whole days)."""
    plan_id, report = saved_plan(ctx)
    out: dict[int, str] = {}
    for r in rows(
        ctx.conn,
        "SELECT item_id, max(end_utc) AS last, sum((julianday(end_utc) - julianday(start_utc)) * 1440) AS minutes "
        "FROM blocks WHERE plan_id = ? GROUP BY item_id",
        [plan_id],
    ):
        if round(r["minutes"]) >= remaining.get(r["item_id"], 0):
            out[r["item_id"]] = ctx.local(r["last"]) or ""
    if "allocation_start" in report:
        first = date.fromisoformat(report["allocation_start"])
        for item_id, day in report.get("allocation_finish", {}).items():
            out.setdefault(int(item_id), (first + timedelta(days=day)).isoformat())
    return out


@query("projects")
def projects(ctx: Ctx, inp: Empty) -> list[ProjectOut]:
    """Open projects with their descendants, rolled-up progress, planned finish and whether they're on track."""
    found = rows(ctx.conn, "SELECT * FROM items WHERE user_id = ? AND status IN ('todo', 'done')", [ctx.user_id])
    items = {r["id"]: item_from_row(r) for r in found}
    children: dict[int, list[int]] = defaultdict(list)
    for item in items.values():
        if item.parent_id is not None:
            children[item.parent_id].append(item.id or 0)
    # Steps in the order you gave them (`reorder`), the rest after them as they were made.
    order = kv_get(ctx.conn, "project_order", {}, ctx.user_id) or {}
    for parent, kids in children.items():
        given = order.get(str(parent), [])
        kids.sort(key=lambda i: (given.index(i) if i in given else len(given), i))
    done = minutes_by_item(ctx.conn, ctx.user_id)
    left = {i: remaining_minutes(it, done.get(i, 0)) or 0 for i, it in items.items() if it.when != "fixed"}
    finish = finishes(ctx, left)
    out = []
    for item in items.values():
        is_project = children.get(item.id or 0) or item.preset == "Project"
        if not is_project or item.status != "todo" or (item.parent_id in items and item.preset != "Project"):
            continue
        tree = [item_out(ctx, items[i], done.get(i, 0)) for i in descendants(children, item.id or 0)]
        out.append(project_out(ctx, item_out(ctx, item, done.get(item.id or 0, 0)), tree, finish))
    return sorted(out, key=lambda p: (p.item.due or "9999", p.item.id))


def descendants(children: dict[int, list[int]], root: int) -> list[int]:
    out, stack = [], list(reversed(children.get(root, [])))
    while stack:
        at = stack.pop()
        out.append(at)
        stack.extend(reversed(children.get(at, [])))
    return out


def project_out(ctx: Ctx, project: ItemOut, tree: list[ItemOut], finish: dict[int, str]) -> ProjectOut:
    parents = {c.parent_id for c in tree}
    leaves = [c for c in tree if c.id not in parents] or [project]
    open_leaves = [c for c in leaves if c.status == "todo" and (c.remaining_min or 0) > 0]
    planned = [finish[c.id] for c in open_leaves if c.id in finish]
    late = any(
        c.id in finish and (c.due or project.due) and finish[c.id] > (c.due or project.due or "") for c in open_leaves
    )
    if not open_leaves:
        status = "done"
    elif len(planned) < len(open_leaves):
        status = "unplanned"
    else:
        status = "late" if late else "on_track"
    return ProjectOut(
        item=project,
        children=tree,
        done_min=sum(c.done_min for c in leaves),
        remaining_min=sum(c.remaining_min or 0 for c in open_leaves),
        planned_finish=max(planned) if planned and len(planned) == len(open_leaves) else None,
        status=status,  # type: ignore[arg-type]
    )


@query("load")
def load(ctx: Ctx, inp: LoadInput) -> list[WeekLoad]:
    """Planned hours against room, week by week: the plan inside the horizon, the allocator's forecast past it."""
    plan_id, report = saved_plan(ctx)
    if "allocation_start" not in report:
        raise FieldError("plan", "there's no plan yet; run `replan`")
    first = date.fromisoformat(report["allocation_start"])
    forecast, capacity = report["allocation_hours"], report["allocation_capacity_hours"]
    scheduled: dict[date, float] = defaultdict(float)
    for r in rows(ctx.conn, "SELECT start_utc, end_utc FROM blocks WHERE plan_id = ?", [plan_id]):
        start = parse_utc(r["start_utc"])
        scheduled[planning_date(start, ctx.tz, ctx.day_start)] += (parse_utc(r["end_utc"]) - start) / 60
    horizon = first + timedelta(days=ctx.settings["time"].horizon_days - 1)
    forecast = less_done_early(forecast, sum(scheduled.values()), (horizon - first).days + 1)
    week_start = ctx.settings["time"].grid_spec().week_start
    weeks: dict[date, WeekLoad] = {}
    for d in range(min(len(forecast), inp.weeks * 7)):
        day = first + timedelta(days=d)
        monday = day - timedelta(days=(day.weekday() - week_start) % 7)
        week = weeks.setdefault(monday, WeekLoad(start=monday.isoformat(), hours=0, capacity=0, forecast=False, due=[]))
        week.hours += scheduled.get(day, 0.0) if day <= horizon else forecast[d]
        week.capacity += capacity[d]
        week.forecast |= day > horizon
    for monday, week in weeks.items():
        week.hours, week.capacity = round(week.hours, 1), round(week.capacity, 1)
        week.due = dues(ctx, monday, monday + timedelta(days=7), hard_only=True)
    return list(weeks.values())


def less_done_early(forecast: list[float], scheduled: float, horizon_days: int) -> list[float]:
    """The forecast past the horizon less what the plan does early (more than the allocator put inside the
    horizon), so it isn't counted twice; taken off the latest days, where the allocator leaves distant work."""
    # ponytail: totals, not per item; per-item allocations in the plan report would make it exact.
    extra = max(0.0, scheduled - sum(forecast[:horizon_days]))
    out = list(forecast)
    for d in range(len(out) - 1, horizon_days - 1, -1):
        taken = min(out[d], extra)
        out[d], extra = out[d] - taken, extra - taken
    return out


@command("template_apply", affects_plan=True)
def template_apply(ctx: Ctx, inp: TemplateApplyInput) -> ItemResult:
    """Create a project from a template: one child per step, each after the one before."""
    steps = ctx.settings["templates"].get(inp.template)
    if steps is None:
        raise FieldError(
            "template", f"no template called {inp.template}; saved: {', '.join(ctx.settings['templates'])}"
        )
    common: dict[str, Any] = {"due": inp.due, "release": inp.release, "area": inp.area}
    if inp.due is None:
        common["firmness"] = "none"  # a hard item needs a due date
    parent = add(ctx, AddInput(title=inp.title, preset="Project", duration_min=round(inp.hours * 60), **common)).item
    assert parent is not None
    total = sum(s.share for s in steps)
    aims = step_aims(ctx, inp, [s.share / total for s in steps])
    previous = None
    for step, aim in zip(steps, aims, strict=True):
        minutes = max(UNIT_MIN, math.ceil(inp.hours * 60 * step.share / total / UNIT_MIN) * UNIT_MIN)
        fields = {
            "title": step.title,
            "preset": step.preset or "Assignment",
            "duration_min": minutes,
            "parent_id": parent.id,
        }
        child = add(ctx, AddInput(**fields, **(common | aim))).item
        assert child is not None
        if previous is not None:
            add_dependency(ctx, child.id, previous, 1.0, 0)
        previous = child.id
    return ItemResult(item=item_out(ctx, require_item(ctx, parent.id)))


def step_aims(ctx: Ctx, inp: TemplateApplyInput, shares: list[float]) -> list[dict[str, Any]]:
    """Each step but the last aims to be done when its share of the time to the due has passed, as a soft due:
    with only the project's due, every step was left for its last three days (M15)."""
    if inp.due is None:
        return [{} for _ in shares]
    start = parse_utc(ctx.utc(inp.release, "release")) if inp.release else ctx.now_utc
    end = parse_utc(ctx.utc(inp.due, "due"))
    aims: list[dict[str, Any]] = []
    done = 0.0
    for share in shares[:-1]:
        done += share
        day = (ctx.local(format_utc(start + round((end - start) * done))) or "")[:10]
        aims.append({"due": min(f"{day}T23:59", inp.due), "firmness": "soft"})  # the end of that day
    return [*aims, {}]


@command("template_save")
def template_save(ctx: Ctx, inp: TemplateSaveInput) -> Changed:
    """Save a project's children, in order, as a template; each step's share is its part of the hours."""
    kids = [item_from_row(r) for r in rows(
        ctx.conn, "SELECT * FROM items WHERE user_id = ? AND parent_id = ? ORDER BY id", [ctx.user_id, inp.project_id]
    )]  # fmt: skip
    # In the order the project shows them, as you put them (`reorder`); steps added since go after (3 Nov: a saved
    # template ignored the order you had dragged the steps into)
    order = (kv_get(ctx.conn, "project_order", {}, ctx.user_id) or {}).get(str(inp.project_id), [])
    rank = {item_id: n for n, item_id in enumerate(order)}
    kids.sort(key=lambda k: (rank.get(k.id, len(rank)), k.id))
    if not kids:
        raise FieldError("project_id", f"T{inp.project_id} has no items inside it")
    units = [k.duration_units or 1 for k in kids]
    steps = [
        {"title": k.title, "share": round(u / sum(units), 3), "preset": k.preset}
        for k, u in zip(kids, units, strict=True)
    ]
    templates = {name: [s.model_dump() for s in v] for name, v in ctx.settings["templates"].items()}
    write_setting(ctx, "templates", templates | {inp.name: steps})
    return Changed(message=f"Saved template {inp.name} ({len(steps)} steps)")


@command("reorder")
def reorder(ctx: Ctx, inp: ReorderInput) -> Changed:
    """Put a project's steps in this order (it shows them so; the plan follows their dependencies)."""
    require_item(ctx, inp.parent_id)
    order = kv_get(ctx.conn, "project_order", {}, ctx.user_id) or {}
    order[str(inp.parent_id)] = inp.ids
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "project_order"}, {"value": json.dumps(order)})
    return Changed(message="Reordered")
