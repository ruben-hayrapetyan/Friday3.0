"""Tracking your sleep (Settings → Schedule, off until you turn it on): one tap each for "Done with work", "Going to
bed", "I'm up" and "Ready to work", a correction for a tap at the wrong time, and what Friday makes of them
(`learn/sleep.py`): the last two weeks of nights, your morning routine and evening wind-down, and learned bedtimes and
wake times offered as a change to your schedule. Naps are `commands/napping.py`; the sleep view shows them too.
"""

import json
from datetime import datetime, timedelta

from friday.api.commands import Changed, SleepMarkEditInput, SleepMarkInput, SleepMarkRef, SleepSkipInput
from friday.api.types import Empty
from friday.api.views import SleepAsk, SleepChangeOut, SleepNightOut, SleepOut
from friday.commands.conflicts import minutes, short_nights
from friday.commands.napping import shown as naps_shown
from friday.commands.napping import taking, usual_min, wake
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.rule_text import days_spoken
from friday.core.time import ampm, format_local, format_utc, parse_utc, to_local, to_zoned
from friday.learn.sleep import WEEKDAYS, Mark, Night, changes, evening_of, learn, nights_from
from friday.planner.build import night_times
from friday.planner.snapshot import day_overrides
from friday.planner.store import kv_get

SHOWN_DAYS = 14
LEARN_DAYS = 56  # the last eight weeks teach the times
SAID = {"done": "Done with work", "bed": "Good night", "up": "Good morning", "ready": "Ready to work"}
DONE_FROM_H = 4  # "Done with work" is offered from this many hours before your bedtime


def tracking(ctx: Ctx) -> None:
    if not ctx.settings["sleep_tracking"].on:
        raise FieldError("kind", "sleep tracking is off; turn it on in Settings → Schedule")


def at_utc(ctx: Ctx, local: str | None) -> int:
    moment = parse_utc(ctx.utc(local, "at")) if local else ctx.now_utc
    if moment > ctx.now_utc + 5:
        raise FieldError("at", "that's later than now")
    return moment


@command("sleep_mark", affects_plan=True)
def sleep_mark(ctx: Ctx, inp: SleepMarkInput) -> Changed:
    """Done with work, going to bed, up, or ready to work: now, or at the time you give."""
    tracking(ctx)
    moment = at_utc(ctx, inp.at)
    wake(ctx, moment)  # a nap left running ends
    ctx.db.insert("sleep_marks", {"kind": inp.kind, "at_utc": format_utc(moment), "created_utc": ctx.now_text})
    return Changed(message=f"{SAID[inp.kind]}: {ampm(to_local(moment, ctx.tz))}")


@command("sleep_mark_edit", affects_plan=True)
def sleep_mark_edit(ctx: Ctx, inp: SleepMarkEditInput) -> Changed:
    """A tap at the wrong time, moved to the right one."""
    found = mark_row(ctx, inp.id)
    moment = at_utc(ctx, inp.at)
    ctx.db.update("sleep_marks", {"id": inp.id}, {"at_utc": format_utc(moment)})
    return Changed(message=f"{SAID[found['kind']]} moved to {ampm(to_local(moment, ctx.tz))}")


@command("sleep_mark_remove", affects_plan=True)
def sleep_mark_remove(ctx: Ctx, inp: SleepMarkRef) -> Changed:
    """A tap you didn't mean."""
    found = mark_row(ctx, inp.id)
    ctx.db.delete("sleep_marks", {"id": inp.id})
    return Changed(
        message=f"Removed {SAID[found['kind']].lower()} at {ampm(to_local(parse_utc(found['at_utc']), ctx.tz))}"
    )


@command("sleep_skip")
def sleep_skip(ctx: Ctx, inp: SleepSkipInput) -> Changed:
    """A tap you don't remember: the review stops asking for it."""
    skipped = sorted(set(kv_get(ctx.conn, "sleep_skipped", [], ctx.user_id)) | {f"{inp.date}:{inp.kind}"})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sleep_skipped"}, {"value": json.dumps(skipped)})
    return Changed(message="Skipped")


ASKED = {
    "up": "When did you get up?",
    "ready": "When were you ready to work?",
    "done": "When did you stop working for the night?",
    "bed": "When did you go to bed?",
}


