"""The snapshot (DESIGN §15.1): everything a solve needs, read in one transaction, frozen and picklable.

Replans are reproducible from a saved snapshot: nothing after this point reads the database or the clock.
"""

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

import numpy as np

from friday.core.calendars import left_out
from friday.core.db import one, rows
from friday.core.items import Item
from friday.core.pace import Dials, PacePeriod
from friday.core.rows import item_from_row
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_date, to_local, to_utc
from friday.learn.sleep import Mark, learn, nights_from
from friday.learn.state import loadings
from friday.planner.cushion import cushion, cushioned
from friday.planner.progress import progress_rows
from friday.planner.store import (
    area_names,
    current_plan,
    event_links,
    generation,
    kv_get,
    load_settings,
    settings_version,
)


@dataclass(frozen=True)
class PinRow:
    id: int
    item_id: int
    start_utc: int
    end_utc: int
    kind: str


@dataclass(frozen=True)
class BlockRow:
    item_id: int
    start_utc: int
    end_utc: int
    tentative: bool = False


@dataclass(frozen=True)
class SleepFacts:
    """What tracked sleep tells the planner (Settings → Schedule → Track my sleep; None while it's off)."""

    routine_min: dict[str, int]  # your morning routine, learned, by the morning's weekday
    slept_min: dict[date, int]  # each recorded night's sleep, by its evening
    woke_utc: int | None = None  # this morning's "I'm up"
    ready: bool = False  # this morning's "Ready to work", or a timer started since waking


@dataclass(frozen=True)
class Snapshot:
    user_id: int
    now_utc: int
    generation: int
    settings: dict[str, Any]
    settings_version: int
    items: tuple[Item, ...]  # todo flexible items, fixed items in range, and the parents of either
    dependencies: tuple[tuple[int, int, float, int], ...]  # item, depends on, fraction, lag
    pins: tuple[PinRow, ...]
    progress: dict[int, tuple[dict[str, Any], ...]]
    timer: tuple[int, int] | None  # item id, start
    day_overrides: dict[date, dict[str, Any]]
    pace_periods: tuple[PacePeriod, ...]
    areas: dict[int, str]
    reviewed_dates: frozenset[date]
    plan_id: int | None
    plan_blocks: tuple[BlockRow, ...]
    # The first replan after a pace switch loosens minimize_changes (to `pace.switch_stability`), and after a rule or
    # schedule change drops it: you asked for a different plan, so holding the old one would hide the change.
    next_stability: float | None
    log_since_plan: tuple[dict[str, Any], ...]  # the commands since the current plan, for the change list
    last_command_id: int  # the newest command this snapshot has seen
    multipliers: dict[str, float] = field(default_factory=dict)  # learned θ in effect (DESIGN §21.8)
    profile_version: int = 0  # 0: nothing learned yet
    cold_once: bool = False  # the next solve starts afresh, not from the current plan (a picked other way)
    sleep: SleepFacts | None = None


def take_snapshot(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> Snapshot:
    conn.execute("BEGIN")
    try:
        return read_snapshot(conn, now_utc, user_id)
    finally:
        conn.execute("COMMIT")


def read_snapshot(conn: sqlite3.Connection, now_utc: int, user_id: int) -> Snapshot:
    settings = with_learned_energy(conn, load_settings(conn, user_id), user_id)
    settings = with_rule_wins(conn, with_picked_way(conn, now_utc, settings, user_id), user_id)
    plan = current_plan(conn, user_id)
    plan_blocks = (
        tuple(
            BlockRow(r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), bool(r["tentative"]))
            for r in rows(conn, "SELECT * FROM blocks WHERE plan_id = ?", [plan["id"]])
        )
        if plan
        else ()
    )
    return Snapshot(
        user_id=user_id,
        now_utc=now_utc,
        generation=generation(conn, user_id),
        settings=settings,
        settings_version=settings_version(conn, user_id),
        items=snapshot_items(conn, now_utc, settings, user_id),
        dependencies=tuple(
            (r["item_id"], r["depends_on_id"], r["fraction"], r["lag_min"])
            for r in rows(conn, "SELECT * FROM dependencies WHERE user_id = ?", [user_id])
        ),
        pins=tuple(
            PinRow(r["id"], r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), r["kind"])
            for r in rows(conn, "SELECT * FROM pins WHERE user_id = ? ORDER BY id", [user_id])
        ),
        progress={k: tuple(v) for k, v in progress_rows(conn, user_id).items()},
        timer=timer(conn, user_id),
        day_overrides=day_overrides(conn, user_id),
        pace_periods=pace_periods(conn, user_id),
        areas=area_names(conn, user_id),
        reviewed_dates=frozenset(
            date.fromisoformat(r["date"]) for r in rows(conn, "SELECT date FROM reviews WHERE user_id = ?", [user_id])
        ),
        plan_id=plan["id"] if plan else None,
        plan_blocks=plan_blocks,
        next_stability=kv_get(conn, "next_stability", None, user_id),
        cold_once=kv_get(conn, "next_cold", None, user_id) is not None,
        sleep=sleep_facts(conn, now_utc, settings, user_id),
        **learned(conn, now_utc, settings, user_id),
        log_since_plan=log_since(conn, json.loads(plan["report"]).get("last_command_id", 0) if plan else 0, user_id),
        last_command_id=int(
            conn.execute("SELECT coalesce(max(id), 0) FROM command_log WHERE user_id = ?", [user_id]).fetchone()[0]
        ),
    )


