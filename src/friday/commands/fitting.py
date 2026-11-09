"""Do I have time for this? A change tried on a copy of your plan and never kept (`registry.tried`): a task to add,
an event (going to an optional one is an event over its time), a shove, a rule, a day's limits.

- The quick answer (well under a second) runs the deadline check, every hard due on the time left after events and
  sleep, before the change and with it: what could no longer be done by its due, and how much free time a new task
  has before it must start. It's the best case (work packed into every free minute), so "late" is certain and
  "fits" means it can.
- The exact one plans the week as a replan would, without the change and with it, side by side (the engine and
  CP-SAT run outside Python's lock): what would end later past its due, whether it fits only by working later at
  night, and how many blocks would move. Planned at the same moment from the same plan, the two differ only by the
  change; against the saved plan they didn't (it may be hours old, or the night's fresh one).
- An event that makes work late is offered up to three nearby times that don't (the same day, else the next ones).
"""

import time
from concurrent.futures import ThreadPoolExecutor

from friday.api.commands import FitInput
from friday.api.views import FitLate, FitOut, FitTime
from friday.commands.registry import Ctx, query, tried
from friday.core.items import Item
from friday.core.time import format_local, parse_utc, to_local
from friday.engine.executor import ExecutorInput, Interval, edf, slack, subtract
from friday.engine.problem import Problem
from friday.planner.build import build_problem, id_of, key_of
from friday.planner.inputs import executor_input
from friday.planner.prepare import build_input
from friday.planner.service import plan_snapshot
from friday.planner.snapshot import Snapshot, read_snapshot, take_snapshot

TIGHT_MIN = 120  # a new task with less free time than this before it must start fits only just
STEP_MIN = 30  # other times for an event are tried this far apart, up to half a day either way
SHOWN = 3


@query("fit")
def fit(ctx: Ctx, inp: FitInput) -> FitOut:
    """Do I have time for this? A change tried on a copy of your plan, never kept.

    Whether everything still fits with it (a task, an event, a shove, a rule), what would be late, and for an event
    that makes work late, times that don't."""
    began = time.perf_counter()
    before = take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    after = tried(ctx.conn, inp.command, inp.input, lambda conn: read_snapshot(conn, ctx.now_utc, ctx.user_id),
                  now_utc=ctx.now_utc, user_id=ctx.user_id)  # fmt: skip
    titles = {i.id: i.title for i in after.items} | {i.id: i.title for i in before.items}
    out = exactly(before, after, titles) if inp.exact else quickly(before, after, titles)
    if out.verdict == "late" and (event := moved_event(before, after)) is not None:
        out.instead = other_times(ctx, before, event)
    out.seconds = round(time.perf_counter() - began, 2)
    return out


def deadlines(snapshot: Snapshot) -> ExecutorInput:
    return deadlines_and_problem(snapshot)[0]


def deadlines_and_problem(snapshot: Snapshot) -> tuple[ExecutorInput, Problem]:
    inp = build_input(snapshot)
    problem = build_problem(inp)
    return executor_input(inp, problem), problem


def over_caps(problem: Problem, new: set[str]) -> bool:
    """Whether the work due by a new item's due is more than your daily limits allow before it (audit, 8 Nov: the
    quick answer, by free time alone, said "Fits" to 8 h due tomorrow on a 3 h day)."""
    grid = problem.grid
    for key in new:
        item = problem.items.get(key)
        if item is None or item.due_utc is None:
            continue
        days = [d for d in range(grid.n_days) if grid.day_slots[d] and grid.start[grid.day_slots[d][0]] < item.due_utc]
        room = sum(problem.day_caps[d] for d in days)
        due = [
            i
            for i in problem.items.values()
            if i.amount == "fixed" and i.due_utc is not None and i.due_utc <= item.due_utc
        ]
        if sum(i.need for i in due) > room:
            return True
    return False


def late_minutes(ex: ExecutorInput, free: list[Interval] | None = None) -> dict[str, int]:
    """Each hard due's minutes late in the best case: every free minute used, earliest due first."""
    result = edf(ex.jobs, ex.free if free is None else free)
    return {j.key: max(0, result.finish[j.key] - j.due) for j in ex.jobs}


def short_minutes(ex: ExecutorInput) -> dict[str, int]:
    """Each hard due's minutes of work that don't fit before it, in that best case."""
    result = edf(ex.jobs, ex.free)
    done = {j.key: sum(max(0, min(hi, j.due) - lo) for lo, hi in result.pieces[j.key]) for j in ex.jobs}
    return {j.key: max(0, j.minutes - done[j.key]) for j in ex.jobs}


def hours(minutes: float) -> str:
    whole, rest = divmod(round(minutes / 5) * 5, 60)
    return f"{whole} h {rest} min" if whole and rest else f"{whole} h" if whole else f"{rest} min"


def listed(later: list[FitLate]) -> str:
    """What it would make late, the worst first: `Would leave Essay 2 h short of its due` (quick: the work that no
    longer fits before it), `Would make Essay finish 9 h 30 min after its due` (exact), and how many more."""
    more = f", and {len(later) - 2} more" if len(later) > 2 else ""
    if all(x.short_h is not None for x in later):
        named = " and ".join(f"{x.title} {hours((x.short_h or 0) * 60)}" for x in later[:2])
        return f"Would leave {named} short of {'its due' if len(later) == 1 else 'their dues'}{more}"
    named = " and ".join(
        f"{x.title} finish {hours((x.after_h - x.before_h) * 60)} {'later past' if x.before_h else 'after'} its due"
        for x in later[:2]
    )
    return f"Would make {named}{more}"


