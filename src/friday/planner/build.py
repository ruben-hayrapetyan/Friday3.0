"""Items, pins and settings → a pruned engine Problem (DESIGN §11.2, §15.2).

`build_problem` is pure: the planner's snapshot (M5) gathers its inputs from the database.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from friday.core.guess import EXAM, same_course, subject_of, subjects
from friday.core.items import Item
from friday.core.pace import DayScales
from friday.core.quickadd import MEAL
from friday.core.settings import SleepDay, bedtime_minutes, minutes_of
from friday.core.textnorm import identity_text, norm
from friday.core.time import (
    UNIT_MIN,
    WEEKDAYS,
    Grid,
    GridSpec,
    make_grid,
    night_utc,
    parse_utc,
    planning_date,
    wake_utc,
)
from friday.engine.problem import DepSpec, EngineItem, FixedOcc, Night, Problem
from friday.engine.prune import demote_unusable_locks, prune
from friday.engine.rules import RULE_TYPES, build_rules
from friday.engine.rules.prices import has_words
from friday.engine.sampler import SamplerConfig, default_chains
from friday.engine.scheduler import SchedulerConfig, StepBudget
from friday.planner.late_cutoff import set_cutoffs

# Rules the build or the job loop applies itself, not the engine's priced or walled rules: time kept around events,
# and meals Friday decides from tracking (`commands/eating.decide`).
PLANNER_RULES = frozenset({"travel", "meal_learned", "late_cutoff"})
# Whether a meal may leave its window is the calendar's to say, not the work's: when events leave no room in it
# (dinner's 5:30-8:30 under a 6pm Zoom and a 7:30 lab), it may go up to MEAL_REACH_MIN outside, priced in the
# wellbeing stage so it stays close; with room nowhere near, it isn't asked for that day. Whether work may take a
# meal's time is yours to say: a rule ("Never skip lunch or dinner") keeps it in the deadlines stage, and the time to
# get there and back with it (`travel_kept`).
MEAL_REACH_MIN = 120
MEAL_WINDOW = {"type": "meal_window", "name": "meal_window", "weight": 1.0, "stage": "wellbeing",
               "params": {"price": 2000.0}}  # fmt: skip
# A pin holds: its time given up costs in the deadlines stage, beside lateness and far below it, so nothing but work
# that would be late moves it (27 Oct). In wellbeing, a heavy Tuesday still took two hours of a pinned evening.
PIN_HOLD = {"type": "pin_hold", "name": "pin_hold", "weight": 1.0, "stage": "deadlines", "params": {"price": 100.0}}


def steady(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Your minimize_changes, split (29 Oct): work with a due, and pinned or timed time, held where it was as before;
    the rest of undated work's place weighed among preferences, beside soft lateness, so a reading due Sunday takes
    the evening an undated task had been given rather than going unplanned."""
    out = []
    for rule in rules:
        if rule["type"] != "minimize_changes":
            out.append(rule)
            continue
        params = rule.get("params") or {}
        out.append({**rule, "params": {**params, "which": "dated"}})
        undated = {"name": f"{rule['name']}_undated", "stage": "preferences", "params": {**params, "which": "undated"}}
        out.append({**rule, **undated})
    return out


LONG_TERM_SCALE = 0.25  # how much Long term work counts when short-term work comes first


@dataclass(frozen=True)
class Pin:
    item_id: int
    start_utc: int
    end_utc: int
    kind: Literal["preferred", "locked"] = "locked"
    created: int = 0  # creation order; the newer of two overlapping locks wins


@dataclass(frozen=True)
class Dependency:
    item_id: int
    depends_on_id: int
    fraction: float = 1.0
    lag_min: int = 0


