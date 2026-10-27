"""Learning, wired (DESIGN §21): the commands that answer and steer what Friday learns (compare_answer,
proposal_answer, checkin, learn_apply, learn_reject, learn_reset) and the queries questions and learning. The
fitting is in `refit.py`. Everything learned is a versioned row of `learned_profile`; plans record the version.
"""

import json
from typing import Any

from friday.api.commands import (
    Changed,
    CheckinInput,
    CompareAnswerInput,
    LearnOrderInput,
    ProposalAnswerInput,
    ResetInput,
    VersionInput,
)
from friday.api.types import Empty
from friday.api.views import LearningOut, OrderOut, Question, QuestionsOut
from friday.commands.estimates import in_use
from friday.commands.learned import MIN_DONE
from friday.commands.refit import EMPTY_PROFILE, answered, profile
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import format_utc, parse_utc
from friday.estimate.durations import LEARNED_SOURCES
from friday.learn.order import MIN_CHOICES, Choice, reordered, suggest
from friday.learn.proposals import TEMPLATES
from friday.planner.learning import learnable
from friday.planner.store import kv_get


@query("questions")
def questions(ctx: Ctx, inp: Empty) -> QuestionsOut:
    """Today's unanswered comparisons, a pending rule proposal or wall question, and whether to ask for a check-in."""
    since = format_utc(ctx.now_utc - 24 * 60)
    found = rows(
        ctx.conn,
        "SELECT * FROM comparisons WHERE user_id = ? AND source = 'question' AND answer IS NULL "
        "AND asked_utc >= ? ORDER BY id LIMIT ?",
        [ctx.user_id, since, ctx.settings["learn"].questions_per_day],
    )
    comparisons = []
    for r in found:
        a, b = json.loads(r["plan_a"]), json.loads(r["plan_b"])
        day = a["day"]
        comparisons.append(Question(id=r["id"], day=day, a=a["blocks"], b=b["blocks"], fixed=fixed_on(ctx, day)))
    last = profile(ctx.conn, ctx.user_id) or {}
    pending = (last.get("proposals") or {}).get("pending")
    template = next((t for t in TEMPLATES if t.name == pending), None)
    wall = (last.get("wall_decisions") or {}).get("pending")
    checked = one(
        ctx.conn, "SELECT 1 FROM checkins WHERE user_id = ? AND date = ?", [ctx.user_id, ctx.today.isoformat()]
    )
    return QuestionsOut(
        comparisons=comparisons,
        proposal={"name": template.name, "sentence": f"{template.sentence()} Add that as a rule?"}
        if template
        else None,
        wall={
            "rule": wall,
            "sentence": f"You worked during '{wall}'. Keep it as a hard rule? (No makes it a strong preference.)",
        }
        if wall
        else None,
        checkin=ctx.settings["learn"].state_inference == "on" and checked is None,
    )


def fixed_on(ctx: Ctx, day: str) -> list[dict[str, Any]]:
    """The day's classes and events, shown in both versions: a day is judged around what can't move."""
    lo = ctx.utc(f"{day}T00:00")
    hi = format_utc(parse_utc(lo) + 24 * 60)
    found = rows(
        ctx.conn,
        "SELECT title, start_utc, end_utc FROM items WHERE user_id = ? AND when_kind = 'fixed' AND blocks_time = 1 "
        "AND status = 'todo' AND start_utc >= ? AND start_utc < ? ORDER BY start_utc",
        [ctx.user_id, lo, hi],
    )
    return [{"title": r["title"], "start": ctx.local(r["start_utc"]), "end": ctx.local(r["end_utc"])} for r in found]