def missing(ctx: Ctx, day) -> list[SleepAsk]:
    """The taps a reviewed day is missing: that morning's up and ready, and its night's done with work and bedtime
    once the night is over; not ones you skipped. Each starts from your usual time."""
    if not ctx.settings["sleep_tracking"].on or ctx.settings["sleep"] is None or day > ctx.today:
        return []
    overrides = day_overrides(ctx.conn, ctx.user_id)
    nights = recorded(ctx, (ctx.today - day).days + 3)
    skipped = set(kv_get(ctx.conn, "sleep_skipped", [], ctx.user_id))
    last_night, tonight = nights.get(day - timedelta(days=1)), nights.get(day)
    _, wake, _ = night_times(ctx.settings, overrides, day - timedelta(days=1), ctx.tz, ctx.day_start)
    bedtime, _, _ = night_times(ctx.settings, overrides, day, ctx.tz, ctx.day_start)
    up = last_night.up.at if last_night and last_night.up else to_local(wake, ctx.tz)
    learned = learn(nights.values(), ctx.settings["sleep_tracking"].min_nights)
    bed = tonight.bed.at if tonight and tonight.bed else to_local(bedtime, ctx.tz)
    usual = {
        "up": to_local(wake, ctx.tz),
        "ready": up + timedelta(minutes=learned.routine_min.get(WEEKDAYS[day.weekday()], 60)),
        "done": bed - timedelta(minutes=learned.wind_down_min.get(WEEKDAYS[day.weekday()], 60)),
        "bed": to_local(bedtime, ctx.tz),
    }
    over = day >= ctx.today  # tonight isn't over yet
    has = {
        "up": bool(last_night and last_night.up),
        "ready": bool(last_night and last_night.ready_at),
        "done": bool(tonight and tonight.done_at) or over,
        "bed": bool(tonight and tonight.bed) or over,
    }
    return [
        SleepAsk(kind=kind, date=day.isoformat(), at=format_local(usual[kind]), question=ASKED[kind])  # type: ignore[arg-type]
        for kind in ("up", "ready", "done", "bed")
        if not has[kind] and f"{day.isoformat()}:{kind}" not in skipped
    ]


def mark_row(ctx: Ctx, mark_id: int) -> dict:
    found = one(ctx.conn, "SELECT * FROM sleep_marks WHERE user_id = ? AND id = ?", [ctx.user_id, mark_id])
    if found is None:
        raise FieldError("id", f"no sleep mark {mark_id}")
    return found


def recorded(ctx: Ctx, days: int) -> dict:
    """The nights of the last `days`, by their evening."""
    since = format_utc(ctx.now_utc - days * 1440)
    marks = [
        Mark(r["id"], r["kind"], to_zoned(parse_utc(r["at_utc"]), ctx.tz))
        for r in rows(
            ctx.conn,
            "SELECT * FROM sleep_marks WHERE user_id = ? AND at_utc >= ? ORDER BY at_utc",
            [ctx.user_id, since],
        )
    ]
    timed = rows(
        ctx.conn,
        "SELECT start_utc, end_utc FROM progress WHERE user_id = ? AND source = 'timer' AND start_utc >= ?",
        [ctx.user_id, since],
    )
    starts = [to_zoned(parse_utc(r["start_utc"]), ctx.tz) for r in timed]
    ends = [to_zoned(parse_utc(r["end_utc"]), ctx.tz) for r in timed if r["end_utc"]]
    return nights_from(marks, starts, ctx.day_start, ends)


def planned_min(ctx: Ctx, overrides: dict, evening) -> int:
    bedtime, wake, _ = night_times(ctx.settings, overrides, evening, ctx.tz, ctx.day_start)
    return wake - bedtime


