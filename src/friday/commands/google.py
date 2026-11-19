"""Publishing the plan to Google Calendar (DESIGN §22.3): the current plan's blocks from now to the end of the
horizon become the events of a "Friday" calendar, at most once every `gcal.publish_debounce_s`, and only when the
plan changed. Fixed items aren't blocks, so what came from Google is never copied back. The server's job loop runs
this every minute; kv `gcal_publish` keeps the calendar id, the account it's in (the first connected, unless it was
made in another that's still there) and what was published last.
"""

import json
import sqlite3
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from friday.core import vacations as breaks
from friday.core.db import rows
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_date
from friday.core.vacations import on_a_break
from friday.planner.prepare import block_key
from friday.planner.store import current_plan, kv_get, load_settings
from friday.sync import gcal, google_auth


def publish_plan(
    conn: sqlite3.Connection, now_utc: int, user_id: int = 1, folder: Path | None = None, google: Any | None = None
) -> bool:
    """Publish when it is due; returns whether it did."""
    settings = load_settings(conn, user_id)
    wanted, saved = settings["gcal"], current_plan(conn, user_id)
    if not wanted.publish or saved is None:
        return False
    state = kv_get(conn, "gcal_publish", {}, user_id) or {}
    if state.get("plan") == saved["id"]:
        return False
    if state.get("at") and (now_utc - parse_utc(state["at"])) * 60 < wanted.publish_debounce_s:
        return False
    apis = google_auth.per_account(google, folder, google_auth.calendar)
    account = google_auth.which(apis, state.get("account"))
    account = next(iter(apis), None) if account is None else account  # its account was removed: the first's now
    service = apis[account]() if account is not None else None
    if service is None:
        return False
    calendar = gcal.own_calendar(service, state.get("calendar"), settings["time"].timezone)
    until = now_utc + settings["time"].horizon_days * 24 * 60
    gcal.publish(
        service,
        calendar,
        blocks(conn, saved["id"], now_utc, until, settings["notify"].app_url, on_a_break(conn, user_id, settings))
        + break_blocks(conn, user_id, settings, now_utc, until),
        gcal.rfc3339(now_utc),
    )
    state = {"calendar": calendar, "account": account, "plan": saved["id"], "at": format_utc(now_utc)}
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'gcal_publish', ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(state)],
    )
    return True


def mode_said(v: breaks.Vacation) -> str:
    """ "Off: nothing to do." or "Light: about 2h of work a day.", as the break's event says it."""
    if v.mode == "off":
        return "Off: nothing to do."
    hours, minutes = divmod(v.work_min, 60)
    amount = f"{hours}h {minutes}m" if hours and minutes else f"{hours}h" if hours else f"{minutes}m"
    return f"Light: about {amount} of work a day."


def break_blocks(conn: sqlite3.Connection, user_id: int, settings: Any, now_utc: int, until: int) -> list[gcal.Block]:
    """Each break from today to the end of the horizon as one all-day event on Friday's calendar (19 Nov, your choice
    "One event on Friday's calendar"): from today if it's under way, through its last day (the end is the day after,
    as calendars count it). Its key is the break's, so a break changed is its event changed."""
    tz, day_start = settings["time"].timezone, minutes_of(settings["time"].day_start)
    if tz is None:
        return []
    today, last = planning_date(now_utc, tz, day_start), planning_date(until, tz, day_start)
    return [
        gcal.Block(key=f"break:{v.id}", title=v.name, start=max(v.first, today).isoformat(),
                   end=(v.last + timedelta(days=1)).isoformat(), tentative=False, link=mode_said(v), all_day=True)
        for v in breaks.load(conn, user_id, settings["breaks"])
        if v.last >= today and v.first <= last
    ]  # fmt: skip


def blocks(
    conn: sqlite3.Connection,
    plan_id: int,
    now_utc: int,
    until: int,
    app_url: str | None,
    on_break: Callable[[str], bool] = lambda _start: False,
) -> list[gcal.Block]:
    """The plan's blocks for a calendar of it (Google's "Friday", the Mac's), but none on a break day: those days are a
    list, not times (core/vacations.py; 18 Nov, they went back onto the phone as times)."""
    found = rows(
        conn,
        "SELECT b.item_id, b.start_utc, b.end_utc, b.tentative, i.title FROM blocks b JOIN items i ON i.id = b.item_id "
        "WHERE b.plan_id = ? AND b.end_utc > ? AND b.start_utc < ? ORDER BY b.start_utc",
        [plan_id, format_utc(now_utc), format_utc(until)],
    )
    return [
        gcal.Block(
            key=block_key(r["item_id"], parse_utc(r["start_utc"])),
            title=r["title"],
            start=gcal.rfc3339(parse_utc(r["start_utc"])),
            end=gcal.rfc3339(parse_utc(r["end_utc"])),
            tentative=bool(r["tentative"]),
            link=f"{app_url.rstrip('/')}/#/" if app_url else None,
        )
        for r in found
        if not on_break(r["start_utc"])
    ]
