"""Answers computed from the current state and plan: now, fits, why-not, triage, weight previews (DESIGN §14, §16)."""

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from friday.api.types import BlockOut, ChangeOut
from friday.core.calendars import fallback_level, rating_key
from friday.core.items import Item
from friday.core.time import ampm, format_local, format_utc, parse_utc, to_local
from friday.engine.compile import compile_problem
from friday.engine.executor import ExecutorInput, Now, NowSettings, now, safe_items
from friday.engine.explain import WhyNot, why_not
from friday.engine.problem import Plan, Problem
from friday.planner.assemble import AssembledPlan, assemble
from friday.planner.build import BuildInput, build_problem, key_of
from friday.planner.inputs import executor_input, now_settings
from friday.planner.learning import learnable
from friday.planner.prepare import build_input, day_of
from friday.planner.service import quick_late, with_pins_preferred
from friday.planner.snapshot import Snapshot, picked
from friday.planner.solve import solve

MAX_TRIAGE_ACTIONS = 8
MAX_SKIPS = 4  # events offered to skip, least important first (COMBINED.md 56)


@dataclass
class Current:
    inp: BuildInput
    problem: Problem
    plan: Plan  # the saved plan's future blocks, as slots of this problem
    executor: ExecutorInput


def current(snapshot: Snapshot) -> Current:
    inp = build_input(snapshot)
    problem = build_problem(inp)
    grid = problem.grid
    plan: dict[str, list[int]] = {k: [] for k in problem.items}
    for block in snapshot.plan_blocks:
        key = key_of(block.item_id)
        if key in plan:
            plan[key].extend(grid.slots_in(block.start_utc, block.end_utc))
    return Current(inp, problem, {k: tuple(sorted(set(v))) for k, v in plan.items()}, executor_input(inp, problem))


def now_view(snapshot: Snapshot) -> tuple[Current, Now]:
    state = current(snapshot)
    timer_key = key_of(snapshot.timer[0]) if snapshot.timer else None
    return state, now(state.problem, state.plan, state.executor, now_settings(snapshot.settings), timer_key)


def fits_view(snapshot: Snapshot, minutes: int | None) -> tuple[Current, list]:
    state, shown = now_view(snapshot)
    gap = minutes if minutes is not None else shown.gap_minutes
    settings: NowSettings = now_settings(snapshot.settings)
    found = [w for w in safe_items(state.problem, state.plan, state.executor, gap) if w.chunk_minutes <= gap]
    return state, found[: settings.swap_count * 3]


def why_not_view(
    snapshot: Snapshot, item_id: int, start_utc: int, new_start_utc: int | None
) -> tuple[WhyNot, int | None]:
    """The relocation answer, and where the block was tried, in UTC minutes."""
    state = current(snapshot)
    c = compile_problem(state.problem)
    owner = c.owner_from_plan(state.plan)
    grid = state.problem.grid
    slot = grid.slot_at(start_utc)
    if slot < 0 or owner[slot] < 0 or c.keys[owner[slot]] != key_of(item_id):
        raise ValueError(f"T{item_id} has no block at that time in the current plan")
    target = grid.slot_at(new_start_utc) if new_start_utc is not None else None
    if target is not None and target < 0:
        raise ValueError("that start is outside the planning horizon")
    answer = why_not(c, owner, slot, target)
    return answer, int(grid.start[answer.start]) if answer.start is not None else None


def preview_weights(
    snapshot: Snapshot, weights: dict[str, float], off: list[str], rules_instead: tuple | None = None
) -> AssembledPlan:
    """A warm run with changed weights, rules switched off or another rules list; nothing is saved."""
    rules = [
        r.model_copy(update={"weight": weights.get(r.name, r.weight)})
        for r in (snapshot.settings["rules"] if rules_instead is None else rules_instead)
        if r.name not in off
    ]
    changed = dataclasses.replace(snapshot, settings=snapshot.settings | {"rules": tuple(rules)})
    return assemble(changed, solve(changed, warm=True))


