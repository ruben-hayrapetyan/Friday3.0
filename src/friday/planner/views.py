"""Answers computed from the current state and plan: now, fits, why-not, triage, weight previews (DESIGN §14, §16)."""

import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from friday.api.types import BlockOut, ChangeOut
from friday.core.calendars import fallback_level, rating_key
from friday.core.items import Item
from friday.core.settings import minutes_of
from friday.core.time import clock_time, format_local, format_utc, parse_utc, planning_date, to_local
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
from friday.planner.snapshot import WIN, Snapshot, picked
from friday.planner.solve import solve

MAX_TRIAGE_ACTIONS = 8
MAX_SKIPS = 4  # events offered to skip, least important first


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


WAY_TRIES = 6  # seeds tried for two ways unlike your plan and each other


Way = tuple[dict[str, float], int, AssembledPlan]  # the rules' factors, the seed, the plan


def other_ways(snapshot: Snapshot, n: int = 2, tries: int = WAY_TRIES) -> list[Way]:
    """Other ways to plan the same work (personal's options): each a plan made from scratch with the
    learnable rules weighed differently (×e^N(0, 1)) and another search seed, kept when its blocks differ from the plan
    you have and from the ways already found. Picking one plans with those weights afresh, so it comes out the same."""
    seen = {signature(snapshot.plan_blocks)}
    out = []
    for seed in range(1, tries + 1):
        factors, plan = other_way(snapshot, seed)
        if signature(plan.blocks) in seen:
            continue
        seen.add(signature(plan.blocks))
        out.append((factors, seed, plan))
        if len(out) == n:
            break
    return out


def other_way(snapshot: Snapshot, seed: int) -> tuple[dict[str, float], AssembledPlan]:
    """The way made with one seed: about half a minute on a full term, so the app asks for one at a time and shows
    each as it comes (6 Nov: "it just says the same static thing for over 20 seconds")."""
    rng = np.random.default_rng(seed)
    factors = {r: round(float(np.exp(rng.normal(0, 1.0))), 3) for r in learnable(snapshot.settings)}
    # Made afresh on purpose (`cold_once`): the plan you have doesn't stand against it, or every way were yours.
    changed = dataclasses.replace(snapshot, settings=picked(snapshot.settings, factors, seed), cold_once=True)
    return factors, assemble(changed, solve(changed, warm=False))


def signature(blocks: Iterable[Any]) -> str:
    """Which blocks a plan has, as a short text: two ways with the same one are the same way."""
    found = sorted((b.item_id, b.start_utc, b.end_utc) for b in blocks)
    return hashlib.sha1(repr(found).encode()).hexdigest()[:16]


CLASH_FACTOR = 20  # how much more the rule is weighed when asking what keeping it would cost
CLASH_SHARE = 0.25  # a rival counts when it loses at least this share of what the rule gains (less is search noise)
# 15 Nov (the user: "if clashes are problematic, ask in inbox about them, else, add the because"): a clash is asked
# when your answer would change the plan: the rival alone pays at least all the rule gains (less, and other rules pay
# the rest), yet less than WIN² times it (your answer weighs the winner ×WIN and the other ÷WIN, so a dearer trade
# stays as it is whatever you say); or when keeping the rule makes work late. Else Friday says why, and doesn't ask.
ASK_SHARE = 1.0
ASK_MOST = WIN * WIN
ASK_LATE_HOURS = 0.25  # keeping the rule makes work late: a quarter of an hour more past its due, or more


@dataclass
class Clash:
    other: str  # the rule that gives way when this one is kept
    days: list[str]  # the days (ISO dates) where they pull against each other
    because: str = ""  # "Finishing Lab 9 a day sooner splits it into 3 sittings instead of 1", from the two plans
    ask: bool = False  # a clash your answer decides (`ASK_SHARE`, `ASK_MOST`, `ASK_LATE_HOURS`): asked in the Inbox


def rule_clash(snapshot: Snapshot, name: str) -> Clash | None:
    """What a rule the plan bends is up against ("Which should win?"): plan afresh with it weighed far
    more, and see, on the days it is then kept better, which other rule is bent more. Both plans are made from
    scratch with the same seed (a warm start stays where it is), so the weight is what differs. None when keeping it
    costs no other rule: deadlines bend it, or nothing would."""
    return rule_clashes(snapshot, [name])[name]


