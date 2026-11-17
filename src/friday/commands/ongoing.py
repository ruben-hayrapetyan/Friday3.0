"""Ongoing projects with hours a week and no deadline (the Projects page's Ongoing shelf; planner/ongoing.py says what
the planner reads of them). Each is a weekly repeat of a Goal from your week's first day, so this week's rest counts
pro rata as any Goal's does. Changing one changes its repeat and its open weeks in place, this week's too. Its options:
how much of a short week carries into the next, a rhythm (days a week to touch it: its week in that many pieces, at
most one piece a day), a priority (how much of a pace's push or cut it takes), and a pause, until you resume it or
until a date (the nightly `materialize` brings it back that morning)."""

import json
import math
from datetime import date, timedelta

from friday.api.commands import Changed, OngoingAddInput, OngoingSetInput, SeriesAddInput, SeriesOut, SeriesRef
from friday.api.types import Empty
from friday.api.views import OngoingOut, OngoingWeek
from friday.commands.fields import area_id
from friday.commands.registry import Ctx, command, query
from friday.commands.series import load_series, series_add, series_delete, series_out, series_resume, series_stop
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.pace import budget_factor, dials_on, priority_weight
from friday.core.recurrence import rule_parts
from friday.core.time import UNIT_MIN, format_utc, parse_utc
from friday.planner.ongoing import ONGOING, carried_minutes, ongoing_options
from friday.planner.progress import minutes_by_item
from friday.planner.snapshot import pace_periods
from friday.planner.store import area_names, current_plan

PAST_WEEKS = 6
TOUCHED_DAYS = 56  # eight weeks: the shelf's grid of days


def save_options(ctx: Ctx, options: dict[str, dict]) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": ONGOING}, {"value": json.dumps(options)})


@command("ongoing_add", affects_plan=True)
def ongoing_add(ctx: Ctx, inp: OngoingAddInput) -> SeriesOut:
    """Start an ongoing project with hours a week, from this week (the rest of this week counts pro rata)."""
    week_start = ctx.settings["time"].grid_spec().week_start
    first = ctx.today - timedelta(days=(ctx.today.weekday() - week_start) % 7)
    made = series_add(
        ctx,
        SeriesAddInput(
            title=inp.title.strip(),
            preset="Goal",
            area=inp.area,
            amount="target",
            target_min=max(UNIT_MIN, round(inp.hours_per_week * 60 / UNIT_MIN) * UNIT_MIN),
            neglect_carry=inp.carry,
            every="week",
            start_date=first.isoformat(),
        ),
    )
    options = ongoing_options(ctx.conn, ctx.user_id)
    options[str(made.id)] = dict(NEW_OPTIONS)
    save_options(ctx, options)
    return made


NEW_OPTIONS = {"rhythm_days": None, "priority": 3, "paused_until": None}


def weekly_goal(series: dict) -> bool:
    """A repeat that's a target amount each week: what an ongoing project is, however it was made."""
    rule = rule_parts(series["rrule"])
    return json.loads(series["template"]).get("amount") == "target" and rule.get("FREQ") == "WEEKLY" \
        and rule.get("INTERVAL", "1") == "1"  # fmt: skip


def goals_as_before(ctx: Ctx, options: dict[str, dict]) -> set[int]:
    """Weekly goals made outside the shelf (before 0.5.0, or as a repeating Goal elsewhere): listed on the shelf so
    they can be found, planned as they always were (no carry-over or priority) until a setting changes (16 Nov: "Show
    them, plan unchanged")."""
    found = rows(ctx.conn, "SELECT * FROM series WHERE user_id = ? AND active = 1", [ctx.user_id])
    return {s["id"] for s in found if str(s["id"]) not in options and weekly_goal(s)}


def require_ongoing(ctx: Ctx, series_id: int) -> tuple[dict, dict, dict]:
    """The repeat, its template, and every ongoing project's options; a weekly goal made elsewhere becomes one here (a
    setting changed on the shelf); any other repeat is refused."""
    found = load_series(ctx, series_id)
    options = ongoing_options(ctx.conn, ctx.user_id)
    template = json.loads(found["template"])
    if str(series_id) not in options and series_id in goals_as_before(ctx, options):
        options[str(series_id)] = dict(NEW_OPTIONS)
    if str(series_id) not in options or template.get("amount") != "target":
        raise FieldError("id", "that repeat isn't an ongoing project")
    return found, template, options


