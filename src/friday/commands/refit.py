"""The fitting side of learning (DESIGN §21): today's comparison questions, and the refit after a review (θ,
answer noise, state, a rule proposal, a wall question) into a new version of the learned profile.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations
from typing import Any

import numpy as np

from friday.commands.registry import Ctx
from friday.core.db import one, rows
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_date, to_local
from friday.learn.preferences import Comparison, answer_scale, design, fit
from friday.learn.proposals import propose
from friday.learn.queries import choose
from friday.learn.state import StateModel, Week
from friday.planner.learning import day_versions, learnable
from friday.planner.snapshot import read_snapshot
from friday.planner.store import load_settings

NOISY = 0.15  # answer noise above which asking stops (§21.4)
AUTO_STEP = 1.5  # in auto mode a weight moves at most ×1.5 or ÷1.5 a week
EMPTY_PROFILE = {
    "proposals": {"pending": None, "accepted": [], "refused": []},
    "walls": {"pending": None, "decided": {}},
}


def profile(conn: sqlite3.Connection, user_id: int, status: str | None = None) -> dict[str, Any] | None:
    sql = "SELECT * FROM learned_profile WHERE user_id = ?" + (" AND status = ?" if status else "")
    found = one(conn, sql + " ORDER BY version DESC LIMIT 1", [user_id, *([status] if status else [])])
    if found is None:
        return None
    return found | {
        k: json.loads(found[k]) if found[k] else None
        for k in ("theta", "state", "proposals", "wall_decisions", "evidence")
    }


def answered(conn: sqlite3.Connection, user_id: int, drag_weight: float) -> tuple[list[Comparison], list[tuple]]:
    """Every answered comparison and drag as (winner, loser), and their template hours."""
    out, extras = [], []
    for r in rows(conn, "SELECT * FROM comparisons WHERE user_id = ? AND answer IN ('a', 'b') ORDER BY id", [user_id]):
        a, b = json.loads(r["features_a"]), json.loads(r["features_b"])
        win, lose = (a, b) if r["answer"] == "a" else (b, a)
        out.append(Comparison(win["rules"], lose["rules"], drag_weight if r["source"] == "drag" else 1.0))
        extras.append((win.get("templates", {}), lose.get("templates", {})))
    return out, extras


def ctx_today(settings: dict[str, Any], now_utc: int) -> date:
    return planning_date(now_utc, settings["time"].timezone, minutes_of(settings["time"].day_start))


def prepare_questions(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> int:
    """Draw today's comparison questions about tomorrow, within the budget (§21.4); returns how many were added.
    The server's job runs this once a day, before the evening review."""
    settings = load_settings(conn, user_id)
    learn = settings["learn"]
    if learn.weights == "off" or settings["time"].timezone is None or settings["sleep"] is None:
        return 0
    today = ctx_today(settings, now_utc)
    start = format_utc(now_utc - 24 * 60)
    asked = rows(conn, "SELECT asked_utc FROM comparisons WHERE user_id = ? AND source = 'question'", [user_id])
    today_count = sum(1 for r in asked if r["asked_utc"] >= start)
    this_week = sum(1 for r in asked if r["asked_utc"] >= format_utc(now_utc - 7 * 1440))
    room = min(learn.questions_per_day - today_count, learn.questions_per_week - this_week)
    found, _ = answered(conn, user_id, learn.drag_weight)
    rules = learnable(settings)
    if room <= 0 or noise(found, rules) > NOISY:
        return 0
    snapshot = read_snapshot(conn, now_utc, user_id)
    theta = snapshot.multipliers or None
    versions = day_versions(snapshot, today + timedelta(days=1), seed=now_utc % 10_000)
    pairs = list(combinations(range(len(versions)), 2))
    made = 0
    for _ in range(room):
        pick = choose(
            [(versions[i].features, versions[j].features) for i, j in pairs],
            found,
            rules,
            theta,
            learn.query_stop_disagreement,
            seed=now_utc % 10_000 + made,
        )
        if pick is None:
            break
        i, j = pairs.pop(pick)
        a, b = versions[i], versions[j]
        conn.execute(
            "INSERT INTO comparisons (user_id, asked_utc, plan_a, plan_b, features_a, features_b, source, dials) "
            "VALUES (?, ?, ?, ?, ?, ?, 'question', ?)",
            [
                user_id,
                format_utc(now_utc),
                json.dumps({"day": str(today + timedelta(days=1)), "blocks": a.blocks}),
                json.dumps({"day": str(today + timedelta(days=1)), "blocks": b.blocks}),
                json.dumps({"rules": a.features, "templates": a.templates}),
                json.dumps({"rules": b.features, "templates": b.templates}),
                json.dumps({}),
            ],
        )
        made += 1
    return made


def noise(found: list[Comparison], rules: tuple[str, ...]) -> float:
    if len(found) < 12:
        return 0.05
    x, weight = design(found, rules)
    return answer_scale(x, np.ones(len(rules)), weight)