def rule_clashes(snapshot: Snapshot, names: Iterable[str]) -> dict[str, Clash | None]:
    """`rule_clash` for each rule, your plan made once for them all."""

    def made(settings: dict[str, Any]) -> AssembledPlan:
        changed = dataclasses.replace(snapshot, settings=settings, cold_once=True)  # both from scratch, as said
        return assemble(changed, solve(changed, warm=False))

    before = made(snapshot.settings)
    out: dict[str, Clash | None] = {}
    for name in names:
        if not any(t.get(name, 0) > 0 for t in by_day(before).values()):
            out[name] = None
            continue
        out[name] = clash_of(snapshot, name, before, made(picked(snapshot.settings, {name: CLASH_FACTOR}, 0)))
    return out


def by_day(plan: AssembledPlan) -> dict[str, dict[str, int]]:
    return {d: t for d, t in plan.report.get("rule_totals_by_day", {}).items() if d != "other"}


def clash_of(snapshot: Snapshot, name: str, before_plan: AssembledPlan, after_plan: AssembledPlan) -> Clash | None:
    """The rule that loses most when this one is kept, across the plan: work kept to one rule on one day often goes
    to another day, where the other rule pays (15 Nov: finishing Lab 9 sooner split it on Monday, not on its due)."""
    before, after = by_day(before_plan), by_day(after_plan)
    days = sorted(set(before) | set(after))
    gained = [d for d in before if before[d].get(name, 0) > after.get(d, {}).get(name, 0) / CLASH_FACTOR]
    gain = sum(before[d].get(name, 0) - after.get(d, {}).get(name, 0) / CLASH_FACTOR for d in gained)
    lost: dict[str, float] = {}
    for rule in learnable(snapshot.settings):
        if rule != name:
            lost[rule] = sum(after.get(d, {}).get(rule, 0) - before.get(d, {}).get(rule, 0) for d in days)
    rival, cost = max(lost.items(), key=lambda kv: kv[1], default=("", 0.0))
    if cost <= 0 or cost < CLASH_SHARE * gain:
        return None
    where = sorted(d for d in days if after.get(d, {}).get(rival, 0) > before.get(d, {}).get(rival, 0))
    late = late_total(after_plan) - late_total(before_plan)
    ask = ASK_SHARE * gain <= cost < ASK_MOST * gain or late >= ASK_LATE_HOURS
    return Clash(rival, where, because(snapshot, name, rival, before_plan, after_plan), ask)


def late_total(plan: AssembledPlan) -> float:
    return sum(plan.report.get("late_hours", {}).values())


def because(snapshot: Snapshot, name: str, rival: str, before: AssembledPlan, after: AssembledPlan) -> str:
    """Why keeping `name` costs `rival`, from the two plans: the work whose cost under the rival went up most, and
    what happened to it ("Finishing Lab 9 a day sooner splits it into 3 sittings instead of 1")."""
    rules = {r.name: r for r in snapshot.settings["rules"]}
    paid: dict[int, int] = {}
    for sign, plan in ((-1, before), (1, after)):
        for b in plan.blocks:
            paid[b.item_id] = paid.get(b.item_id, 0) + sign * b.cost.get(rival, 0)
    item_id = max(paid, key=lambda i: paid[i], default=None)
    items = {i.id: i for i in snapshot.items}
    if item_id is None or paid[item_id] <= 0 or item_id not in items:
        return "Keeping it means more of that rule's cost elsewhere"
    title = items[item_id].title
    was = sorted((b for b in before.blocks if b.item_id == item_id), key=lambda b: b.start_utc)
    now = sorted((b for b in after.blocks if b.item_id == item_id), key=lambda b: b.start_utc)
    lead = kept_said(rules[name].type, title, was, now, snapshot)
    return lead + " " + cost_said(rules[rival].type, "it" if title in lead else title, was, now, snapshot)


Blocks = list[Any]  # one item's blocks in a plan, earliest first