@dataclass
class BuildInput:
    items: Sequence[Item]
    now_utc: int
    settings: Mapping[str, Any]  # validated settings values by key, as core.settings.DEFAULTS
    dependencies: Sequence[Dependency] = ()
    pins: Sequence[Pin] = ()
    areas: Mapping[int, str] = field(default_factory=dict)
    progress_units: Mapping[int, int] = field(default_factory=dict)  # item id → units done in its window
    progress_today_units: Mapping[int, int] = field(default_factory=dict)
    current: Mapping[int, Sequence[tuple[int, int]]] = field(default_factory=dict)  # item id → (start, end) blocks
    day_scales: Sequence[DayScales] | None = None
    debt_hours: Mapping[date, float] = field(default_factory=dict)
    multipliers: Mapping[str, float] = field(default_factory=dict)
    minimize_changes_scale: float = 1.0
    hold: tuple[int, int, int] | None = None  # the running timer's item, held from (start, end) without a pin
    day_overrides: Mapping[date, Mapping[str, Any]] = field(default_factory=dict)  # bedtime, wake, margin, cap
    routine_min: Mapping[str, int] = field(default_factory=dict)  # tracked sleep: the morning routine by weekday
    woke_utc: int | None = None  # tracked sleep: this morning's "I'm up"
    ready_today: bool = False  # tracked sleep: ready to work this morning
    wind_down_min: Mapping[str, int] = field(default_factory=dict)  # tracked sleep: done with work to bed, by evening
    done_utc: int | None = None  # tracked sleep: tonight's "Done with work"
    end_utc: int | None = None  # truncates the grid (tests, brute force)
    going: frozenset[int] = frozenset()  # optional events you said you'd go to this time: they hold their time
    away: tuple[str, int, int] | None = None  # a nap or a snack now: no work from start to end (`prepare.away_hold`)


def key_of(item_id: int) -> str:
    return f"item:{item_id}"


def id_of(key: str) -> int:
    return int(key.removeprefix("item:"))


def build_problem(inp: BuildInput) -> Problem:
    settings = inp.settings
    grid = make_grid(inp.now_utc, settings["time"].grid_spec(), inp.end_utc)
    fixed, fixed_items = fixed_occurrences(inp, grid.now, grid.horizon_end)
    if inp.away is not None:  # napping, or a snack: no work until it should be over
        fixed.append(FixedOcc(inp.away[0], "other", inp.away[1], inp.away[2], norm_title=inp.away[0].lower()))
    items = flexible_items(inp, grid, fixed_items)
    meal_room(items, fixed, grid)
    pins = pin_slots(inp, grid, items)
    scales = list(inp.day_scales) if inp.day_scales is not None else [DayScales()] * grid.n_days
    problem = Problem(
        grid=grid,
        items=items,
        fixed=fixed,
        nights=nights(inp, grid.spec, grid.slots[0].date, grid.spec.horizon_days),
        day_caps=day_caps(inp, grid),
        rules=[],
        scales=scales,
        energy_map=settings["energy_map"],
        multipliers=dict(inp.multipliers),
        scale=settings["engine"].scale,
        minimize_changes_scale=inp.minimize_changes_scale,
        text=settings["text"].rules(),
    )
    problem.day_caps = repair_locks(problem, pins, inp)
    for key, item in items.items():
        item.locked = frozenset(pins[key]["locked"])
        item.preferred = frozenset(pins[key]["preferred"])
        planned = frozenset(s for lo, hi in inp.current.get(id_of(key), ()) for s in grid.slots_in(lo, hi))
        # A preferred pin counts as already planned there, so `minimize_changes` holds it (×10) even when the plan
        # had the item elsewhere: a block dragged to a new time moves there unless that costs more.
        item.current = planned | item.preferred
        if inp.hold is not None and id_of(key) == inp.hold[0]:
            # What you're timing: `minimize_changes` weighs these slots like a preferred pin, but no pin edge splits
            # the block around them (a lock had cut a 3-hour block into pieces, M16).
            item.held = frozenset(grid.slots_in(inp.hold[1], inp.hold[2]))
            item.current = item.current | item.held
    problem.refresh_locks()
    # A rule whose type a plugin should have defined, but didn't load, is off; the plan report says so.
    rules = [
        rule.model_dump(exclude={"enabled"}) for rule in settings["rules"] if rule.type in RULE_TYPES and rule.enabled
    ]
    problem.rules = build_rules(steady(rules) + [MEAL_WINDOW, PIN_HOLD] + travel_kept(rules))
    for rule in problem.rules:
        rule.prepare(problem)
    set_cutoffs(problem, settings["rules"], settings["time"].timezone)
    prune(problem)
    if demote_unusable_locks(problem):
        prune(problem)
    return problem