@query("sleep")
def sleep(ctx: Ctx, inp: Empty) -> SleepOut:
    """Your nights, routines and the times Friday has learned, with the tap to offer now.

    Your morning routine and evening wind-down, learned bedtimes and wake times, and the tap that fits: "I'm up" in
    the morning, "Ready to work" after it, "Done with work", then "Going to bed"."""
    tracking_on = ctx.settings["sleep_tracking"]
    if not tracking_on.on or ctx.settings["sleep"] is None:
        return SleepOut(on=False, min_nights=tracking_on.min_nights)
    overrides = day_overrides(ctx.conn, ctx.user_id)
    nights = recorded(ctx, LEARN_DAYS)
    learned = learn(nights.values(), tracking_on.min_nights)
    found = changes(learned, ctx.settings["sleep"])
    suggested = None
    against: list[str] = []
    if found:
        sleep_now = {d: s.model_dump() for d, s in ctx.settings["sleep"].items()}
        for change in found:
            for day in change.days:
                sleep_now[day][change.field] = change.learned
        suggested = sleep_now
        # Checked against your sleep rule before you take them (29 Oct: learned times must not quietly break a rule)
        for (bed, wake, down, hours, _), days in short_nights(
            sleep_now, ctx.settings["rules"], learned.wind_down_min
        ).items():
            asleep = (minutes(wake) - minutes(bed)) % (24 * 60) - down
            against.append(
                f"{days_spoken(tuple(days))}: bed at {ampm(bed)} and up at {ampm(wake)} leave {asleep // 60} h "
                f"{asleep % 60:02d} m asleep{' after winding down' if down else ''}, under your {hours:g} h rule"
            )
    now = to_local(ctx.now_utc, ctx.tz)
    shown = sorted(
        (n for n in nights.values() if n.date >= now.date() - timedelta(days=SHOWN_DAYS)),
        key=lambda n: n.date,
        reverse=True,
    )
    full = [n.slept_min for n in shown if n.slept_min is not None][:7]
    this_morning = nights.get(now.date() - timedelta(days=1))
    tonight = nights.get(evening_of(now, ctx.day_start))
    nap = taking(ctx)
    return SleepOut(
        on=True,
        next=None if nap else offer(ctx, now, nights, overrides, tracking_on.morning_hours),
        up=format_local(this_morning.up.at) if this_morning and this_morning.up else None,
        ready=format_local(this_morning.ready_at) if this_morning and this_morning.ready_at else None,
        nights=[night_out(ctx, overrides, n) for n in shown],
        average_slept_min=round(sum(full) / len(full)) if full else None,
        routine_min=learned.routine_min,
        wind_down_min=learned.wind_down_min,
        done=format_local(tonight.done.at) if tonight and tonight.done and not tonight.bed else None,
        changes=[SleepChangeOut(days=list(c.days), field=c.field, now=c.now, learned=c.learned) for c in found],  # type: ignore[arg-type]
        suggested=suggested,
        against=against,
        recorded_nights=learned.nights,
        min_nights=tracking_on.min_nights,
        napping=nap,
        naps=naps_shown(ctx),
        usual_nap_min=usual_min(ctx.conn, ctx.now_utc, ctx.user_id),
    )


def offer(ctx: Ctx, now: datetime, nights: dict, overrides: dict, morning_hours: float) -> str | None:
    """The tap that fits now: up in the morning until it's tapped, ready for a few hours after; in the evening done
    with work from four hours before your bedtime (not while a timer runs), then bed once you're done, or from three
    hours before bedtime if you never said, until the day starts."""
    morning = nights.get(now.date() - timedelta(days=1))
    up = morning.up if morning else None
    if up is None and ctx.day_start <= now.hour * 60 + now.minute < 15 * 60:
        return "up"
    if (
        up is not None
        and morning.ready_at is None
        and now < up.at.replace(tzinfo=None) + timedelta(hours=morning_hours)
    ):  # type: ignore[union-attr]
        return "ready"
    evening = evening_of(now, ctx.day_start)
    tonight = nights.get(evening)
    bedtime, _, _ = night_times(ctx.settings, overrides, evening, ctx.tz, ctx.day_start)
    if tonight is not None and tonight.bed is not None:
        return None
    if tonight is not None and tonight.done is not None:
        return "bed"
    working = one(ctx.conn, "SELECT 1 FROM timer WHERE user_id = ?", [ctx.user_id]) is not None
    if not working and ctx.now_utc >= bedtime - DONE_FROM_H * 60:
        return "done"
    return None


def night_out(ctx: Ctx, overrides: dict, night: Night) -> SleepNightOut:
    local = lambda m: format_local(m.at) if m else None  # noqa: E731
    bedtime, wake, _ = night_times(ctx.settings, overrides, night.date, ctx.tz, ctx.day_start)
    return SleepNightOut(
        planned_bed=format_local(to_local(bedtime, ctx.tz)),
        planned_up=format_local(to_local(wake, ctx.tz)),
        date=night.date.isoformat(),
        bed=local(night.bed),
        up=local(night.up),
        ready=format_local(night.ready_at) if night.ready_at else None,
        ready_timed=night.ready is None and night.ready_from_timer is not None,
        bed_id=night.bed.id if night.bed else None,
        up_id=night.up.id if night.up else None,
        ready_id=night.ready.id if night.ready else None,
        slept_min=night.slept_min,
        planned_min=wake - bedtime,
        routine_min=night.routine_min,
        done=format_local(night.done_at) if night.done_at else None,
        done_timed=night.done is None and night.done_from_timer is not None,
        done_id=night.done.id if night.done else None,
        wind_down_min=night.wind_down_min,
    )
