"""The snapshot (DESIGN §15.1): everything a solve needs, read in one transaction, frozen and picklable.

Replans are reproducible from a saved snapshot: nothing after this point reads the database or the clock.
"""

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from statistics import median
from typing import Any

import numpy as np

from friday.core.calendars import left_out
from friday.core.db import one, rows
from friday.core.items import Item
from friday.core.pace import Dials, PacePeriod
from friday.core.rows import item_from_row
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_date, to_local, to_zoned, utc_minutes
from friday.learn import guard
from friday.learn.sleep import NAP_USUAL_MIN, Mark, evening_of, learn, nights_from, usual_nap
from friday.learn.state import loadings
from friday.planner.cushion import SHARES, cushion, cushioned, shortened
from friday.planner.progress import progress_rows, recorded_minutes
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
    wind_down_min: dict[str, int] = field(default_factory=dict)  # done with work to bed, learned, by the evening
    done_utc: int | None = None  # tonight's "Done with work", before going to bed
    napped_min: dict[date, int] = field(default_factory=dict)  # naps, by their planning day


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
    eating: tuple[int, int] | None = None  # the routine of the meal you're eating (Sleep & meals), and its start
    going: frozenset[int] = frozenset()  # optional events you said you'd go to this time (`event_keep`): walled off
    away: tuple[str, int, int] | None = None  # a nap or a snack now (`away`): what, since when, until when
    alongside: tuple[tuple[int, int], ...] = ()  # timed at once with `timer` (item id, start): their time counts
    # Repeats whose times are kept apart (planner/spacing.py): days between, and the last done time's start, end, due.
    series_gaps: dict[int, float] = field(default_factory=dict)
    series_last: dict[int, tuple[int, int, int | None]] = field(default_factory=dict)