def other_ways(snapshot: Snapshot, n: int = 2, tries: int = 6) -> list[tuple[dict[str, float], int, AssembledPlan]]:
    """Other ways to plan the same work (personal's options, COMBINED.md 25): each a plan made from scratch with the
    learnable rules weighed differently (×e^N(0, 1)) and another search seed, kept when its blocks differ from the plan
    you have and from the ways already found. Picking one plans with those weights afresh, so it comes out the same."""
    rules = learnable(snapshot.settings)
    seen = [{(b.item_id, b.start_utc, b.end_utc) for b in snapshot.plan_blocks}]
    out = []
    for seed in range(1, tries + 1):
        rng = np.random.default_rng(seed)
        factors = {r: round(float(np.exp(rng.normal(0, 1.0))), 3) for r in rules}
        changed = dataclasses.replace(snapshot, settings=picked(snapshot.settings, factors, seed))
        plan = assemble(changed, solve(changed, warm=False))
        blocks = {(b.item_id, b.start_utc, b.end_utc) for b in plan.blocks}
        if any(blocks == other for other in seen):
            continue
        seen.append(blocks)
        out.append((factors, seed, plan))
        if len(out) == n:
            break
    return out


CLASH_FACTOR = 20  # how much more the rule is weighed when asking what keeping it would cost
CLASH_SHARE = 0.25  # a rival counts when it loses at least this share of what the rule gains (less is search noise)


@dataclass
class Clash:
    other: str  # the rule that gives way when this one is kept
    days: list[str]  # the days (ISO dates) where they pull against each other


def rule_clash(snapshot: Snapshot, name: str) -> Clash | None:
    """What a rule the plan bends is up against ("Which should win?", COMBINED.md 66): plan afresh with it weighed far
    more, and see, on the days it is then kept better, which other rule is bent more. Both plans are made from
    scratch with the same seed (a warm start stays where it is), so the weight is what differs. None when keeping it
    costs no other rule: deadlines bend it, or nothing would."""

    def by_day(settings: dict[str, Any]) -> dict[str, dict[str, int]]:
        changed = dataclasses.replace(snapshot, settings=settings)
        totals = assemble(changed, solve(changed, warm=False)).report.get("rule_totals_by_day", {})
        return {d: t for d, t in totals.items() if d != "other"}

    before = by_day(snapshot.settings)
    if not any(t.get(name, 0) > 0 for t in before.values()):
        return None
    after = by_day(picked(snapshot.settings, {name: CLASH_FACTOR}, 0))
    gained = [d for d, t in before.items() if t.get(name, 0) > after.get(d, {}).get(name, 0) / CLASH_FACTOR]
    gain = sum(before[d].get(name, 0) - after.get(d, {}).get(name, 0) / CLASH_FACTOR for d in gained)
    lost: dict[str, float] = {}
    for d in gained:
        for rule in learnable(snapshot.settings):
            if rule != name:
                lost[rule] = lost.get(rule, 0) + after.get(d, {}).get(rule, 0) - before[d].get(rule, 0)
    rival, cost = max(lost.items(), key=lambda kv: kv[1], default=("", 0.0))
    if cost <= 0 or cost < CLASH_SHARE * gain:
        return None
    return Clash(rival, sorted(d for d in gained if after.get(d, {}).get(rival, 0) > before[d].get(rival, 0)))


Step = tuple[str, dict[str, Any]]  # a registry command and its input; times as UTC minutes under `*_utc` keys


@dataclass
class TriageOption:
    action: str
    steps: list[Step]  # applying the option runs these commands in order
    hours_saved: float
    side_effects: list[str]
    skip_title: str | None = None  # an event offered to skip: "I'm going" stops offering it