@command("compare_answer")
def compare_answer(ctx: Ctx, inp: CompareAnswerInput) -> Changed:
    """Answer a comparison: which version of the day looks better (or skip)."""
    found = one(ctx.conn, "SELECT * FROM comparisons WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None:
        raise FieldError("id", f"no comparison {inp.id}")
    ctx.db.update("comparisons", {"id": inp.id}, {"answer": inp.answer, "answered_utc": ctx.now_text})
    return Changed(message="Thanks" if inp.answer != "skip" else "Skipped")


@command("proposal_answer", affects_plan=True)
def proposal_answer(ctx: Ctx, inp: ProposalAnswerInput) -> Changed:
    """Yes or no to a proposed rule, or to keeping a "never" rule hard."""
    last = profile(ctx.conn, ctx.user_id)
    if last is None:
        raise FieldError("name", "nothing was proposed")
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    if inp.kind == "rule":
        template = next((t for t in TEMPLATES if t.name == inp.name), None)
        if template is None:
            raise FieldError("name", f"no proposal {inp.name}")
        proposals = last["proposals"] | {"pending": None}
        proposals["accepted" if inp.yes else "refused"] = [
            *proposals.get("accepted" if inp.yes else "refused", []),
            inp.name,
        ]
        if inp.yes:
            write_setting(ctx, "rules", [*rules, template.rule()])
        ctx.db.update(
            "learned_profile",
            {"user_id": ctx.user_id, "version": last["version"]},
            {"proposals": json.dumps(proposals)},
        )
        return Changed(message="Rule added" if inp.yes else "Won't propose that again")
    walls = last["wall_decisions"] | {"pending": None}
    walls["decided"] = walls.get("decided", {}) | {inp.name: "keep" if inp.yes else "soften"}
    if not inp.yes:  # a strong preference instead of a wall: 10 points an hour
        rules = [r | {"params": r["params"] | {"price": 10.0}} if r["name"] == inp.name else r for r in rules]
        write_setting(ctx, "rules", rules)
    ctx.db.update(
        "learned_profile", {"user_id": ctx.user_id, "version": last["version"]}, {"wall_decisions": json.dumps(walls)}
    )
    return Changed(message="Kept as a hard rule" if inp.yes else "Now a strong preference")


@command("checkin")
def checkin(ctx: Ctx, inp: CheckinInput) -> Changed:
    """Today's state, one tap (used only while state inference is on)."""
    ctx.db.upsert("checkins", {"user_id": ctx.user_id, "date": ctx.today.isoformat()}, {"state": inp.state})
    return Changed(message=f"Noted: {inp.state}")


@command("learn_apply", affects_plan=True)
def learn_apply(ctx: Ctx, inp: VersionInput) -> Changed:
    """Approve a suggested profile: its weights plan from now on."""
    return set_status(ctx, inp.version, "suggested", "active", "Applied what Friday learned")


@command("learn_reject")
def learn_reject(ctx: Ctx, inp: VersionInput) -> Changed:
    """Turn down a suggested profile."""
    return set_status(ctx, inp.version, "suggested", "rejected", "Kept the weights as they were")


def set_status(ctx: Ctx, version: int, was: str, now: str, message: str) -> Changed:
    found = one(
        ctx.conn, "SELECT status FROM learned_profile WHERE user_id = ? AND version = ?", [ctx.user_id, version]
    )
    if found is None or found["status"] != was:
        raise FieldError("version", f"no {was} profile version {version}")
    ctx.db.update("learned_profile", {"user_id": ctx.user_id, "version": version}, {"status": now})
    return Changed(message=message)


@command("learn_reset", affects_plan=True)
def learn_reset(ctx: Ctx, inp: ResetInput) -> Changed:
    """Start a module over: the weights back to as set, the state model, or proposals refused and accepted."""
    last = profile(ctx.conn, ctx.user_id) or {"version": 0, "theta": None, "state": None, "evidence": None} | {
        "proposals": EMPTY_PROFILE["proposals"],
        "wall_decisions": EMPTY_PROFILE["walls"],
    }
    reset = {"weights", "state", "proposals", "durations", "energy"} if inp.module == "all" else {inp.module}
    for module in reset & {"durations", "energy"}:
        found = one(ctx.conn, "SELECT 1 FROM kv WHERE user_id = ? AND key = ?", [ctx.user_id, f"learned_{module}"])
        if found:
            ctx.db.delete("kv", {"user_id": ctx.user_id, "key": f"learned_{module}"})
    theta = dict.fromkeys(learnable(ctx.settings), 1.0) if "weights" in reset else last["theta"]
    ctx.db.insert(
        "learned_profile",
        {
            "version": last["version"] + 1,
            "created_utc": ctx.now_text,
            "theta": json.dumps(theta),
            "answer_noise": 0.05,
            "state": None if "state" in reset else json.dumps(last["state"]),
            "proposals": json.dumps(EMPTY_PROFILE["proposals"] if "proposals" in reset else last["proposals"]),
            "wall_decisions": json.dumps(last["wall_decisions"]),
            "evidence": json.dumps(last["evidence"]),
            "status": "active",
        },
    )
    return Changed(message=f"Reset {inp.module}")


@query("learning")
def learning(ctx: Ctx, inp: Empty) -> LearningOut:
    """What Friday has learned: the multipliers in use, a suggestion waiting for you, the evidence and a digest."""
    active, last = profile(ctx.conn, ctx.user_id, "active"), profile(ctx.conn, ctx.user_id)
    found, _ = answered(ctx.conn, ctx.user_id, ctx.settings["learn"].drag_weight)
    suggested = last if last and last["status"] == "suggested" else None
    changes = (suggested or {}).get("evidence", {}) or {}
    digest = [
        f"{'Raise' if c['to'] > c['from'] else 'Lower'} {c['rule'].replace('_', ' ')} ×{c['to'] / c['from']:.1f}"
        for c in changes.get("changes", [])
        if c["from"]
    ]
    return LearningOut(
        mode=ctx.settings["learn"].weights,
        version=active["version"] if active else 0,
        multipliers=(active or {}).get("theta") or {},
        suggested={"version": suggested["version"], "changes": changes.get("changes", [])} if suggested else None,
        comparisons=sum(c.weight == 1.0 for c in found),
        drags=sum(c.weight != 1.0 for c in found),
        answer_noise=float((last or {}).get("answer_noise") or 0.05),
        state=(last or {}).get("state"),
        proposals=(last or {}).get("proposals") or EMPTY_PROFILE["proposals"],
        digest=digest + module_digest(ctx),
        durations=durations_view(ctx),
        energy=energy_view(ctx),
        order=order_view(ctx),
        progress=progress(ctx),
    )


def progress(ctx: Ctx) -> dict[str, dict[str, int]]:
    """How far each learner has got: the finished things you timed (lengths are learned from `MIN_DONE`), and the times
    you started one kind of work before another kind planned first (an order is offered after `MIN_CHOICES`)."""
    since = format_utc(ctx.now_utc - ctx.settings["estimate"].window_days * 1440)
    timed = one(
        ctx.conn,
        f"SELECT COUNT(*) AS n FROM completions WHERE user_id = ? AND completed_utc >= ? AND actual_source IN "
        f"({', '.join('?' * len(LEARNED_SOURCES))})",
        [ctx.user_id, since, *LEARNED_SOURCES],
    )
    kept = kv_get(ctx.conn, "order_choices", [], ctx.user_id) or []
    across = sum(1 for c in kept if c.get("chose_kind") and c.get("over_kind") and c["chose_kind"] != c["over_kind"])
    return {
        "lengths": {"have": timed["n"] if timed else 0, "need": MIN_DONE},
        "order": {"have": across, "need": MIN_CHOICES},
    }


def order_view(ctx: Ctx) -> OrderOut | None:
    """A kind you keep starting ahead of another that was planned first, to plan first from now (`learn/order.py`)."""
    kept = kv_get(ctx.conn, "order_choices", [], ctx.user_id) or []
    choices = [Choice(c["chose_kind"], c["over_kind"]) for c in kept if c.get("chose_kind") and c.get("over_kind")]
    refused = [tuple(r) for r in kv_get(ctx.conn, "order_refused", [], ctx.user_id) or []]
    found = suggest(choices, list(ctx.settings["kind_order"]), refused)  # type: ignore[arg-type]
    return OrderOut(first=found.first, then=found.then, chose=found.chose, of=found.of) if found else None


@command("learn_order", affects_plan=True)
def learn_order(ctx: Ctx, inp: LearnOrderInput) -> Changed:
    """Plan one kind ahead of another from now, as you've been doing them (`kind_order`), or don't ask again."""
    if not inp.use:
        refused = [*(kv_get(ctx.conn, "order_refused", [], ctx.user_id) or []), [inp.first, inp.then]]
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "order_refused"}, {"value": json.dumps(refused)})
        return Changed(message=f"Friday won't suggest {inp.first} before {inp.then} again")
    write_setting(ctx, "kind_order", reordered(list(ctx.settings["kind_order"]), inp.first, inp.then))
    return Changed(message=f"{inp.first} is planned ahead of {inp.then} from now")


DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def durations_view(ctx: Ctx) -> dict[str, Any] | None:
    kept = kv_get(ctx.conn, "learned_durations", None, ctx.user_id)
    if not kept:
        return None
    return {
        "in_use": in_use(ctx.settings, kept, "durations"),
        "n": kept["model"]["n"],
        "better": kept.get("better"),
        "error": kept.get("error"),
        "error_before": kept.get("error_before"),
    }


def energy_view(ctx: Ctx) -> dict[str, Any] | None:
    kept = kv_get(ctx.conn, "learned_energy", None, ctx.user_id)
    if not kept:
        return None
    cells = [
        (price, day, cell) for day, row in enumerate(kept["prices"]) for cell, price in enumerate(row) if price > 0
    ]
    worst = [
        {"day": DAYS[d], "time": f"{c // 2:02d}:{30 * (c % 2):02d}", "price": p} for p, d, c in sorted(cells)[::-1][:5]
    ]
    return {"in_use": in_use(ctx.settings, kept, "energy"), "observations": kept["observations"], "worst": worst}


def module_digest(ctx: Ctx) -> list[str]:
    """Plain lines for the weekly review about what the two modules would change."""
    out = []
    durations, energy = durations_view(ctx), energy_view(ctx)
    if durations and durations["better"] and not durations["in_use"]:
        out.append(
            f"Learned lengths are typically {round(100 * durations['error'])}% off, against "
            f"{round(100 * durations['error_before'])}% now. Use them?"
        )
    if energy and energy["worst"] and not energy["in_use"]:
        when = ", ".join(f"{w['day']} {w['time']}" for w in energy["worst"][:3])
        out.append(f"Planned work often slips around {when}. Plan less deep work there?")
    return out