def series_spacing(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    """Each spaced repeat's days between times, and its last done time: when its work began, ended and was due."""
    gaps = {
        r["id"]: float(r["min_gap_days"])
        for r in rows(
            conn, "SELECT id, min_gap_days FROM series WHERE user_id = ? AND min_gap_days IS NOT NULL", [user_id]
        )  # fmt: skip
    }
    last: dict[int, tuple[int, int, int | None]] = {}
    if gaps:
        done = rows(
            conn,
            f"SELECT i.id, i.series_id, i.due_utc, c.completed_utc, c.actual_minutes, "
            f"(SELECT min(p.start_utc) FROM progress p WHERE p.item_id = i.id) AS began, "
            f"(SELECT max(p.end_utc) FROM progress p WHERE p.item_id = i.id) AS ended FROM completions c "
            f"JOIN items i ON i.id = c.item_id WHERE c.user_id = ? AND i.series_id IN ({', '.join('?' * len(gaps))}) "
            f"ORDER BY c.completed_utc DESC",
            [user_id, *gaps],
        )
        for r in done:
            if r["series_id"] not in last:
                # When the work was done, as its timed or logged sessions say; else the done time less its length.
                end = parse_utc(r["ended"] or r["completed_utc"])
                began = parse_utc(r["began"]) if r["began"] else end - int(r["actual_minutes"] or 0)
                due = parse_utc(r["due_utc"]) if r["due_utc"] else None
                last[r["series_id"]] = (began, end, due)
    return {"series_gaps": gaps, "series_last": last}


def take_snapshot(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> Snapshot:
    conn.execute("BEGIN")
    try:
        return read_snapshot(conn, now_utc, user_id)
    finally:
        conn.execute("COMMIT")


def read_snapshot(conn: sqlite3.Connection, now_utc: int, user_id: int) -> Snapshot:
    from friday.planner.holds import held  # it builds PinRows, defined here

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
    progress = progress_rows(conn, user_id)
    # An event that holds a task's time gives it to the task (planner/holds.py).
    items, pins = held(
        snapshot_items(conn, now_utc, settings, user_id),
        tuple(
            PinRow(r["id"], r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), r["kind"])
            for r in rows(conn, "SELECT * FROM pins WHERE user_id = ? ORDER BY id", [user_id])
        ),
        event_holds(conn, user_id),
        {k: recorded_minutes(v) for k, v in progress.items()},
        now_utc,
        frozenset(kv_get(conn, "event_holds_loose", [], user_id) or []),
    )
    timed = timers(conn, user_id)
    return Snapshot(
        user_id=user_id,
        now_utc=now_utc,
        generation=generation(conn, user_id),
        settings=settings,
        settings_version=settings_version(conn, user_id),
        items=items,
        dependencies=tuple(
            (r["item_id"], r["depends_on_id"], r["fraction"], r["lag_min"])
            for r in rows(conn, "SELECT * FROM dependencies WHERE user_id = ?", [user_id])
        ),
        pins=pins,
        progress={k: tuple(v) for k, v in progress.items()},
        timer=timed[-1] if timed else None,
        alongside=tuple(timed[:-1]),
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
        eating=eating(conn, user_id) if settings["meal_tracking"].on else None,
        away=away(conn, now_utc, settings, user_id),
        going=frozenset(kv_get(conn, "events_kept", [], user_id)),
        **series_spacing(conn, user_id),
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
        Mark(r["id"], r["kind"], to_zoned(parse_utc(r["at_utc"]), tz))
        for r in rows(conn, "SELECT * FROM sleep_marks WHERE user_id = ? AND at_utc >= ?", [user_id, since])
    ]
    timed = rows(
        conn,
        "SELECT start_utc, end_utc FROM progress WHERE user_id = ? AND source = 'timer' AND start_utc >= ?",
        [user_id, since],
    )
    starts = [to_zoned(parse_utc(r["start_utc"]), tz) for r in timed]
    ends = [to_zoned(parse_utc(r["end_utc"]), tz) for r in timed if r["end_utc"]]
    day_start = minutes_of(settings["time"].day_start)
    nights = nights_from(marks, starts, day_start, ends)
    morning = nights.get(to_local(now_utc, tz).date() - timedelta(days=1))
    tonight = nights.get(evening_of(to_local(now_utc, tz), day_start))
    learned = learn(nights.values(), tracking.min_nights)
    napped: dict[date, int] = {}
    for r in rows(conn, "SELECT * FROM naps WHERE user_id = ? AND end_utc IS NOT NULL AND start_utc >= ?",
                  [user_id, since]):  # fmt: skip
        day = date.fromisoformat(r["date"])
        napped[day] = napped.get(day, 0) + parse_utc(r["end_utc"]) - parse_utc(r["start_utc"])
    return SleepFacts(
        routine_min=learned.routine_min,
        wind_down_min=learned.wind_down_min,
        done_utc=utc_minutes(tonight.done.at) if tonight and tonight.done and not tonight.bed else None,
        slept_min={d: n.slept_min for d, n in nights.items() if n.slept_min is not None},
        woke_utc=utc_minutes(morning.up.at) if morning and morning.up else None,
        ready=bool(morning and morning.ready_at),
        napped_min=napped,
    )


def snapshot_items(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> tuple[Item, ...]:
    """Todo items, plus fixed items from a day ago to past the allocator's horizon (with a week to spare)."""
    days = settings["time"].allocator_weeks * 7 + 7
    calendars = {item_id: link.calendar for item_id, link in event_links(conn, user_id).items()}
    areas, memo, shares = area_names(conn, user_id), {}, kv_get(conn, SHARES, {}, user_id) or {}
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
        items[r["id"]] = shortened(cushioned(item, factor), shares.get(item.preset or "") if factor <= 1 else None)
    missing = {i.parent_id for i in items.values() if i.parent_id is not None} - set(items)
    while missing:
        parents = rows(conn, f"SELECT * FROM items WHERE id IN ({', '.join('?' * len(missing))})", list(missing))
        items |= {r["id"]: item_from_row(r) for r in parents}
        missing = {i.parent_id for i in items.values() if i.parent_id is not None} - set(items)
    return tuple(items[k] for k in sorted(without_finished_projects(items, with_steps(conn, user_id))))


def without_finished_projects(items: dict[int, Item], projects: set[int]) -> dict[int, Item]:
    """Less the projects with nothing left in them: once a project's steps are all done, the planner would plan its own
    length as work (13 Nov: 6h15 of "CDJ Article" planned after its three steps were ticked off). Leaving one out can
    leave the project around it with nothing left too, so until none is."""
    items = dict(items)
    while True:
        parents = {i.parent_id for i in items.values() if i.parent_id is not None}
        finished = [k for k, i in items.items() if k in projects and k not in parents and i.when != "fixed"]
        if not finished:
            return items
        for k in finished:
            del items[k]


def with_steps(conn: sqlite3.Connection, user_id: int) -> set[int]:
    """Items with steps in them (a project): their steps are their work, so the item itself is never planned and never
    late or unplanned on its own; it is judged by its steps (13 Nov: a project whose steps were all planned days before
    its due was called "not planned before it's due"). A step done still counts; one deleted doesn't."""
    found = rows(
        conn,
        "SELECT DISTINCT parent_id FROM items WHERE user_id = ? AND parent_id IS NOT NULL AND status != 'dropped'",
        [user_id],
    )
    return {r["parent_id"] for r in found}


def event_holds(conn: sqlite3.Connection, user_id: int) -> dict[int, int]:
    """Each event that holds a task's time, and the task (`event_hold`)."""
    return {int(e): int(t) for e, t in (kv_get(conn, "event_holds", {}, user_id) or {}).items()}


def busy_as_you_count(item: Item, settings: dict[str, Any], calendars: dict[int, str]) -> Item:
    """An event left out of planning (a due reminder, marked free, filtered, a calendar of room bookings; COMBINED.md
    28) is kept in the snapshot but blocks no time."""
    if item.when != "fixed" or not item.blocks_time:
        return item
    reason = left_out(item.title, calendars.get(item.id or 0), item.free, settings["categories"], settings["busy"])
    return replace(item, blocks_time=False) if reason else item


def timers(conn: sqlite3.Connection, user_id: int) -> list[tuple[int, int]]:
    """Each timer (item id, start), the one started last last: "the timer"."""
    found = conn.execute("SELECT item_id, start_utc FROM timer WHERE user_id = ? ORDER BY start_utc, rowid", [user_id])
    return [(r["item_id"], parse_utc(r["start_utc"])) for r in found]


def eating(conn: sqlite3.Connection, user_id: int) -> tuple[int, int] | None:
    found = conn.execute(
        "SELECT item_id, start_utc FROM meals WHERE user_id = ? AND end_utc IS NULL AND start_utc IS NOT NULL "
        "AND skipped = 0 AND item_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        [user_id],
    ).fetchone()
    return (found["item_id"], parse_utc(found["start_utc"])) if found else None


FORGOTTEN_MIN = 3 * 60  # a nap or a snack running this long was a tap forgotten: nothing is held for it
MEAL_USUAL_MIN = {"snack": 15}  # a meal's length until you've had a few (else half an hour)


def away(conn: sqlite3.Connection, now_utc: int, settings: dict[str, Any], user_id: int) -> tuple[str, int, int] | None:
    """What you're doing now that no planned item stands for (29 Oct: naps and snacks): a nap, or a meal with no
    routine of its name (a snack, a breakfast you don't plan), since when and until it should end: as long as you
    usually nap, or take over that meal."""
    since = format_utc(now_utc - LEARN_DAYS * 1440)
    nap = settings["sleep_tracking"].on and one(
        conn, "SELECT start_utc FROM naps WHERE user_id = ? AND end_utc IS NULL ORDER BY id DESC LIMIT 1", [user_id]
    )
    if nap and now_utc - (start := parse_utc(nap["start_utc"])) <= FORGOTTEN_MIN:
        found = rows(
            conn,
            "SELECT start_utc, end_utc FROM naps WHERE user_id = ? AND end_utc IS NOT NULL AND start_utc >= ?",
            [user_id, since],
        )
        usual = usual_nap(parse_utc(r["end_utc"]) - parse_utc(r["start_utc"]) for r in found) or NAP_USUAL_MIN
        return ("Nap", start, start + usual)
    meal = settings["meal_tracking"].on and one(
        conn,
        "SELECT kind, start_utc FROM meals WHERE user_id = ? AND end_utc IS NULL AND start_utc IS NOT NULL "
        "AND skipped = 0 AND item_id IS NULL ORDER BY id DESC LIMIT 1",
        [user_id],
    )
    if meal and now_utc - (start := parse_utc(meal["start_utc"])) <= FORGOTTEN_MIN:
        lengths = [
            parse_utc(r["end_utc"]) - parse_utc(r["start_utc"])
            for r in rows(
                conn,
                "SELECT start_utc, end_utc FROM meals WHERE user_id = ? AND kind = ? AND end_utc IS NOT NULL "
                "AND start_utc >= ?",
                [user_id, meal["kind"], since],
            )
        ]
        usual = round(median(lengths)) if len(lengths) >= 3 else MEAL_USUAL_MIN.get(meal["kind"], 30)
        return (meal["kind"].capitalize(), start, start + usual)
    return None


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
    held, freed = kv_get(conn, guard.HELD, [], user_id) or [], kv_get(conn, guard.FREED, [], user_id) or []
    theta = guard.guarded(json.loads(found["theta"]), settings["rules"], held, freed)  # never past what you said
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