@command("ongoing_set", affects_plan=True)
def ongoing_set(ctx: Ctx, inp: OngoingSetInput) -> SeriesOut:
    """Change an ongoing project: its name, tag, hours a week, carry-over, rhythm, priority or pause."""
    _, template, options = require_ongoing(ctx, inp.id)
    mine = dict(options[str(inp.id)])
    change: dict[str, object] = {}
    if inp.title is not None:
        if not inp.title.strip():
            raise FieldError("title", "an ongoing project needs a name")
        change["title"] = inp.title.strip()
    if inp.area is not None:  # its tag (a client: "can't add a tag on projects of type ongoing")
        change["area_id"] = area_id(ctx, inp.area.strip()) if inp.area.strip() else None
    if inp.hours_per_week is not None:
        units = max(1, round(inp.hours_per_week * 60 / UNIT_MIN))
        change |= {"target_units": units, "cap_units": math.ceil(1.5 * units)}
    if inp.carry is not None:
        change["neglect_carry"] = inp.carry
    if inp.rhythm_days is not None:
        mine["rhythm_days"] = inp.rhythm_days or None
    if inp.priority is not None:
        mine["priority"] = inp.priority
    change |= sittings(template | change, mine.get("rhythm_days"))
    if inp.paused_until is not None:
        pause(ctx, inp.id, inp.paused_until, mine)
    options[str(inp.id)] = mine
    save_options(ctx, options)
    ctx.db.update("series", {"id": inp.id}, {"template": json.dumps(template | change), "updated_utc": ctx.now_text})
    for r in rows(ctx.conn, "SELECT id FROM items WHERE series_id = ? AND status = 'todo'", [inp.id]):
        ctx.db.update("items", {"id": r["id"]}, change | {"updated_utc": ctx.now_text})
    return series_out(ctx, inp.id)