def triage(
    snapshot: Snapshot, ratings: Mapping[str, Mapping[str, str]] | None = None, going: frozenset[str] = frozenset()
) -> tuple[dict[int, float], list[TriageOption]]:
    """Ways to make late hard work less late, each tested with a quick replan (§16): m16's, and events you could skip
    (personal's, COMBINED.md 56), rated by how much they need attending; `going` are titles you said you go to."""
    inp = build_input(snapshot)
    _, late = quick_late(inp, with_fallback=False)
    if not late:
        return {}, []
    before = sum(late.values())
    options = []
    candidates = candidate_actions(snapshot, inp, late)[:MAX_TRIAGE_ACTIONS]
    candidates += skip_actions(snapshot, late, ratings or {}, going)
    for action, steps, change, effects, *rest in candidates:
        _, after = quick_late(change(inp), with_fallback=False)
        saved = round(before - sum(after.values()), 2)
        if saved > 0 and steps:
            options.append(TriageOption(action, steps, saved, effects, rest[0] if rest else None))
    return late, sorted(options, key=lambda o: -o.hours_saved)


def skip_actions(
    snapshot: Snapshot, late: dict[int, float], ratings: Mapping[str, Mapping[str, str]], going: frozenset[str]
) -> list[tuple]:
    """Events before the latest late due that aren't required, least important first, then the longest: skipping one
    keeps it on your calendar and only stops it blocking time."""
    by_id = {i.id: i for i in snapshot.items}
    until = (
        max(parse_utc(by_id[k].due_utc) for k in late if by_id[k].due_utc)
        if any(by_id[k].due_utc for k in late)
        else None
    )
    if until is None:
        return []
    rank = {"optional": 0, "likely": 1}
    found = []
    for event in snapshot.items:
        if event.when != "fixed" or not event.blocks_time or event.status != "todo" or not event.start_utc:
            continue
        start, end = parse_utc(event.start_utc), parse_utc(event.end_utc or event.start_utc)
        if not snapshot.now_utc <= start < until or rating_key(event.title) in going:
            continue
        level = (ratings.get(rating_key(event.title)) or {}).get("level") or fallback_level(event.title)
        if level in rank:
            found.append((rank[level], -(end - start), start, event))
    out = []
    for _, _, start, event in sorted(found, key=lambda f: f[:3])[:MAX_SKIPS]:
        reason = (ratings.get(rating_key(event.title)) or {}).get("reason")
        local = to_local(start, snapshot.settings["time"].timezone)
        when = f"{local:%a} {ampm(local)}"
        out.append(
            (
                f"Skip {event.title} ({when})",
                [("edit", {"id": event.id, "blocks_time": False})],
                without_blocking(event.id or 0),
                ["It stays on your calendar; Friday plans through it", *([reason] if reason else [])],
                event.title,
            )
        )
    return out


def without_blocking(event_id: int) -> "Change":
    return lambda inp: dataclasses.replace(
        inp, items=[dataclasses.replace(i, blocks_time=False) if i.id == event_id else i for i in inp.items]
    )


Change = Callable[[BuildInput], BuildInput]


def candidate_actions(snapshot: Snapshot, inp: BuildInput, late: dict[int, float]) -> list[tuple]:
    by_id = {i.id: i for i in snapshot.items}
    worst = max(late, key=lambda k: late[k])
    item = by_id[worst]
    due = parse_utc(item.due_utc) if item.due_utc else snapshot.now_utc
    out: list[tuple] = []
    for other in competitors(snapshot, item, due)[:5]:
        out.append(
            (
                f"Drop {other.title}",
                [("drop", {"id": other.id})],
                without_item(other.id or 0),
                [f"{other.title} won't be done"],
            )
        )
    for days in (1, 3):
        later = due + days * 1440
        out.append(
            (
                f"Move {item.title}'s due {days} day{'s' * (days > 1)} later",
                [("edit", {"id": worst, "due_utc": later})],
                with_due(worst, format_utc(later)),
                [],
            )
        )
    nights = nights_before(snapshot, due)
    out.append(
        (
            "Use the sleep margin on the nights before it",
            [("day_override", {"date": d.isoformat(), "margin_min": 0}) for d in nights],
            without_margin(nights),
            ["Later nights"],
        )
    )
    locks = [p for p in snapshot.pins if p.kind == "locked"]
    if locks:
        steps = [
            ("pin", {"id": p.item_id, "start_utc": p.start_utc, "end_utc": p.end_utc, "kind": "preferred"})
            for p in locks
        ]
        out.append(("Make locked blocks preferred", steps, with_pins_preferred(None), ["Pinned blocks may move"]))
    elastic = [i for i in competitors(snapshot, item, due) if i.amount == "elastic" and i.min_units is not None]
    if elastic:
        steps = [("edit", {"id": i.id, "ideal_min": i.min_units * 15, "max_min": i.min_units * 15}) for i in elastic]
        out.append(
            (
                "Shorten meals and routines to their minimum",
                steps,
                at_minimum({i.id for i in elastic}),
                ["Shorter meals"],
            )
        )
    return out


