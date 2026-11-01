"""Reading a stretch of use back (M16): what you did, what the planner did with it, and what went wrong, in order.
`report` is the app telling the daemon about an error on your screen; `diagnose` lists the last hours."""

import json
import logging
from datetime import timedelta
from typing import Any

from friday.api.commands import Changed, DiagnoseInput, ReportInput
from friday.api.views import Happening
from friday.commands.registry import Ctx, command, query
from friday.core.db import rows
from friday.core.time import format_utc
from friday.planner.store import kv_get

log = logging.getLogger("friday.client")


REPORTS_KEPT = 50


@command("report")
def report(ctx: Ctx, inp: ReportInput) -> Changed:
    """Note an error or something that looked wrong in the app: in the daemon's log, and kept (the last 50) for
    `diagnose` to list next to what the server did."""
    log.warning("%s: %s%s", inp.where, inp.message, f"\n{inp.detail}" if inp.detail else "")
    kept = kv_get(ctx.conn, "client_reports", [], ctx.user_id) or []
    kept = [*kept, {"at": ctx.now_text, "where": inp.where, "message": inp.message}][-REPORTS_KEPT:]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "client_reports"}, {"value": json.dumps(kept)})
    return Changed(message="Noted")


@query("diagnose")
def diagnose(ctx: Ctx, inp: DiagnoseInput) -> list[Happening]:
    """The last hours in order: each command, each plan with its reason, time and how today's work was cut into
    pieces, jobs that failed, and what the app reported."""
    since = format_utc(ctx.now_utc - round(inp.hours * 60))
    found = [*commands_since(ctx, since), *plans_since(ctx, since), *failed_jobs(ctx, since), *reports(ctx, since)]
    return sorted(found, key=lambda h: h.at)


def commands_since(ctx: Ctx, since: str) -> list[Happening]:
    out = []
    for r in rows(
        ctx.conn,
        "SELECT * FROM command_log WHERE user_id = ? AND at_utc >= ? AND command != 'report' ORDER BY id",
        [ctx.user_id, since],
    ):
        given = {k: v for k, v in json.loads(r["input"]).items() if v not in (None, [], {})}
        text = " ".join(f"{k}={json.dumps(v)}" for k, v in given.items())[:90]
        undone = f" (undone by C{r['undone_by']})" if r["undone_by"] else ""
        summary = f"C{r['id']} {r['actor']} {r['command']} {text}{undone}"
        out.append(Happening(at=ctx.local(r["at_utc"]) or "", kind="command", summary=summary))
    return out


def reports(ctx: Ctx, since: str) -> list[Happening]:
    kept = kv_get(ctx.conn, "client_reports", [], ctx.user_id) or []
    return [
        Happening(at=ctx.local(r["at"]) or "", kind="report", summary=f"{r['where']}: {r['message']}")
        for r in kept
        if r["at"] >= since
    ]


def plans_since(ctx: Ctx, since: str) -> list[Happening]:
    out = []
    day_lo = ctx.utc(f"{ctx.today}T00:00")
    day_hi = ctx.utc(f"{ctx.today + timedelta(days=1)}T00:00")  # the next midnight: 25 hours when the clocks go back
    for r in rows(
        ctx.conn, "SELECT * FROM plans WHERE user_id = ? AND created_utc >= ? ORDER BY id", [ctx.user_id, since]
    ):
        report_ = json.loads(r["report"] or "{}")
        late = report_.get("late_hours") or {}
        pieces = pieces_today(ctx, r["id"], day_lo, day_hi)
        parts = [f"P{r['id']} {r['reason']}, {r['solve_seconds']:.1f} s, {r['status']}"]
        if late:
            parts.append(f"late: {', '.join(f'{v:g} h' for v in late.values())}")
        parts += [f"{title} in {n} pieces today ({touching} touching)" for title, n, touching in pieces if n > 1]
        out.append(Happening(at=ctx.local(r["created_utc"]) or "", kind="plan", summary="; ".join(parts)))
    return out


def pieces_today(ctx: Ctx, plan_id: int, lo: str, hi: str) -> list[tuple[str, int, int]]:
    """Each item's block count today in that plan, and how many of them touch the one before: the mark of a
    sitting cut up by replans."""
    found = rows(
        ctx.conn,
        "SELECT b.item_id, i.title, b.start_utc, b.end_utc FROM blocks b JOIN items i ON i.id = b.item_id "
        "WHERE b.plan_id = ? AND b.start_utc >= ? AND b.start_utc < ? ORDER BY b.item_id, b.start_utc",
        [plan_id, lo, hi],
    )
    out: list[tuple[str, int, int]] = []
    by_item: dict[int, list[dict[str, Any]]] = {}
    for r in found:
        by_item.setdefault(r["item_id"], []).append(r)
    for blocks in by_item.values():
        touching = sum(1 for a, b in zip(blocks, blocks[1:], strict=False) if a["end_utc"] == b["start_utc"])
        out.append((blocks[0]["title"], len(blocks), touching))
    return out


def failed_jobs(ctx: Ctx, since: str) -> list[Happening]:
    return [
        Happening(at=ctx.local(r["last_run_utc"]) or "", kind="job", summary=f"{r['name']} failed: {r['last_error']}")
        for r in rows(
            ctx.conn,
            "SELECT * FROM job_runs WHERE user_id = ? AND last_status = 'error' AND last_run_utc >= ?",
            [ctx.user_id, since],
        )
    ]