def refit(ctx: Ctx) -> int | None:
    """A new profile version when there is new evidence: θ, answer noise, state, a proposal, a wall question.
    In suggest mode it waits for your approval; in auto it applies within ×1.5 a week. Returns the version."""
    learn = ctx.settings["learn"]
    if learn.weights == "off":
        return None
    rules = learnable(ctx.settings)
    found, extras = answered(ctx.conn, ctx.user_id, learn.drag_weight)
    last = profile(ctx.conn, ctx.user_id)
    evidence = {"comparisons": sum(c.weight == 1.0 for c in found), "drags": sum(c.weight != 1.0 for c in found)}
    if last and last["evidence"] and {k: last["evidence"].get(k) for k in evidence} == evidence:
        return None
    if not found:
        return None
    active = profile(ctx.conn, ctx.user_id, "active")
    before = (active or {}).get("theta") or dict.fromkeys(rules, 1.0)
    theta = fit(found, rules, learn.prior_sd, learn.theta_min)
    status = "suggested"
    if learn.weights == "auto":
        theta = {
            r: float(np.clip(t, before.get(r, 1) / AUTO_STEP, before.get(r, 1) * AUTO_STEP)) for r, t in theta.items()
        }
        status = "active"
    base = last or EMPTY_PROFILE | {"wall_decisions": EMPTY_PROFILE["walls"]}
    proposals = dict(base.get("proposals") or EMPTY_PROFILE["proposals"])
    proposals["pending"] = proposals.get("pending") or pending_proposal(ctx, found, extras, rules, proposals)
    walls = dict(base.get("wall_decisions") or EMPTY_PROFILE["walls"])
    walls["pending"] = walls.get("pending") or forbidden_work(ctx, walls)
    changes = [
        {"rule": r, "from": round(before.get(r, 1.0), 2), "to": round(t, 2)}
        for r, t in theta.items()
        if abs(t - before.get(r, 1.0)) / max(before.get(r, 1.0), 1e-9) > 0.1
    ]
    version = (last["version"] if last else 0) + 1
    ctx.db.insert(
        "learned_profile",
        {
            "version": version,
            "created_utc": ctx.now_text,
            "theta": json.dumps(theta),
            "answer_noise": noise(found, rules),
            "state": json.dumps(state(ctx, found, rules)),
            "proposals": json.dumps(proposals),
            "wall_decisions": json.dumps(walls),
            "evidence": json.dumps(evidence | {"changes": changes}),
            "status": status,
        },
    )
    return version


def pending_proposal(
    ctx: Ctx, found: list[Comparison], extras: list[tuple], rules: tuple[str, ...], proposals: dict[str, Any]
) -> str | None:
    """From week `proposal_from_week`, every `proposal_every_weeks`, the best rule template, if it clears the bar."""
    learn = ctx.settings["learn"]
    if learn.proposals == "off" or len(found) < learn.proposal_min_comparisons:
        return None
    first = one(ctx.conn, "SELECT min(asked_utc) AS t FROM comparisons WHERE user_id = ?", [ctx.user_id])
    if not first or not first["t"]:
        return None
    week = (ctx.now_utc - parse_utc(first["t"])) // (7 * 1440)
    if week < learn.proposal_from_week or (week - learn.proposal_from_week) % learn.proposal_every_weeks:
        return None
    refused = set(proposals.get("refused", [])) | set(proposals.get("accepted", []))
    best, _ = propose(found, extras, rules, refused, learn.proposal_min_gain, seed=int(week))
    return best.name if best else None


def forbidden_work(ctx: Ctx, walls: dict[str, Any]) -> str | None:
    """A "never" rule (a forbid time preference) that recorded work fell inside, asked about once (§21.6)."""
    tz = ctx.tz
    for rule in ctx.settings["rules"]:
        if rule.type != "time_preference" or rule.params.get("price") != "forbid" or rule.name in walls["decided"]:
            continue
        days = rule.params.get("days")
        lo, hi = rule.params.get("start", "00:00"), rule.params.get("end", "23:59")
        for r in rows(
            ctx.conn,
            "SELECT start_utc, end_utc FROM progress WHERE user_id = ? AND source IN "
            "('timer', 'review', 'retro') AND start_utc IS NOT NULL",
            [ctx.user_id],
        ):
            start = to_local(parse_utc(r["start_utc"]), tz)
            day_name = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[start.weekday()]
            if (days is None or day_name in days) and lo <= start.strftime("%H:%M") < hi:
                return rule.name
    return None


def state(ctx: Ctx, found: list[Comparison], rules: tuple[str, ...]) -> dict[str, Any] | None:
    """With state inference on: this week's units and whether the gate is open (§21.3)."""
    if ctx.settings["learn"].state_inference != "on":
        return None
    weeks: dict[int, list[int]] = defaultdict(list)
    found_rows = rows(
        ctx.conn,
        "SELECT asked_utc FROM comparisons WHERE user_id = ? AND answer IN ('a', 'b') ORDER BY id",
        [ctx.user_id],
    )
    for n, r in enumerate(found_rows):
        weeks[parse_utc(r["asked_utc"]) // (7 * 1440)].append(n)
    model = StateModel(rules)
    for week_no in sorted(weeks):
        picked = [found[n] for n in weeks[week_no]]
        x, weight = design(picked, rules)
        week = Week(x, weight, 0, 0, checkin_in(ctx, week_no), None)
        model.score(week, model.predict_h(week.checkin, None), model.theta)
        model.add(week, iters=60)
    h = model.h[-1] if model.h else np.zeros(4)
    return {
        "h": [float(v) for v in h],
        "on": model.units_on(ctx.settings["learn"].state_gate_nats),
        "gain": round(model.gain, 2),
        "mood": model.mood(h),
    }


def checkin_in(ctx: Ctx, week_no: int) -> str | None:
    # week_no counts weeks from 1970, as `state` numbers them (12 Nov: counted from year 1, it looked in the year 57)
    epoch = date(1970, 1, 1)
    lo, hi = epoch + timedelta(days=week_no * 7), epoch + timedelta(days=week_no * 7 + 7)
    found = one(
        ctx.conn,
        "SELECT state FROM checkins WHERE user_id = ? AND date >= ? AND date < ? ORDER BY date DESC",
        [ctx.user_id, lo.isoformat(), hi.isoformat()],
    )
    return found["state"] if found else None