def sittings(template: dict, days: int | None) -> dict:
    """A rhythm as pieces: N days a week is the week in N pieces, at most one piece's worth a day, each at least half a
    piece (and 30 minutes); no rhythm leaves its pieces to the kind (a Goal's at least 30 minutes, no most a day)."""
    if not days:
        return {"daily_ceiling_units": None, "max_chunk_units": None}
    target = template.get("target_units") or 1
    most = max(1, math.ceil(target / days))
    return {"daily_ceiling_units": most, "max_chunk_units": most, "min_chunk_units": min(most, max(2, most // 2))}


def pause(ctx: Ctx, series_id: int, until: str, mine: dict) -> None:
    """Pause until a date (its weeks go meanwhile) or until you resume it ("resume"), or "" to resume now."""
    if not until:
        mine["paused_until"] = None
        series_resume(ctx, SeriesRef(id=series_id))
        return
    if until == "resume":  # until you resume it
        mine["paused_until"] = None
        series_stop(ctx, SeriesRef(id=series_id))
        return
    try:
        day = date.fromisoformat(until)
    except ValueError as error:
        raise FieldError("paused_until", "a date like 2026-11-20") from error
    if day <= ctx.today:
        raise FieldError("paused_until", "a day after today")
    mine["paused_until"] = until
    series_stop(ctx, SeriesRef(id=series_id))


def resume_paused(ctx: Ctx) -> None:
    """Ongoing projects paused until a day that has come start again: their weeks come back."""
    options = ongoing_options(ctx.conn, ctx.user_id)
    woken = [
        k for k, v in options.items() if v.get("paused_until") and date.fromisoformat(v["paused_until"]) <= ctx.today
    ]
    for key in woken:
        options[key] = {**options[key], "paused_until": None}
        series_resume(ctx, SeriesRef(id=int(key)))
    if woken:
        save_options(ctx, options)


@command("ongoing_delete", affects_plan=True)
def ongoing_delete(ctx: Ctx, inp: SeriesRef) -> Changed:
    """Delete an ongoing project: its weeks to come go; the hours you put in stay in your history."""
    _, template, options = require_ongoing(ctx, inp.id)
    # A week with time in it is closed first: deleting a repeat removes every week not done, its time with it.
    done = minutes_by_item(ctx.conn, ctx.user_id)
    for r in rows(ctx.conn, "SELECT id FROM items WHERE series_id = ? AND status = 'todo'", [inp.id]):
        if done.get(r["id"], 0) > 0:
            ctx.db.update("items", {"id": r["id"]}, {"status": "done", "completed_utc": ctx.now_text,
                                                     "updated_utc": ctx.now_text})  # fmt: skip
    series_delete(ctx, inp)
    options.pop(str(inp.id), None)
    save_options(ctx, options)
    return Changed(message=f"{template.get('title', 'It')} deleted; the hours you put in stay in your history")


@query("ongoing_projects")
def ongoing_projects(ctx: Ctx, inp: Empty) -> list[OngoingOut]:
    """Each ongoing project: this week's hours (with what carried in), done and still planned, and the weeks before."""
    options = ongoing_options(ctx.conn, ctx.user_id)
    made_elsewhere = goals_as_before(ctx, options)
    if not options and not made_elsewhere:
        return []
    done = minutes_by_item(ctx.conn, ctx.user_id)
    carried = carried_minutes(ctx.conn, ctx.now_utc, ctx.user_id)
    planned = planned_minutes(ctx)
    areas = area_names(ctx.conn, ctx.user_id)
    growth = dials_on(
        ctx.today,
        list(pace_periods(ctx.conn, ctx.user_id)),
        ctx.settings["paces"],
        ctx.settings["pace"].default,
        ctx.settings["pace"].weekly,
    ).growth
    out = []
    for s in rows(ctx.conn, "SELECT * FROM series WHERE user_id = ? ORDER BY id", [ctx.user_id]):
        mine = options.get(str(s["id"])) or (dict(NEW_OPTIONS) if s["id"] in made_elsewhere else None)
        template = json.loads(s["template"])
        if mine is None or template.get("amount") != "target":
            continue
        weeks = rows(
            ctx.conn,
            "SELECT * FROM items WHERE series_id = ? AND status IN ('todo', 'done') AND release_utc IS NOT NULL "
            "AND release_utc <= ? ORDER BY release_utc",
            [s["id"], ctx.now_text],
        )

        def week(r: dict, now: bool) -> OngoingWeek:
            extra = carried.get(r["id"], 0) if now else 0
            return OngoingWeek(
                start=ctx.local(r["release_utc"]) or "",
                end=ctx.local(r["due_utc"]) or "",
                target_min=(r["target_units"] or 0) * UNIT_MIN + extra,
                carried_min=extra,
                done_min=done.get(r["id"], 0),
                planned_min=planned.get(r["id"], 0) if now else 0,
                item_id=r["id"],
            )

        current = [r for r in weeks if r["due_utc"] and parse_utc(r["due_utc"]) > ctx.now_utc]
        before = [r for r in weeks if r not in current][-PAST_WEEKS:]
        hours = (template.get("target_units") or 0) * UNIT_MIN / 60
        priority = int(mine.get("priority") or 3)
        out.append(
            OngoingOut(
                id=s["id"],
                title=template.get("title", ""),
                area=areas.get(template["area_id"]) if template.get("area_id") else None,
                active=bool(s["active"]),
                hours_per_week=hours,
                carry=float(template.get("neglect_carry", 0.5)),
                week=week(current[0], True) if current and s["active"] else None,
                past=[week(r, False) for r in before],
                touched=touched_days(ctx, s["id"]),
                rhythm_days=mine.get("rhythm_days"),
                priority=priority,
                aim_min=round(hours * 60 * budget_factor(growth, priority_weight(priority))),
                paused_until=mine.get("paused_until"),
                as_before=s["id"] in made_elsewhere,
            )
        )
    return out


def touched_days(ctx: Ctx, series_id: int) -> list[str]:
    """The local dates in the last eight weeks with work on any of the repeat's weeks."""
    since = format_utc(ctx.now_utc - TOUCHED_DAYS * 24 * 60)
    found = rows(
        ctx.conn,
        "SELECT COALESCE(p.start_utc, p.created_utc) AS at FROM progress p JOIN items i ON i.id = p.item_id "
        "WHERE i.series_id = ? AND p.minutes > 0 AND COALESCE(p.start_utc, p.created_utc) >= ?",
        [series_id, since],
    )
    return sorted({(ctx.local(r["at"]) or "")[:10] for r in found} - {""})


def planned_minutes(ctx: Ctx) -> dict[int, int]:
    """Minutes still planned per item in the current plan, from now."""
    saved = current_plan(ctx.conn, ctx.user_id)
    if saved is None:
        return {}
    out: dict[int, int] = {}
    for b in rows(ctx.conn, "SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ?", [saved["id"]]):
        start, end = max(parse_utc(b["start_utc"]), ctx.now_utc), parse_utc(b["end_utc"])
        if end > start:
            out[b["item_id"]] = out.get(b["item_id"], 0) + end - start
    return out
