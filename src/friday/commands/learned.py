"""Learned durations and the learned energy map, wired (DESIGN §21.7): the nightly fit, and what new items and the
planner take from it. Results are kept in `kv` (`learned_durations`, `learned_energy`), each with whether you
approved it; in `auto` mode it is used without asking. Both learn from default-pace days only.
"""

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from friday.api.commands import Changed, LearnModuleInput
from friday.commands.estimates import in_use
from friday.commands.progress import day_bounds
from friday.commands.registry import Ctx, command
from friday.commands.writer import Writer
from friday.core.db import one, rows
from friday.core.pace import dials_on
from friday.core.textnorm import similarity, type_text
from friday.core.time import format_utc, parse_utc, planning_date, to_local
from friday.estimate.durations import LEARNED_SOURCES, estimate_length
from friday.learn.durations import Done, abs_log_error, fit
from friday.learn.energy import Seen, prices
from friday.planner.snapshot import pace_periods
from friday.planner.store import kv_get, load_settings

MIN_DONE = 5  # fewer completions than this: the §6.6 estimator stands
HELD_OUT = 20  # the newest completions the model is scored on without seeing them
ENERGY_DAYS = 56


def kinds(titles: list[str], min_similarity: float) -> list[str]:
    """Each title's kind: single-linkage clusters of type text, named by their first title."""
    words = [type_text(t.split()) for t in titles]
    kind = list(range(len(titles)))

    def root(i: int) -> int:
        while kind[i] != i:
            kind[i] = kind[kind[i]]
            i = kind[i]
        return i

    for i in range(len(titles)):
        for j in range(i):
            if similarity(words[i], words[j]) >= min_similarity:
                kind[root(i)] = root(j)
    return [" ".join(words[root(i)]) for i in range(len(titles))]


