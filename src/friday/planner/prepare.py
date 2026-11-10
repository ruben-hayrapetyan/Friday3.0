"""Snapshot → BuildInput (DESIGN §15.2): progress per §8, the timer's hold, each day's dials, overrides, pins."""

import dataclasses
from datetime import date, timedelta

from friday.core.pace import dials_on, scales
from friday.core.settings import minutes_of
from friday.core.time import UNIT_MIN, format_utc, parse_utc, planning_date
from friday.planner.build import BuildInput, Dependency, Pin, night_times
from friday.planner.cushion import past_shortened
from friday.planner.progress import recorded_minutes, remaining_minutes
from friday.planner.snapshot import BlockRow, Snapshot
from friday.planner.spacing import LastDone, let_go, loosened, spaced
from friday.planner.timed import timed_over, with_running


def block_key(item_id: int, start_utc: int) -> str:
    return f"T{item_id}@{format_utc(start_utc)}"


def today(snapshot: Snapshot) -> date:
    time = snapshot.settings["time"]
    return planning_date(snapshot.now_utc, time.timezone, minutes_of(time.day_start))


def day_of(snapshot: Snapshot, moment: int) -> date:
    time = snapshot.settings["time"]
    return planning_date(moment, time.timezone, minutes_of(time.day_start))


