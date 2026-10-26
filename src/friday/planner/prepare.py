"""Snapshot → BuildInput (DESIGN §15.2): progress per §8, the timer's hold, each day's dials, overrides, pins."""

import dataclasses
from datetime import date, timedelta

from friday.core.pace import dials_on, scales
from friday.core.settings import minutes_of
from friday.core.time import UNIT_MIN, format_utc, parse_utc, planning_date
from friday.planner.build import BuildInput, Dependency, Pin, night_times
from friday.planner.progress import recorded_minutes, remaining_minutes
from friday.planner.snapshot import BlockRow, Snapshot


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
        block = dataclasses.replace(block, end_utc=min(block.end_utc, -(-snapshot.now_utc // UNIT_MIN) * UNIT_MIN))
        recorded = snapshot.progress.get(block.item_id, ())
        settled = any(r["block_key"] == block_key(block.item_id, block.start_utc) for r in recorded)
        timed = any(r["source"] == "timer" and overlaps(r, block) for r in recorded)  # a session replaces the block
        # The slider sets the total as of when you moved it: a block begun before then is in that total already.
        slid = any(r["source"] == "slider" and parse_utc(r["created_utc"]) > block.start_utc for r in recorded)
        if not settled and not timed and not slid:
            out.append(block)
    return out


def overlaps(row: dict, block: BlockRow) -> bool:
    if not row["start_utc"] or not row["end_utc"]:
        return False
    return parse_utc(row["start_utc"]) < block.end_utc and parse_utc(row["end_utc"]) > block.start_utc


def progress_minutes(snapshot: Snapshot) -> tuple[dict[int, int], dict[int, int]]:
    """Minutes done per item, in all and today: recorded rows, assumed blocks and the running timer."""
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
    if snapshot.timer is not None:
        extra.append((snapshot.timer[0], max(0, snapshot.now_utc - snapshot.timer[1]), True))
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
    """The timed item, held from the plan's first slot for `timer_hold_min` (§8 rule 2)."""
    if snapshot.timer is None:
        return None
    at = snapshot.now_utc + (-snapshot.now_utc) % UNIT_MIN
    return (snapshot.timer[0], at, at + snapshot.settings["planner"].timer_hold_min)


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
            hours = max(hours, (wake - bedtime - snapshot.sleep.slept_min[night]) / 60)
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
    return BuildInput(
        items=list(snapshot.items),
        now_utc=snapshot.now_utc,
        settings=snapshot.settings,
        dependencies=[Dependency(a, b, fraction, lag) for a, b, fraction, lag in snapshot.dependencies],
        pins=pins,
        areas=snapshot.areas,
        progress_units={k: v // UNIT_MIN for k, v in done.items()},
        progress_today_units={k: v // UNIT_MIN for k, v in on_today.items()},
        current=current,
        day_scales=day_scales(snapshot),
        minimize_changes_scale=stability,
        hold=timer_hold(snapshot),
        day_overrides=snapshot.day_overrides,
        end_utc=end_utc,
        multipliers=snapshot.multipliers,
        debt_hours=debt_hours(snapshot),
        routine_min=snapshot.sleep.routine_min if snapshot.sleep else {},
        woke_utc=snapshot.sleep.woke_utc if snapshot.sleep else None,
        ready_today=bool(snapshot.sleep and snapshot.sleep.ready),
    )
