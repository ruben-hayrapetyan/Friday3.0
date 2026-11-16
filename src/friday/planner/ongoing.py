"""Ongoing projects: hours a week with no deadline (the Projects page's Ongoing shelf). Each is a weekly repeat of a
Goal (a target amount, from your week's first day), listed under `ONGOING` with its own options. What the planner
reads of them: a short week's carry-over into the next (the item's `neglect_carry` times what the week before fell
short by) and their priority (how much of a pace's push or cut each takes, `core/pace.budget_factor`). Only repeats
made as ongoing projects carry or weigh: a Goal repeat made otherwise plans as it always did."""

import sqlite3
from typing import Any

from friday.core.db import rows
from friday.core.pace import priority_weight
from friday.core.time import UNIT_MIN, parse_utc
from friday.planner.progress import minutes_by_item
from friday.planner.store import kv_get

ONGOING = "ongoing_projects"  # kv, by repeat id: {"rhythm_days", "priority", "paused_until"}
PROJECT_OPTIONS = "project_options"  # kv, by project id: {"pacing"} (commands/project_options.py)
PACINGS = ("front", "linear", "back")


def ongoing_options(conn: sqlite3.Connection, user_id: int = 1) -> dict[str, dict[str, Any]]:
    return dict(kv_get(conn, ONGOING, {}, user_id) or {})


def carried_minutes(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> dict[int, int]:
    """Each ongoing project's open week: what the week before fell short by, times this week's carry, by this week's
    item id. Only once the week before has closed, so a week isn't short while it can still be made up; a week paused
    (dropped) or skipped isn't short. One week back only: a shortfall carried and missed again isn't carried twice."""
    ongoing = {int(k) for k in ongoing_options(conn, user_id)}
    if not ongoing:
        return {}
    found = rows(
        conn,
        f"SELECT id, series_id, due_utc, target_units, neglect_carry, status FROM items WHERE user_id = ? "
        f"AND amount = 'target' AND series_id IN ({', '.join('?' * len(ongoing))}) "
        f"ORDER BY series_id, occurrence_date, id",
        [user_id, *sorted(ongoing)],
    )
    done = minutes_by_item(conn, user_id)
    out: dict[int, int] = {}
    for last, item in zip(found, found[1:], strict=False):
        if last["series_id"] != item["series_id"] or item["status"] != "todo" or not item["neglect_carry"]:
            continue
        if last["status"] not in ("todo", "done") or last["due_utc"] is None or parse_utc(last["due_utc"]) > now_utc:
            continue
        short = (last["target_units"] or 0) * UNIT_MIN - done.get(last["id"], 0)
        if short > 0:
            out[item["id"]] = round(item["neglect_carry"] * short)
    return out


def priorities(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, float]:
    """Each ongoing project's priority as its weight, by repeat id (the middle priority, 1.0, left out)."""
    out = {int(k): priority_weight(v.get("priority")) for k, v in ongoing_options(conn, user_id).items()}
    return {k: v for k, v in out.items() if v != 1.0}


def project_pacing(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, str]:
    """Each project's own pace through its work, by project id: those set on the project (its kind's otherwise)."""
    found = kv_get(conn, PROJECT_OPTIONS, {}, user_id) or {}
    return {int(k): v["pacing"] for k, v in found.items() if v.get("pacing") in PACINGS}