def travel_kept(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Beside each rule keeping routines from work, the time to get to and from them kept the same way, at the same
    price (a must's travel is a must too)."""
    return [
        {"type": "travel_kept", "name": f"{r['name']}:travel", "weight": 1.0, "stage": "deadlines",
         "scope": r.get("scope"), "reason": r.get("reason"),
         "params": {"price": (r.get("params") or {}).get("steep", 10000.0)}}
        for r in rules
        if r["type"] == "elastic_shortfall" and r.get("stage") == "deadlines"
    ]  # fmt: skip


def fixed_occurrences(inp: BuildInput, now: int, end: int) -> tuple[list[FixedOcc], dict[int, Item]]:
    """Occurrences overlapping [now, end + a day), and every fixed item by id."""
    kinds = inp.settings["event_kinds"]
    text = inp.settings["text"].rules()
    # Events you said are optional don't wall off their time; the `skippable` rule prices it instead.
    optional = [
        identity_text(norm(t, text))
        for r in inp.settings["rules"]
        if r.type == "skippable" and r.enabled
        for t in r.params.get("titles", [])
        if t.strip()
    ]
    # Time kept around some events by name ("30 minutes before and after gym"), on top of their kind's.
    travel = [
        (identity_text(norm(t, text)), int(r.params.get("before_min", 0)), int(r.params.get("after_min", 0)))
        for r in inp.settings["rules"]
        if r.type == "travel" and r.enabled
        for t in r.params.get("titles", [])
        if t.strip()
    ]
    out, by_id = [], {}
    for item in inp.items:
        if item.when != "fixed":
            continue
        start, end_at = parse_utc(item.start_utc), parse_utc(item.end_utc)  # type: ignore[arg-type]
        by_id[item.id] = item
        if start >= end + 1440:
            continue
        kind = kinds.get(item.event_kind or "other", kinds["other"])
        before = item.buffer_before_min if item.buffer_before_min is not None else kind.before_min
        after = item.buffer_after_min if item.buffer_after_min is not None else kind.after_min
        title = identity_text(norm(item.title, text))
        for words, more_before, more_after in travel:
            if has_words(title, words):
                before, after = max(before, more_before), max(after, more_after)
        # An event already over still holds the time after it: a lecture ending at 10:00 keeps 10:00-10:15 free when
        # the plan starts at 10:00 (the next quarter hour from 9:51); dropped as over, its buffer went with it.
        if end_at + after <= now:
            continue
        skippable = item.blocks_time and item.id not in inp.going and any(has_words(title, o) for o in optional)
        out.append(FixedOcc(item.title, item.event_kind or "other", start, end_at, tuple(item.tags), before, after,
                            item.blocks_time and not skippable, title, skippable))  # fmt: skip
    return out, by_id


def flexible_items(inp: BuildInput, grid: Grid, fixed: Mapping[int, Item]) -> dict[str, EngineItem]:
    by_id = {item.id: item for item in inp.items}
    parents = {item.parent_id for item in inp.items if item.parent_id is not None}
    exams = focus_exams(fixed, inp.settings)
    out: dict[str, EngineItem] = {}
    for item in inp.items:
        if item.when == "fixed" or item.id in parents or item.status != "todo":
            continue
        engine_item = to_engine_item(item, inp, grid, by_id, fixed, exams)
        if engine_item is not None:
            out[engine_item.key] = engine_item
    known = subjects(i.title for i in out.values())  # one course for a stretch (same_course), as Insights reads them
    for engine_item in out.values():
        engine_item.course = subject_of(engine_item.title, known)
    dependencies = [*inp.dependencies, *parts_in_order(inp, out), *long_after_short(inp, out)]
    for engine_item in out.values():
        engine_item.depends_on = dependency_specs(id_of(engine_item.key), dependencies, out)
    return out


SHORT_TERM_DAYS = 7  # short-term work due within this long comes before any long-term work


def long_after_short(inp: BuildInput, items: Mapping[str, EngineItem]) -> list[Dependency]:
    """With `short_term_first`, Long term work waits until the Short term work due this week is done: it isn't
    started in free time while that work is still to do. Long term work due this week itself doesn't wait, and
    meals and habits don't hold anything up."""
    if not inp.settings["short_term_first"]:
        return []
    soon = inp.now_utc + SHORT_TERM_DAYS * 1440
    planned = {item.id: item for item in inp.items if key_of(item.id) in items}
    due_soon = lambda i: i.due_utc is not None and parse_utc(i.due_utc) <= soon  # noqa: E731
    shorts = [i for i in planned.values() if not i.long_term and due_soon(i) and i.preset not in ("Routine", "Habit")]
    longs = [i for i in planned.values() if i.long_term and not due_soon(i)]
    return [Dependency(long.id, short.id) for long in longs for short in shorts]  # type: ignore[arg-type]


def parts_in_order(inp: BuildInput, items: Mapping[str, EngineItem]) -> list[Dependency]:
    """Parts of one set done one after the other (personal's, COMBINED.md 53): tasks of the same kind due the same day
    whose titles start with the same two words ("PS 7 odds" and "PS 7 evens", "Chem HW 5" and "Chem HW 6") each wait
    for the one before, by title, so a plan never alternates between them. Left alone when you tied any yourself."""
    tied = {d.item_id for d in inp.dependencies} | {d.depends_on_id for d in inp.dependencies}
    groups: dict[tuple[str, str, date], list[Item]] = {}
    time = inp.settings["time"]
    for item in inp.items:
        engine_item = items.get(key_of(item.id or 0))
        if engine_item is None or engine_item.due_utc is None or item.preset is None or item.id in tied:
            continue
        if item.series_id is not None or engine_item.firmness == "none":
            continue  # a repeat's occurrences (meals) and work with no deadline aren't parts of a set
        stem = " ".join(re.findall(r"[a-z0-9]+", item.title.lower())[:2])
        day = planning_date(engine_item.due_utc, time.timezone, minutes_of(time.day_start))  # your day, not UTC's
        groups.setdefault((stem, item.preset, day), []).append(item)
    out = []
    for members in groups.values():
        if len({m.title.strip().lower() for m in members}) < len(members):
            continue  # the same title twice is the same thing twice, not two parts
        ordered = sorted(members, key=lambda i: (natural(i.title), i.id))
        out += [Dependency(after.id, before.id) for before, after in zip(ordered, ordered[1:], strict=False)]  # type: ignore[arg-type]
    return out


def natural(title: str) -> list[tuple[int, int, str]]:
    """ "Chapter 9" before "Chapter 10"."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower()) for part in re.split(r"(\d+)", title)]


def window(item: Item, inp: BuildInput, by_id: Mapping[int, Item], fixed: Mapping[int, Item],
           now: int, exams: list[tuple[int, int, str]]) -> tuple[int | None, int | None]:  # fmt: skip
    """Release and due, with a parent's due inherited and dependencies on fixed items folded in (§6.4)."""
    release = parse_utc(item.release_utc) if item.release_utc else None
    due = parse_utc(item.due_utc) if item.due_utc else None
    parent = by_id.get(item.parent_id) if item.parent_id is not None else None
    if due is None and parent is not None and parent.due_utc:
        due = parse_utc(parent.due_utc)
    for dep in inp.dependencies:
        if dep.item_id == item.id and dep.depends_on_id in fixed:
            event_end = parse_utc(fixed[dep.depends_on_id].end_utc)  # type: ignore[arg-type]
            release = max(release if release is not None else now, event_end + dep.lag_min)
        if dep.depends_on_id == item.id and dep.item_id in fixed:  # `before:` an event
            event_start = parse_utc(fixed[dep.item_id].start_utc)  # type: ignore[arg-type]
            due = min(due, event_start - dep.lag_min) if due is not None else event_start - dep.lag_min
    due = exam_due(item, due, fixed, now)
    return focused_release(item, release, due, exams, inp.settings, now), due


def focus_exams(fixed: Mapping[int, Item], settings: Mapping[str, Any]) -> list[tuple[int, int, str]]:
    """The exams exam focus looks at, as start, end and title: found once a build, not once a task (each task
    searched every event's title, 27 Oct)."""
    focus = settings["exam_focus"]
    if not focus.on:
        return []
    words = re.compile(r"\b(" + "|".join(re.escape(w) for w in focus.words) + r")\b", re.IGNORECASE)
    return [
        (parse_utc(exam.start_utc), parse_utc(exam.end_utc), exam.title)
        for exam in fixed.values()
        if exam.start_utc and exam.end_utc and exam.status == "todo" and words.search(exam.title)
    ]


def focused_release(
    item: Item, release: int | None, due: int | None, exams: list[tuple[int, int, str]], settings: Mapping[str, Any],
    now: int,
) -> int | None:  # fmt: skip
    """Exam focus (personal's, COMBINED.md 38): while an exam is `days_before` days off or less, another course's work
    due after it waits until the exam ends, when a day and half again its length still fit before its own due."""
    focus = settings["exam_focus"]
    if not focus.on or due is None or item.preset == "Exam prep":
        return release
    length = (item.duration_units or 0) * UNIT_MIN
    for start, end, title in exams:
        focusing = start - focus.days_before * 1440 <= now < start
        room_after = due - end >= 1440 + 1.5 * length
        if focusing and not same_course(item.title, title) and due > end and room_after:
            release = max(release if release is not None else now, end)
    return release


def exam_due(item: Item, due: int | None, fixed: Mapping[int, Item], now: int) -> int | None:
    """Prep for an exam or quiz on the calendar is due when it starts (personal's, COMBINED.md 50): the same course's
    exam within three days before the prep's due ("Math quiz prep" due the evening of the quiz is due at the quiz).
    Of several, the one nearest the due, and never one already begun: Monday's quiz isn't what Wednesday's midterm
    review is for."""
    if item.preset != "Exam prep" or due is None:
        return due
    starts = [
        parse_utc(f.start_utc)
        for f in fixed.values()
        if f.start_utc and f.status == "todo" and EXAM.search(f.title) and same_course(item.title, f.title)
    ]
    near = [start for start in starts if due - 3 * 1440 <= start <= due and start > now]
    return max(near) if near else due


def to_engine_item(item: Item, inp: BuildInput, grid: Grid, by_id: Mapping[int, Item],
                   fixed: Mapping[int, Item], exams: list[tuple[int, int, str]]) -> EngineItem | None:  # fmt: skip
    release, due = window(item, inp, by_id, fixed, grid.now, exams)
    progress = inp.progress_units.get(item.id, 0)
    preset = inp.settings["presets"].get(item.preset) if item.preset else None
    created = parse_utc(item.created_utc) if item.created_utc else None
    tentative = item.certainty == "tentative"
    engine_item = EngineItem(
        key=key_of(item.id), title=item.title, norm_title=identity_text(norm(item.title, inp.settings["text"].rules())),
        area=inp.areas.get(item.area_id) if item.area_id is not None else None, tags=tuple(item.tags),
        preset=item.preset, energy=item.energy,
        importance=importance(item, inp.settings["kind_order"], inp.settings["short_term_first"])
        * fading(item, inp.settings, grid.now),
        firmness=item.firmness,
        amount=item.amount, release_utc=release, due_utc=due, shape=item.shape,
        min_chunk=1 if item.shape == "one_sitting" else max(1, item.min_chunk_units),
        max_chunk=item.max_chunk_units, chunk_cost=sitting_cost(item, inp.settings), spread=item.spread,
        tentative=tentative,
        progress=progress,
        window_is_hard=tentative or item.amount in ("elastic", "target") or expires(item, inp.settings),
        pacing=preset.pacing if preset else "none", pacing_start_utc=release if release is not None else created,
        travel_before=math.ceil((item.buffer_before_min or 0) / UNIT_MIN),
        travel_after=math.ceil((item.buffer_after_min or 0) / UNIT_MIN),
    )  # fmt: skip
    if item.preset == "Routine" and item.amount == "elastic" and MEAL.search(item.title) and release and due:
        engine_item.meal_window = (release, due)  # how far it may reach is settled once events are known: meal_room
    return with_amount(engine_item, item, inp)


def meal_room(items: Mapping[str, EngineItem], fixed: list[FixedOcc], grid: Grid) -> None:
    """Each meal's window as the calendar leaves it: its own when events leave room for its minimum, else reaching
    up to MEAL_REACH_MIN either side (priced: `meal_window`), else none asked for that day (minimum 0), so a meal
    that can't be had doesn't count as late work the plan keeps trying to fix."""
    busy = sorted((f.blocked_lo, f.blocked_hi) for f in fixed if f.blocks_time)
    for item in items.values():
        if item.meal_window is None:
            continue
        lo, hi = item.meal_window
        if free_run(grid, busy, lo, hi) >= item.min:
            continue
        if free_run(grid, busy, lo - MEAL_REACH_MIN, hi + MEAL_REACH_MIN) >= item.min:
            item.release_utc, item.due_utc = lo - MEAL_REACH_MIN, hi + MEAL_REACH_MIN
        else:
            item.min = 0


def free_run(grid: Grid, busy: list[tuple[int, int]], lo: int, hi: int) -> int:
    """The longest run of whole slots in [lo, hi), from now, that no event (with the time kept around it) touches."""
    near = [(x, y) for x, y in busy if x < hi and y > lo]
    best = run = 0
    for s in grid.slots_in(max(lo, grid.now), hi):
        a, b = int(grid.start[s]), int(grid.end[s])
        if a < max(lo, grid.now) or b > hi or any(x < b and y > a for x, y in near):
            run = 0
            continue
        run += int(grid.units[s])
        best = max(best, run)
    return best


def expires(item: Item, settings: Mapping[str, Any]) -> bool:
    """Pointless once late (COMBINED.md 50): your say on the item, else the kinds and titles in settings."""
    if item.due_utc is None:
        return False
    return (
        item.expires if item.expires is not None else bool(settings["pointless_late"].covers(item.preset, item.title))
    )


def fading(item: Item, settings: Mapping[str, Any], now: int) -> float:
    """What's left of an overdue item's importance when its kind fades once late (`fading_late`, 3 Nov): halved every
    half-life it has been late, measured from its own due. 1 for anything on time, without a due, or pointless once
    late (never planned after its due at all)."""
    if item.due_utc is None or now <= parse_utc(item.due_utc) or expires(item, settings):
        return 1.0
    fade = settings["fading_late"]
    return fade.factor(now - parse_utc(item.due_utc)) if fade.covers(item.preset, item.title) else 1.0


def sitting_cost(item: Item, settings: Mapping[str, Any]) -> float:
    """What splitting an item costs, after your split preference (COMBINED.md 38): kept between 0 and 1."""
    sittings = settings["sittings"]
    if not sittings.one_go:
        return item.chunk_cost
    factor = 0.5 if item.preset in sittings.split_first else sittings.factor
    return min(1.0, max(item.chunk_cost, 0.05) * factor)


def importance(item: Item, kind_order: Sequence[str], short_term_first: bool = False) -> float:
    """The item's importance, scaled by its kind's place in `kind_order`: twice for the first, once for the last
    and for kinds not listed. Lateness is priced by importance, so the first kinds keep their time. With
    `short_term_first`, Long term work counts a quarter as much, and waits for this week's short-term work
    (`long_after_short`)."""
    scale = LONG_TERM_SCALE if short_term_first and item.long_term else 1.0
    if item.preset not in kind_order or len(kind_order) < 2:
        return item.importance * scale
    rank = list(kind_order).index(item.preset)
    return item.importance * scale * (1 + (len(kind_order) - 1 - rank) / (len(kind_order) - 1))


def with_amount(engine_item: EngineItem, item: Item, inp: BuildInput) -> EngineItem | None:
    progress = engine_item.progress
    if item.amount == "fixed" and item.background:
        # It runs by itself: only its first quarter hour needs you, early enough for the rest to run before its due;
        # once started (any of it done), nothing more is yours to plan.
        if progress > 0 or not item.duration_units:
            return None
        engine_item.need = engine_item.min_chunk = 1
        engine_item.runs_units = item.duration_units - 1
        running = (item.duration_units - 1) * UNIT_MIN
        if engine_item.due_utc is not None:
            engine_item.due_utc -= running
        engine_item.size_hours = UNIT_MIN / 60
        return engine_item
    if item.amount == "fixed":
        engine_item.need = max(0, (item.duration_units or 0) - progress)
        if engine_item.need == 0:
            return None  # finished: awaiting confirmation, not scheduled
        # The last bit of an item may be shorter than its minimum chunk; otherwise it fits nowhere before its due.
        engine_item.min_chunk = min(engine_item.min_chunk, engine_item.need)
        engine_item.size_hours = (item.duration_units or 0) * UNIT_MIN / 60
    elif item.amount == "elastic":
        engine_item.min = max(0, (item.min_units or 0) - progress)
        engine_item.ideal = max(engine_item.min, (item.ideal_units or 0) - progress)
        engine_item.max = max(engine_item.ideal, (item.max_units or 0) - progress)
        engine_item.size_hours = (item.ideal_units or 0) * UNIT_MIN / 60
    elif item.amount == "target":
        engine_item.target = item.target_units or 0
        engine_item.cap = item.cap_units or math.ceil(1.5 * engine_item.target)
        engine_item.size_hours = engine_item.target * UNIT_MIN / 60
    else:
        engine_item.daily_ceiling = item.daily_ceiling_units or 12
        engine_item.progress_today = inp.progress_today_units.get(item.id, 0)
    return engine_item


def dependency_specs(
    item_id: int, dependencies: Sequence[Dependency], items: Mapping[str, EngineItem]
) -> tuple[DepSpec, ...]:
    out = []
    for dep in dependencies:
        other = items.get(key_of(dep.depends_on_id))
        if dep.item_id == item_id and other is not None:
            out.append(DepSpec(other.key, dep.fraction, dep.lag_min, other.total_units, other.progress))
    return tuple(out)


def nights(inp: BuildInput, spec: GridSpec, first: date, days: int) -> dict[date, Night]:
    """The nights beginning on the day before `first` through two days after the last of `days`."""
    sleep = inp.settings["sleep"]
    if sleep is None:
        raise ValueError("sleep: not set yet; run `fridayd init`")
    out = {}
    for offset in range(-1, days + 2):
        day = first + timedelta(days=offset)
        bedtime, wake, margin = night_times(inp.settings, inp.day_overrides, day, spec.timezone, spec.day_start)
        routine = inp.routine_min.get(WEEKDAYS[(day + timedelta(days=1)).weekday()])
        if offset == -1 and inp.woke_utc is not None:  # last night: up early frees the morning, late moves the routine
            wake, routine = inp.woke_utc, 0 if inp.ready_today else routine
        else:  # an event you're going to before you'd be ready (Gym at 7:30, up at 8): up for it, routine and all
            early = early_event(inp, bedtime + margin, wake + (routine or 0))
            if early is not None:
                wake = max(bedtime + margin, min(wake, early - (routine or 0)))
        wind_down = inp.wind_down_min.get(WEEKDAYS[day.weekday()])
        done = inp.done_utc if offset == 0 else None  # tonight's: you said you're done with work
        out[day] = Night(bedtime, wake, margin, inp.debt_hours.get(day, 0.0), routine, wind_down, done)
    return out


def early_event(inp: BuildInput, after: int, before: int) -> int | None:
    """The start of the first event you're going to between `after` (your night, past bedtime's margin) and `before`
    (up and ready, as your sleep times say), or None (29 Oct: Gym at 7:30 and Climbing Club at 6 on mornings Friday
    took you to be asleep until 8, so the 7 hours of sleep were counted back from 8 on those nights too). A whole-day
    event isn't one to get up for."""
    starts = [
        start
        for i in inp.items
        if i.when == "fixed" and i.status == "todo" and i.blocks_time and i.start_utc and i.end_utc
        and after < (start := parse_utc(i.start_utc)) < before and parse_utc(i.end_utc) - start < 12 * 60
    ]  # fmt: skip
    return min(starts, default=None)


def night_times(
    settings: Mapping[str, Any], overrides: Mapping[date, Mapping[str, Any]], day: date, tz: str, day_start: int
) -> tuple[int, int, int]:
    """The night beginning on `day`: bedtime and wake (UTC minutes) and the margin after bedtime."""
    evening = sleep_on(settings, overrides, day)
    morning = sleep_on(settings, overrides, day + timedelta(days=1))
    bedtime = bedtime_minutes(evening.bedtime, morning.wake, day_start)
    return night_utc(day, bedtime, tz), wake_utc(day, minutes_of(morning.wake), tz), evening.margin_min


def sleep_on(settings: Mapping[str, Any], overrides: Mapping[date, Mapping[str, Any]], day: date) -> SleepDay:
    """That date's bedtime (the evening) and wake (the morning), with a day override over the weekday setting."""
    usual = settings["sleep"][WEEKDAYS[day.weekday()]]
    override = {k: v for k, v in overrides.get(day, {}).items() if k in SleepDay.model_fields and v is not None}
    return usual.model_copy(update=override) if override else usual


def cap_hours_on(settings: Mapping[str, Any], overrides: Mapping[date, Mapping[str, Any]], day: date) -> float:
    override = overrides.get(day, {}).get("cap_hours")
    return override if override is not None else settings["daily_cap"][WEEKDAYS[day.weekday()]]


def day_caps(inp: BuildInput, grid: Grid) -> list[int]:
    return [round(cap_hours_on(inp.settings, inp.day_overrides, d) * 60 / UNIT_MIN) for d in grid.day_date]


def pin_slots(inp: BuildInput, grid: Grid, items: Mapping[str, EngineItem]) -> dict[str, dict[str, set[int]]]:
    out: dict[str, dict[str, set[int]]] = {k: {"locked": set(), "preferred": set()} for k in items}
    for pin in sorted(inp.pins, key=lambda p: p.created):
        key = key_of(pin.item_id)
        if key in out:
            out[key][pin.kind].update(grid.slots_in(pin.start_utc, pin.end_utc))
    return out


def repair_locks(problem: Problem, pins: dict[str, dict[str, set[int]]], inp: BuildInput) -> list[int]:
    """The lock checks of §15.2. Returns the day caps, raised where locks exceed them."""
    grid, created = problem.grid, {key_of(p.item_id): p.created for p in inp.pins if p.kind == "locked"}
    owner: dict[int, str] = {}
    for key in sorted(pins, key=lambda k: (created.get(k, -1), k)):  # the newer lock wins an overlap
        for s in sorted(pins[key]["locked"]):
            older = owner.get(s)
            if older is not None:
                pins[older]["locked"].discard(s)
                pins[older]["preferred"].add(s)
            owner[s] = key
    for key, slots in pins.items():
        over_fixed = {s for s in slots["locked"] if problem.blocked[s]}
        slots["locked"] -= over_fixed
        slots["preferred"] |= over_fixed
        if over_fixed:  # said in the plan's notes: a lock you made, not kept, and why
            first = int(grid.start[min(over_fixed)])
            event = next(
                (f.title for f in problem.fixed if f.blocks_time and f.blocked_lo <= first < f.blocked_hi), "an event"
            )
            problem.locks_over_events.append((key, event, first))
    for key, slots in pins.items():
        item = problem.items[key]
        locked_units = sum(int(grid.units[s]) for s in slots["locked"])
        if item.amount == "fixed" and locked_units > item.need:
            item.need = locked_units
    caps = list(problem.day_caps)
    for d in range(grid.n_days):
        locked_today = sum(int(grid.units[s]) for p in pins.values() for s in p["locked"] if grid.slots[s].day == d)
        caps[d] = max(caps[d], locked_today)
    return caps


def scheduler_config(settings: Mapping[str, Any], threads: int | None = None) -> SchedulerConfig:
    """The engine settings as the scheduler takes them. Plans depend on `engine.chains`, never on `threads`."""
    engine = settings["engine"]
    chains = engine.chains or default_chains()
    sampler = SamplerConfig(
        policy=engine.stage_policy,
        weighted_ratio=engine.weighted_ratio,
        seed=engine.seed,
        chains=chains,
        threads=threads if threads is not None else min(chains, default_chains()),
        t0=engine.t0,
        t1=engine.t1,
        tabu_after_steps=engine.tabu_after_steps,
        move_weights=dict(engine.move_weights),
    )
    return SchedulerConfig(
        sampler=sampler,
        step_budgets=tuple(StepBudget(b.max_items, b.cold, b.warm) for b in engine.step_budgets),
        warm_t0=engine.warm_t0,
        repair_steps=engine.repair_steps,
        fallback_threshold=engine.fallback_threshold,
        fallback_s=engine.fallback_s,
        fallback_overload_s=engine.fallback_overload_s,
        fallback_overload_warm_s=engine.fallback_overload_warm_s,
        fallback_warm_s=engine.fallback_warm_s,
        fallback_workers=engine.fallback_workers,
    )