def competitors(snapshot: Snapshot, late_item: Item, due: int) -> list[Item]:
    """Lower-importance flexible work that could use the same time before the due."""
    found = [
        i
        for i in snapshot.items
        if i.status == "todo"
        and i.when != "fixed"
        and i.id != late_item.id
        and i.importance < late_item.importance
        and (i.release_utc is None or parse_utc(i.release_utc) < due)
    ]
    return sorted(found, key=lambda i: (i.importance, i.id or 0))


def without_item(item_id: int) -> Change:
    return lambda inp: dataclasses.replace(inp, items=[i for i in inp.items if i.id != item_id])


def with_due(item_id: int, due: str) -> Change:
    def change(inp: BuildInput) -> BuildInput:
        return dataclasses.replace(
            inp, items=[dataclasses.replace(i, due_utc=due) if i.id == item_id else i for i in inp.items]
        )

    return change


def nights_before(snapshot: Snapshot, due: int) -> list[date]:
    first, last = day_of(snapshot, snapshot.now_utc), day_of(snapshot, due)
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def without_margin(days: list[date]) -> Change:
    def change(inp: BuildInput) -> BuildInput:
        overrides = dict(inp.day_overrides) | {d: {**inp.day_overrides.get(d, {}), "margin_min": 0} for d in days}
        return dataclasses.replace(inp, day_overrides=overrides)

    return change


def at_minimum(item_ids: set[int | None]) -> Change:
    def change(inp: BuildInput) -> BuildInput:
        return dataclasses.replace(
            inp,
            items=[
                dataclasses.replace(i, ideal_units=i.min_units, max_units=i.min_units) if i.id in item_ids else i
                for i in inp.items
            ],
        )

    return change


def change_list(report: dict[str, Any], before: dict[str, int], tz: str, title: Callable[[int], str]) -> ChangeOut:
    """A plan report's change list in local time, with titles."""
    changes = report.get("changes", {})

    def local(stored: str) -> str:
        return format_local(to_local(parse_utc(stored), tz))

    def blocks(entries: list[dict[str, Any]], side: str) -> list[BlockOut]:
        return [
            BlockOut(
                key=f"T{e['item_id']}@{local(a)}",
                item_id=e["item_id"],
                title=title(e["item_id"]),
                start=local(a),
                end=local(b),
            )
            for e in entries
            for a, b in e[side]
        ]

    moved = [
        {
            "item_id": e["item_id"],
            "title": title(e["item_id"]),
            "before": [[local(a), local(b)] for a, b in e["before"]],
            "after": [[local(a), local(b)] for a, b in e["after"]],
        }
        for e in changes.get("moved", [])
    ]
    return ChangeOut(
        added=blocks(changes.get("added", []), "after"),
        moved=moved,
        removed=blocks(changes.get("removed", []), "before"),
        inputs=changes.get("inputs", []),
        rule_totals_before=before,
        rule_totals_after=report.get("rule_totals", {}),
        notices=report.get("notices", []) + report.get("pace_notices", []),
        late_hours={title(int(k)): v for k, v in report.get("late_hours", {}).items()},
    )