def default_pace_days(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> Any:
    periods, paces, default = list(pace_periods(conn, user_id)), settings["paces"], settings["pace"].default

    def is_default(day: date) -> bool:
        return dials_on(day, periods, paces, default, settings["pace"].weekly) == paces[default]

    return is_default


def learn_nightly(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> None:
    """Refit both; the server's nightly job and the simulator run this."""
    settings = load_settings(conn, user_id)
    if settings["time"].timezone is None or settings["sleep"] is None:
        return
    if settings["learn"].durations != "off":
        keep(conn, user_id, "learned_durations", fit_durations(conn, settings, now_utc, user_id))
    if settings["learn"].energy != "off":
        keep(conn, user_id, "learned_energy", fit_energy(conn, settings, now_utc, user_id))


def keep(conn: sqlite3.Connection, user_id: int, name: str, value: dict[str, Any] | None) -> None:
    if value is None:
        return
    value["approved"] = (kv_get(conn, name, {}, user_id) or {}).get("approved", False)
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT (user_id, key) DO UPDATE SET value = "
        "excluded.value",
        [user_id, name, json.dumps(value)],
    )


def fit_durations(conn: sqlite3.Connection, settings: dict[str, Any], now_utc: int, user_id: int) -> dict | None:
    est, tz, day_start = settings["estimate"], settings["time"].timezone, settings["time"].grid_spec().day_start
    is_default = default_pace_days(conn, settings, user_id)
    since = format_utc(now_utc - est.window_days * 1440)
    found = [
        r
        for r in rows(
            conn,
            f"SELECT * FROM completions WHERE user_id = ? AND completed_utc >= ? AND actual_source IN "
            f"({', '.join('?' * len(LEARNED_SOURCES))}) ORDER BY completed_utc",
            [user_id, since, *LEARNED_SOURCES],
        )
        if is_default(planning_date(parse_utc(r["completed_utc"]), tz, day_start))
    ]
    if len(found) < MIN_DONE:
        return None
    kind = kinds([r["norm_title"] for r in found], est.min_similarity)
    done = [Done(r["actual_minutes"], r["area"], r["preset"], k) for r, k in zip(found, kind, strict=True)]
    model = fit(done)
    score = scores(conn, settings, found, done, user_id) if len(found) >= HELD_OUT + MIN_DONE else None
    return {"model": model.to_json(), "fitted_utc": format_utc(now_utc), **(score or {})}


def scores(conn: sqlite3.Connection, settings: dict[str, Any], found: list, done: list[Done], user_id: int) -> dict:
    """The model fitted without the newest completions, against the §6.6 estimator, on those completions."""
    split = len(done) - HELD_OUT
    model = fit(done[:split])
    learned, old, actual = [], [], []
    for row, d in zip(found[split:], done[split:], strict=True):
        learned.append(model.minutes(d.area, d.preset, d.kind, False))
        past = [r for r in found[:split] if (r["area"] == row["area"] if row["area"] else r["preset"] == row["preset"])]
        estimate = estimate_length(
            row["norm_title"], row["area"], past[::-1], settings["estimate"], settings["text"].rules()
        )
        old.append(estimate.units * 15 if estimate else learned[-1])
        actual.append(d.minutes)
    error, before = abs_log_error(learned, actual), abs_log_error(old, actual)
    return {"error": round(error, 3), "error_before": round(before, 3), "better": error < before}


def fit_energy(conn: sqlite3.Connection, settings: dict[str, Any], now_utc: int, user_id: int) -> dict | None:
    """Whether each day's deep and light blocks happened as planned (§21.7), half hour by half hour."""
    tz, day_start = settings["time"].timezone, settings["time"].grid_spec().day_start
    today = planning_date(now_utc, tz, day_start)
    is_default = default_pace_days(conn, settings, user_id)
    ctx = Ctx(conn, Writer(conn, user_id), now_utc, "job", user_id, settings)
    energy = {r["id"]: r["energy"] for r in rows(conn, "SELECT id, energy FROM items WHERE user_id = ?", [user_id])}
    sessions: dict[int, list[tuple[int, int, int]]] = {}
    for r in rows(
        conn,
        "SELECT item_id, start_utc, end_utc, minutes, source, block_key FROM progress WHERE user_id = ? "
        "AND start_utc >= ?",
        [user_id, format_utc(now_utc - (ENERGY_DAYS + 1) * 1440)],
    ):
        if r["source"] == "timer" and r["start_utc"]:
            sessions.setdefault(r["item_id"], []).append(
                (parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), r["minutes"])
            )
    answered = {
        r["block_key"]: r["minutes"]
        for r in rows(
            conn,
            "SELECT block_key, minutes FROM progress WHERE user_id = ? AND source = 'review' AND block_key IS NOT NULL",
            [user_id],
        )
    }
    seen = []
    for back in range(1, ENERGY_DAYS + 1):
        day = today - timedelta(days=back)
        if not is_default(day) or day_bounds(ctx, day)[1] > now_utc:
            continue
        for b in day_plan(ctx, day):
            if energy.get(b["item_id"]) not in ("deep", "light"):
                continue
            start, end = parse_utc(b["start_utc"]), parse_utc(b["end_utc"])
            timed = [s for s in sessions.get(b["item_id"], []) if abs(s[0] - start) <= 15]
            happened = bool(timed) or answered.get(f"T{b['item_id']}@{b['start_utc']}", 0) > 0
            speed = (sum(s[2] for s in timed) / max(1, end - start)) if timed else None
            for minute in range(start, end, 30):
                local = to_local(minute, tz)
                seen.append(Seen(local.weekday(), (local.hour * 60 + local.minute) // 30, happened, speed))
    if not seen:
        return None
    return {"prices": prices(seen), "observations": len(seen), "fitted_utc": format_utc(now_utc)}


def day_plan(ctx: Ctx, day: date) -> list[dict[str, Any]]:
    """That day's blocks in the last plan saved before it ended: what was planned as the day went, past blocks kept."""
    lo, hi = day_bounds(ctx, day)
    found = one(
        ctx.conn,
        "SELECT id FROM plans WHERE user_id = ? AND created_utc < ? ORDER BY id DESC LIMIT 1",
        [ctx.user_id, format_utc(hi)],
    )
    if found is None:
        return []
    return rows(
        ctx.conn,
        "SELECT * FROM blocks WHERE plan_id = ? AND start_utc >= ? AND start_utc < ?",
        [found["id"], format_utc(lo), format_utc(hi)],
    )


def learned_energy(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> list[list[float]] | None:
    kept = kv_get(conn, "learned_energy", None, user_id)
    return kept["prices"] if in_use(settings, kept, "energy") else None


@command("learn_module", affects_plan=True)
def learn_module(ctx: Ctx, inp: LearnModuleInput) -> Changed:
    """Use, or stop using, learned durations or the learned energy map (your approval in suggest mode)."""
    name = f"learned_{inp.module}"
    kept = kv_get(ctx.conn, name, None, ctx.user_id)
    if kept is None:
        return Changed(message="Nothing learned yet")
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": name}, {"value": json.dumps(kept | {"approved": inp.use})})
    what = "durations" if inp.module == "durations" else "good and bad hours"
    return Changed(message=f"Using learned {what}" if inp.use else f"Stopped using learned {what}")