LEARN_DAYS = 56


def sleep_facts(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> SleepFacts | None:
    """The last eight weeks of sleep taps, as the planner uses them: your routine, your nights, this morning."""
    tracking = settings["sleep_tracking"]
    tz = settings["time"].timezone
    if not tracking.on or settings["sleep"] is None or tz is None:
        return None
    since = format_utc(now_utc - LEARN_DAYS * 1440)
    marks = [
        Mark(r["id"], r["kind"], to_local(parse_utc(r["at_utc"]), tz))
        for r in rows(conn, "SELECT * FROM sleep_marks WHERE user_id = ? AND at_utc >= ?", [user_id, since])
    ]
    timers = [
        to_local(parse_utc(r["start_utc"]), tz)
        for r in rows(
            conn,
            "SELECT start_utc FROM progress WHERE user_id = ? AND source = 'timer' AND start_utc >= ?",
            [user_id, since],
        )
    ]
    nights = nights_from(marks, timers, minutes_of(settings["time"].day_start))
    morning = nights.get(to_local(now_utc, tz).date() - timedelta(days=1))
    return SleepFacts(
        routine_min=learn(nights.values(), tracking.min_nights).routine_min,
        slept_min={d: n.slept_min for d, n in nights.items() if n.slept_min is not None},
        woke_utc=to_utc(morning.up.at, tz) if morning and morning.up else None,
        ready=bool(morning and morning.ready_at),
    )


def snapshot_items(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> tuple[Item, ...]:
    """Todo items, plus fixed items from a day ago to past the allocator's horizon (with a week to spare)."""
    days = settings["time"].allocator_weeks * 7 + 7
    calendars = {item_id: link.calendar for item_id, link in event_links(conn, user_id).items()}
    areas, memo = area_names(conn, user_id), {}
    found = rows(
        conn,
        "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND (when_kind != 'fixed' "
        "OR (end_utc > ? AND start_utc < ?))",
        [user_id, format_utc(now_utc - 1440), format_utc(now_utc + days * 1440)],
    )
    items = {}
    for r in found:
        item = busy_as_you_count(item_from_row(r), settings, calendars)
        area = areas.get(item.area_id) if item.area_id is not None else None
        factor = cushion(conn, area, item.preset, now_utc, settings, user_id, memo) if item.when != "fixed" else 1.0
        items[r["id"]] = cushioned(item, factor)
    missing = {i.parent_id for i in items.values() if i.parent_id is not None} - set(items)
    while missing:
        parents = rows(conn, f"SELECT * FROM items WHERE id IN ({', '.join('?' * len(missing))})", list(missing))
        items |= {r["id"]: item_from_row(r) for r in parents}
        missing = {i.parent_id for i in items.values() if i.parent_id is not None} - set(items)
    return tuple(items[k] for k in sorted(items))


def busy_as_you_count(item: Item, settings: dict[str, Any], calendars: dict[int, str]) -> Item:
    """An event left out of planning (a due reminder, marked free, filtered, a calendar of room bookings; COMBINED.md
    28) is kept in the snapshot but blocks no time."""
    if item.when != "fixed" or not item.blocks_time:
        return item
    reason = left_out(item.title, calendars.get(item.id or 0), item.free, settings["categories"], settings["busy"])
    return replace(item, blocks_time=False) if reason else item


def timer(conn: sqlite3.Connection, user_id: int) -> tuple[int, int] | None:
    found = conn.execute("SELECT item_id, start_utc FROM timer WHERE user_id = ?", [user_id]).fetchone()
    return (found["item_id"], parse_utc(found["start_utc"])) if found else None


def with_picked_way(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> dict[str, Any]:
    """The rules' weights as the other way you picked had them (COMBINED.md 25), for a week, while what you learned
    from the pick catches up."""
    way = kv_get(conn, "other_way", None, user_id)
    if not way or parse_utc(way["until"]) <= now_utc:
        return settings
    return picked(settings, way["weights"], way.get("seed", 0))


WIN = 3.0  # an answer to "Which should win?": the winner weighs ×3, the other ÷3


def with_rule_wins(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> dict[str, Any]:
    """The rules' weights with your answers to "Which should win?" (COMBINED.md 66), each for its pair of rules."""
    names = {r.name for r in settings["rules"]}
    factors: dict[str, float] = {}
    for answer in kv_get(conn, "rule_wins", [], user_id):
        winner, loser = answer["winner"], answer["loser"]
        if winner in names and loser in names:
            factors[winner] = factors.get(winner, 1.0) * WIN
            factors[loser] = factors.get(loser, 1.0) / WIN
    return picked(settings, factors, 0) if factors else settings


def picked(settings: dict[str, Any], factors: dict[str, float], seed: int) -> dict[str, Any]:
    """Settings as another way plans with them: each rule's weight times its factor, and the search seed moved on."""
    rules = tuple(r.model_copy(update={"weight": r.weight * factors.get(r.name, 1.0)}) for r in settings["rules"])
    engine = settings["engine"].model_copy(update={"seed": settings["engine"].seed + seed})
    return settings | {"rules": rules, "engine": engine}


def with_learned_energy(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> dict[str, Any]:
    """Your energy map plus the learned prices (§21.7), in auto mode or once you approved them."""
    kept = kv_get(conn, "learned_energy", None, user_id)
    mode = settings["learn"].energy
    if not kept or mode == "off" or (mode == "suggest" and not kept.get("approved")):
        return settings
    mine, learned = settings["energy_map"], kept["prices"]
    summed = tuple(
        tuple(a + b for a, b in zip(row, extra, strict=True)) for row, extra in zip(mine, learned, strict=True)
    )
    return settings | {"energy_map": summed}


def learned(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> dict[str, Any]:
    """The active learned profile's multipliers: θ, times the state units' effect while state inference is on, its
    gate is open and no pace was picked for today (a picked pace always wins, §21.3)."""
    if settings["learn"].weights == "off":
        return {}
    found = one(
        conn,
        "SELECT * FROM learned_profile WHERE user_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
        [user_id],
    )
    if found is None:
        return {}
    theta = json.loads(found["theta"])
    state = json.loads(found["state"]) if found["state"] else None
    today = planning_date(now_utc, settings["time"].timezone, minutes_of(settings["time"].day_start))
    paced = any(
        p.start_date <= today and (p.end_date is None or today <= p.end_date) for p in pace_periods(conn, user_id)
    )
    if settings["learn"].state_inference == "on" and state and state.get("on") and not paced:
        rules = tuple(theta)
        effect = np.exp(np.clip(np.array(state["h"]) @ loadings(rules), -5, 5))
        theta = {r: t * float(e) for r, t, e in zip(rules, theta.values(), effect, strict=True)}
    return {"multipliers": theta, "profile_version": int(found["version"])}


def day_overrides(conn: sqlite3.Connection, user_id: int) -> dict[date, dict[str, Any]]:
    return {
        date.fromisoformat(r["date"]): {k: r[k] for k in ("bedtime", "wake", "margin_min", "cap_hours")}
        for r in rows(conn, "SELECT * FROM day_overrides WHERE user_id = ?", [user_id])
    }


def pace_periods(conn: sqlite3.Connection, user_id: int) -> tuple[PacePeriod, ...]:
    return tuple(
        PacePeriod(
            r["pace_name"],
            Dials.model_validate(json.loads(r["dials"])),
            date.fromisoformat(r["start_date"]),
            date.fromisoformat(r["end_date"]) if r["end_date"] else None,
        )
        for r in rows(conn, "SELECT * FROM pace_periods WHERE user_id = ? ORDER BY start_date", [user_id])
    )


def log_since(conn: sqlite3.Connection, after_id: int, user_id: int) -> tuple[dict[str, Any], ...]:
    found = rows(
        conn,
        "SELECT id, actor, command, input FROM command_log WHERE user_id = ? AND id > ? "
        "AND undo IS NOT NULL ORDER BY id",
        [user_id, after_id],
    )
    return tuple(r | {"input": json.loads(r["input"])} for r in found)