def quickly(before: Snapshot, after: Snapshot, titles: dict[int, str]) -> FitOut:
    base, (ex, problem) = deadlines(before), deadlines_and_problem(after)
    was, now = late_minutes(base), late_minutes(ex)
    was_short, short = short_minutes(base), short_minutes(ex)
    later = worst_first(
        FitLate(item_id=id_of(k), title=titles.get(id_of(k), k), before_h=round(was.get(k, 0) / 60, 2),
                after_h=round(m / 60, 2), short_h=round((short[k] - was_short.get(k, 0)) / 60, 2))
        for k, m in now.items()
        if m > was.get(k, 0) + 5 and short[k] > was_short.get(k, 0)
    )  # fmt: skip
    room = slack(ex)
    known = {i.id for i in before.items}
    spare = [room[key_of(i.id)].free_minutes for i in after.items if i.id not in known and key_of(i.id) in room]
    spare_h = round(min(spare) / 60, 1) if spare else None
    if later:
        return FitOut(verdict="late", said=listed(later), exact=False, later=later, spare_h=spare_h)
    if over_caps(problem, {key_of(i.id) for i in after.items if i.id not in known}):
        return FitOut(verdict="tight", said="Fits in your free time, but not within your daily limits: check exactly",
                      exact=False, spare_h=spare_h)  # fmt: skip
    if spare_h is not None and spare_h * 60 < TIGHT_MIN:
        return FitOut(verdict="tight", said=f"Fits, only just: {hours(spare_h * 60)} to spare before it's due",
                      exact=False, spare_h=spare_h)  # fmt: skip
    said = (
        f"Fits: {hours(spare_h * 60)} free before it must start" if spare_h is not None else "Fits: nothing gets later"
    )
    return FitOut(verdict="fits", said=said, exact=False, spare_h=spare_h)


def exactly(before: Snapshot, after: Snapshot, titles: dict[int, str]) -> FitOut:
    with ThreadPoolExecutor(2) as pool:
        without, plan = pool.map(lambda snapshot: plan_snapshot(snapshot, warm=True), (before, after))
    report = without.report
    was = {int(k): v for k, v in report.get("late_hours", {}).items()}
    now = {int(k): v for k, v in plan.report.get("late_hours", {}).items()}
    later = worst_first(
        FitLate(item_id=i, title=titles.get(i, f"T{i}"), before_h=round(was.get(i, 0.0), 2), after_h=round(h, 2))
        for i, h in now.items()
        if h > was.get(i, 0.0) + 0.05
    )
    blocks = lambda assembled: {(b.item_id, b.start_utc, b.end_utc) for b in assembled.blocks}  # noqa: E731
    known = {i.id for i in before.items}
    moved = sum(1 for b in blocks(plan) - blocks(without) if b[0] in known)  # yours that move, not the new one's
    later_nights = plan.report.get("rule_totals", {}).get("late_night", 0) > report.get("rule_totals", {}).get(
        "late_night", 0
    )
    if later:
        return FitOut(verdict="late", said=listed(later), exact=True, later=later, moved=moved)
    if later_nights:
        return FitOut(verdict="tight", said="Fits, but only with later nights than you have now", exact=True,
                      later_nights=True, moved=moved)  # fmt: skip
    return FitOut(verdict="fits", said="Fits: nothing gets later" + (f", {moved} blocks move" if moved else ""),
                  exact=True, moved=moved)  # fmt: skip


def worst_first(found) -> list[FitLate]:  # noqa: ANN001
    return sorted(found, key=lambda x: x.before_h - x.after_h)


def moved_event(before: Snapshot, after: Snapshot) -> Item | None:
    """The event the change adds or moves, if it adds or moves one that takes time."""
    was = {i.id: (i.start_utc, i.end_utc) for i in before.items}
    events = [i for i in after.items if i.when == "fixed" and i.blocks_time and i.start_utc and i.end_utc]
    changed = [i for i in events if was.get(i.id or 0) != (i.start_utc, i.end_utc)]
    return changed[0] if len(changed) == 1 else None


def other_times(ctx: Ctx, before: Snapshot, event: Item) -> list[FitTime]:
    """The event at nearby times where nothing gets later than without it: half an hour apart on its day, nearest
    first, then the same time on the next three days; never over another event or your sleep, nor in the past."""
    base = deadlines(before)
    start, end = parse_utc(event.start_utc), parse_utc(event.end_utc)  # type: ignore[arg-type]
    if end - start > 12 * 60:
        return []
    was = sum(late_minutes(base).values())
    shifts = sorted(range(-24 * STEP_MIN, 24 * STEP_MIN + 1, STEP_MIN), key=abs)[1:] + [d * 1440 for d in (1, 2, 3)]
    out: list[FitTime] = []
    for shift in shifts:
        lo, hi = start + shift, end + shift
        if lo < base.now or not any(a <= lo and hi <= b for a, b in base.free):
            continue
        if sum(late_minutes(base, subtract(base.free, [(lo, hi)])).values()) <= was:
            out.append(FitTime(start=format_local(to_local(lo, ctx.tz)), end=format_local(to_local(hi, ctx.tz))))
            if len(out) == SHOWN:
                break
    return out