def assumed_blocks(snapshot: Snapshot) -> list[BlockRow]:
    """Past blocks that count as done until the review says otherwise (§8 rule 1): today's, and an earlier day's
    the plan still holds until that day is reviewed or closed (`close_day` writes them as progress, which settles
    them here). The nightly job runs before the day starts, so it closes a day only the night after next."""
    if snapshot.settings["planner"].assume_unreviewed != "done":
        return []
    upto = -(-snapshot.now_utc // UNIT_MIN) * UNIT_MIN  # where the new plan begins, holding the timed item from there
    sittings = with_running(
        (
            (item_id, parse_utc(r["start_utc"]), parse_utc(r["end_utc"]))
            for item_id, found in snapshot.progress.items()
            for r in found
            if r["source"] == "timer" and r["start_utc"] and r["end_utc"]
        ),
        (*snapshot.alongside, *([snapshot.timer] if snapshot.timer else [])),
        upto,
    )
    background = {i.id for i in snapshot.items if i.background and i.id is not None}
    out = []
    for block in snapshot.plan_blocks:
        day = day_of(snapshot, block.start_utc)
        if (
            block.start_utc >= snapshot.now_utc
            or block.tentative
            or day > today(snapshot)
            or day in snapshot.reviewed_dates
        ):
            continue
        # A running block counts up to where the new plan begins, the next quarter hour, so no minutes fall between.
        block = dataclasses.replace(block, end_utc=min(block.end_utc, upto))
        recorded = snapshot.progress.get(block.item_id, ())
        settled = any(r["block_key"] == block_key(block.item_id, block.start_utc) for r in recorded)
        # A sitting of it replaces the block (§8 rule 1); one mostly under other things you timed wasn't done.
        timed = timed_over(block.item_id, block.start_utc, block.end_utc, sittings, background) is not None
        # The slider sets the total as of when you moved it: a block begun before then is in that total already.
        slid = any(r["source"] == "slider" and parse_utc(r["created_utc"]) > block.start_utc for r in recorded)
        if not settled and not timed and not slid:
            out.append(block)
    return out


def progress_minutes(snapshot: Snapshot) -> tuple[dict[int, int], dict[int, int]]:
    """Minutes done per item, in all and today: recorded rows, assumed blocks and the running timers."""
    total = {item_id: recorded_minutes(list(found)) for item_id, found in snapshot.progress.items()}
    this_day = today(snapshot)
    on_today: dict[int, int] = {}
    for item_id, found in snapshot.progress.items():
        today_rows = [r for r in found if r["start_utc"] and day_of(snapshot, parse_utc(r["start_utc"])) == this_day]
        on_today[item_id] = sum(r["minutes"] for r in today_rows)
    # Each with whether it was today's: an earlier day's assumed block counts in all, not toward today's work.
    extra = [
        (b.item_id, b.end_utc - b.start_utc, day_of(snapshot, b.start_utc) == this_day)
        for b in assumed_blocks(snapshot)
    ]
    for item_id, since in (*snapshot.alongside, *([snapshot.timer] if snapshot.timer else [])):
        extra.append((item_id, max(0, snapshot.now_utc - since), True))  # alongside too: its time is being done
    for item_id, minutes, todays in extra:
        total[item_id] = total.get(item_id, 0) + minutes
        if todays:
            on_today[item_id] = on_today.get(item_id, 0) + minutes
    if snapshot.timer is not None:
        keep_a_hold(snapshot, total, on_today)
    return total, on_today


def keep_a_hold(snapshot: Snapshot, total: dict[int, int], on_today: dict[int, int]) -> None:
    """While the timer runs, a hold's worth of its item stays remaining however long it has run (an unreviewed block
    it overlaps counts too): timing past its length extends it in the plan and reflows what came after (scenario
    21), instead of it dropping out as if finished while you're still on it."""
    item_id = snapshot.timer[0] if snapshot.timer else 0
    item = next((i for i in snapshot.items if i.id == item_id), None)
    full = remaining_minutes(item, 0) if item is not None else None
    if full is None:
        return
    over = total.get(item_id, 0) - max(0, full - snapshot.settings["planner"].timer_hold_min)
    if over > 0:
        total[item_id] -= over
        on_today[item_id] = max(0, on_today.get(item_id, 0) - over)


def timer_hold(snapshot: Snapshot) -> tuple[int, int, int] | None:
    """The timed item, held from the plan's first slot for `timer_hold_min` (§8 rule 2); with no timer, the meal you're
    eating, its routine held for what's left of its length, so no work is planned while you eat."""
    at = snapshot.now_utc + (-snapshot.now_utc) % UNIT_MIN
    if snapshot.timer is not None:
        return (snapshot.timer[0], at, at + snapshot.settings["planner"].timer_hold_min)
    meal = next((i for i in snapshot.items if snapshot.eating and i.id == snapshot.eating[0]), None)
    if meal is None or snapshot.eating is None:
        return None
    left = snapshot.eating[1] + (meal.ideal_units or meal.min_units or 1) * UNIT_MIN - at
    return (snapshot.eating[0], at, at + max(UNIT_MIN, left + (-left) % UNIT_MIN))


def away_hold(snapshot: Snapshot) -> tuple[str, int, int] | None:
    """A nap or a snack (`Snapshot.away`), kept clear of work from the plan's first slot until it should end: a quarter
    hour at least while it runs."""
    if snapshot.away is None:
        return None
    title, _, until = snapshot.away
    at = snapshot.now_utc + (-snapshot.now_utc) % UNIT_MIN
    return (title, at, max(at + UNIT_MIN, until + (-until) % UNIT_MIN))


def day_scales(snapshot: Snapshot) -> list:
    settings = snapshot.settings
    first = today(snapshot)
    days = settings["time"].allocator_weeks * 7 + 1
    return [
        scales(
            dials_on(
                first + timedelta(days=d),
                list(snapshot.pace_periods),
                settings["paces"],
                settings["pace"].default,
                settings["pace"].weekly,
            )
        )
        for d in range(days)
    ]


DEBT_NIGHTS = 3


def debt_hours(snapshot: Snapshot) -> dict[date, float]:
    """Sleep debt (DESIGN §12.3): for each night from tonight, the hours of work recorded (or being timed) inside the
    margins after bedtime of the three nights before it. Only work already done counts, so it is known when the plan
    is built; nights more than three ahead owe nothing."""
    settings, time = snapshot.settings, snapshot.settings["time"]
    if settings["sleep"] is None:
        return {}
    first, start = today(snapshot), minutes_of(time.day_start)
    sessions = [
        (parse_utc(r["start_utc"]), parse_utc(r["end_utc"]))
        for found in snapshot.progress.values()
        for r in found
        if r["start_utc"] and r["end_utc"]
    ]
    if snapshot.timer is not None:
        sessions.append((snapshot.timer[1], snapshot.now_utc))
    owed: dict[date, float] = {}
    for back in range(0, DEBT_NIGHTS + 1):  # tonight too: work past bedtime so far makes tomorrow's late hours dearer
        night = first - timedelta(days=back)
        bedtime, wake, margin = night_times(settings, snapshot.day_overrides, night, time.timezone, start)
        hours = sum(max(0, min(end, bedtime + margin) - max(begin, bedtime)) for begin, end in sessions) / 60
        if snapshot.sleep and night in snapshot.sleep.slept_min:  # a tracked night: what it fell short by, if more
            napped = snapshot.sleep.napped_min.get(night + timedelta(days=1), 0)  # less the next day's naps
            hours = max(hours, (wake - bedtime - snapshot.sleep.slept_min[night] - napped) / 60)
        for later in range(1, DEBT_NIGHTS + 1):  # it is owed on each of the three nights after it, from tonight on
            if (owed_on := night + timedelta(days=later)) >= first:
                owed[owed_on] = owed.get(owed_on, 0.0) + hours
    return {day: hours for day, hours in owed.items() if hours > 0}


def build_input(snapshot: Snapshot, end_utc: int | None = None) -> BuildInput:
    done, on_today = progress_minutes(snapshot)
    pins = [Pin(p.item_id, p.start_utc, p.end_utc, p.kind, p.id) for p in snapshot.pins]  # type: ignore[arg-type]
    current: dict[int, list[tuple[int, int]]] = {}
    for block in snapshot.plan_blocks:
        current.setdefault(block.item_id, []).append((block.start_utc, block.end_utc))
    stability = 1.0 if snapshot.next_stability is None else snapshot.next_stability
    if snapshot.cold_once:
        # A plan made afresh on purpose (another way, its pick, "Which should win?") lets go of where your blocks are:
        # held there (minimize_changes, in wellbeing, above every preference), no reweighing could move them, and every
        # other way came out as your plan or paid for each hour it moved (C89). Pins and what you're timing still hold.
        stability = 0.0
    last = {k: LastDone(*v) for k, v in snapshot.series_last.items()}
    items, waits, originals = spaced([past_shortened(i, done.get(i.id, 0) // UNIT_MIN) for i in snapshot.items],
                                     snapshot.series_gaps, last)  # fmt: skip
    inp = BuildInput(
        items=items,
        now_utc=snapshot.now_utc,
        settings=snapshot.settings,
        dependencies=[*(Dependency(a, b, fraction, lag) for a, b, fraction, lag in snapshot.dependencies), *waits],
        pins=pins,
        areas=snapshot.areas,
        progress_units={k: v // UNIT_MIN for k, v in done.items()},
        progress_today_units={k: v // UNIT_MIN for k, v in on_today.items()},
        current=current,
        day_scales=day_scales(snapshot),
        minimize_changes_scale=stability,
        hold=timer_hold(snapshot),
        away=away_hold(snapshot),
        day_overrides=snapshot.day_overrides,
        end_utc=end_utc,
        multipliers=snapshot.multipliers,
        debt_hours=debt_hours(snapshot),
        routine_min=snapshot.sleep.routine_min if snapshot.sleep else {},
        woke_utc=snapshot.sleep.woke_utc if snapshot.sleep else None,
        ready_today=bool(snapshot.sleep and snapshot.sleep.ready),
        wind_down_min=snapshot.sleep.wind_down_min if snapshot.sleep else {},
        done_utc=snapshot.sleep.done_utc if snapshot.sleep else None,
        going=snapshot.going,
    )
    if not originals:
        return inp
    # Keeping times apart is a strong preference, not a wall (C50): a spaced time that would be late with its wait is
    # brought closer to the one before, by as much as it would be late (8 Nov: dropping the wait outright put the next
    # laundry 2.5 days after the last, where 6.6 fit).
    from friday.planner.service import quick_late  # the planner's own quick check; it builds from this input

    others = [d for d in inp.dependencies if d not in waits]
    for _ in range(3):  # brought closer by as much as they'd be late, checked again
        _, late = quick_late(inp, with_fallback=False)
        loose, kept = loosened(list(inp.items), waits, originals, late)
        if kept == waits and loose == list(inp.items):
            return inp
        waits = kept
        inp = dataclasses.replace(inp, items=loose, dependencies=[*others, *waits])
    # Still late after three rounds: something long covers its due (a trip), so a few hours closer isn't enough.
    # Those times wait for nothing and get their own windows back (8 Nov: laundry went 10 h late past a trip).
    _, late = quick_late(inp, with_fallback=False)
    loose, kept = let_go(list(inp.items), waits, originals, late)
    return dataclasses.replace(inp, items=loose, dependencies=[*others, *kept])