def day_of_block(snapshot: Snapshot, minutes: int) -> date:
    time = snapshot.settings["time"]
    return planning_date(minutes, time.timezone, minutes_of(time.day_start))


def day_said(snapshot: Snapshot, day: date) -> str:
    today = day_of_block(snapshot, snapshot.now_utc)
    return f"{day:%a}" if (day - today).days < 7 else f"{day:%a} {day:%b} {day.day}"


def days_said(snapshot: Snapshot, blocks: Blocks) -> str:
    days = sorted({day_of_block(snapshot, b.start_utc) for b in blocks})
    names = [day_said(snapshot, d) for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def sittings(n: int) -> str:
    return "1 sitting" if n == 1 else f"{n} sittings"


def kept_said(kind: str, title: str, was: Blocks, now: Blocks, snapshot: Snapshot) -> str:
    """What keeping the rule does to that work, where the plans show it; else "Keeping it"."""
    if kind == "finish_early" and was and now:
        sooner = (day_of_block(snapshot, was[-1].end_utc - 1) - day_of_block(snapshot, now[-1].end_utc - 1)).days
        if sooner > 0:
            return f"Finishing {title} {'a day' if sooner == 1 else f'{sooner} days'} sooner"
    if kind == "chunk_cost" and now and len(now) < len(was):
        return f"Doing {title} in {sittings(len(now))} instead of {len(was)}"
    if kind == "deep_run" and was and now:
        longest, longest_was = (max(b.end_utc - b.start_utc for b in blocks) for blocks in (now, was))
        if longest < longest_was:
            return f"Keeping {title} to {span(longest)} at a time"
    if kind == "late_night" and was and now and max(b.end_utc for b in now) < max(b.end_utc for b in was):
        return (
            f"Ending {title} by {clock_time(to_local(max(b.end_utc for b in now), snapshot.settings['time'].timezone))}"
        )
    return "Keeping it"


def cost_said(kind: str, it: str, was: Blocks, now: Blocks, snapshot: Snapshot) -> str:
    """What the other rule loses on that work: more sittings, a later finish, a longer sitting, a later night, or
    else the days or the time it moves to."""
    tz = snapshot.settings["time"].timezone
    if kind == "chunk_cost" and len(now) > len(was):
        return f"splits {it} into {len(now)} sittings instead of {len(was)}" if was else f"splits {it} into {len(now)}"
    if kind == "finish_early" and was and now:
        later, earlier = day_of_block(snapshot, now[-1].end_utc - 1), day_of_block(snapshot, was[-1].end_utc - 1)
        if later > earlier:
            return f"finishes {it} on {day_said(snapshot, later)} instead of {day_said(snapshot, earlier)}"
    if kind == "deep_run" and was and now:
        longest, longest_was = (max(b.end_utc - b.start_utc for b in blocks) for blocks in (now, was))
        if longest > longest_was:
            return f"makes a sitting of {it} {span(longest)} long instead of {span(longest_was)}"
    if kind == "late_night" and was and now:
        end, end_was = (clock_time(to_local(max(b.end_utc for b in blocks), tz)) for blocks in (now, was))
        if max(b.end_utc for b in now) > max(b.end_utc for b in was):
            return f"keeps you on {it} until {end} instead of {end_was}"
    if not now:
        return f"leaves {it} out of the plan"
    if not was:
        return f"plans {it} on {days_said(snapshot, now)}"
    if days_said(snapshot, now) != days_said(snapshot, was):
        return f"moves {it} to {days_said(snapshot, now)} from {days_said(snapshot, was)}"
    first_now, first_was = clock_time(to_local(now[0].start_utc, tz)), clock_time(to_local(was[0].start_utc, tz))
    return f"moves {it} to {first_now} from {first_was}"


def span(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if hours and rest else f"{hours} h" if hours else f"{rest} min"


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
    (personal's), rated by how much they need attending; `going` are titles you said you go to."""
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
        if event.id in snapshot.hidden:
            continue  # a calendar you hid isn't offered to skip: it isn't named (planner/hidden.py)
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
        when = f"{local:%a} {clock_time(local)}"
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
