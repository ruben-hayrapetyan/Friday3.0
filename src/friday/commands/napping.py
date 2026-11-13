"""Naps (Sleep & meals → Sleep, with sleep tracking on; 29 Oct: "add functionality for adding naps"): "Taking a nap"
and "I'm up" from the Now bar, Search or Sleep & meals, a nap logged after the fact, put right or taken back.

While you nap the plan keeps the time clear for as long as you usually nap (`planner/snapshot.away`); a nap counts
against the sleep the night before fell short of (`planner/prepare.debt_hours`). A tap for the night ("Going to bed",
"I'm up") ends a nap left running, and "I'm up" tapped hours later counts your usual nap, not the hours between.
"""

import sqlite3
from datetime import date, timedelta

from friday.api.commands import Changed, NapEditInput, NapEndInput, NapLogInput, NapRef, NapStartInput
from friday.api.views import NapOut
from friday.commands.registry import Ctx, command
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import ampm, format_local, format_utc, parse_utc, planning_date, to_local, to_zoned
from friday.learn.sleep import NAP_LONGEST_MIN, NAP_USUAL_MIN, Nap, usual_nap

FORGOT_MIN = 3 * 60  # "I'm up" this long after lying down was a tap forgotten, not a three-hour nap
LEARN_DAYS = 56  # the last eight weeks teach how long you nap
SHOWN_DAYS = 14


def tracking(ctx: Ctx) -> None:
    if not ctx.settings["sleep_tracking"].on:
        raise FieldError("at", "sleep tracking is off; turn it on in Settings → Schedule")


def moment_of(ctx: Ctx, local: str | None, field: str = "at") -> int:
    moment = parse_utc(ctx.utc(local, field)) if local else ctx.now_utc
    if moment > ctx.now_utc + 5:
        raise FieldError(field, "that's later than now")
    return moment


def said(ctx: Ctx, moment: int) -> str:
    return ampm(to_local(moment, ctx.tz))


def napping(conn: sqlite3.Connection, user_id: int) -> dict | None:
    """The nap you're taking: one with no end yet."""
    return one(conn, "SELECT * FROM naps WHERE user_id = ? AND end_utc IS NULL ORDER BY id DESC LIMIT 1", [user_id])


def usual_min(conn: sqlite3.Connection, now_utc: int, user_id: int) -> int | None:
    """How long you usually nap, from the last eight weeks; None until there are three naps."""
    found = rows(
        conn,
        "SELECT start_utc, end_utc FROM naps WHERE user_id = ? AND end_utc IS NOT NULL AND start_utc >= ?",
        [user_id, format_utc(now_utc - LEARN_DAYS * 1440)],
    )
    return usual_nap((parse_utc(r["end_utc"]) - parse_utc(r["start_utc"])) for r in found)


def usual(ctx: Ctx) -> int:
    return usual_min(ctx.conn, ctx.now_utc, ctx.user_id) or NAP_USUAL_MIN


def recorded(ctx: Ctx, days: int) -> list[Nap]:
    since = (ctx.today - timedelta(days=days)).isoformat()
    found = rows(
        ctx.conn, "SELECT * FROM naps WHERE user_id = ? AND date >= ? ORDER BY start_utc", [ctx.user_id, since]
    )
    local = lambda t: to_zoned(parse_utc(t), ctx.tz) if t else None  # noqa: E731  (zoned: real lengths, 12 Nov)
    return [Nap(r["id"], date.fromisoformat(r["date"]), local(r["start_utc"]), local(r["end_utc"])) for r in found]  # type: ignore[arg-type]


def nap_out(nap: Nap) -> NapOut:
    return NapOut(
        id=nap.id, date=nap.date.isoformat(), start=format_local(nap.start),
        end=format_local(nap.end) if nap.end else None, minutes=nap.minutes,
    )  # fmt: skip


def shown(ctx: Ctx) -> list[NapOut]:
    """The last two weeks of naps, newest first."""
    return [nap_out(n) for n in reversed(recorded(ctx, SHOWN_DAYS)) if n.end is not None]


def taking(ctx: Ctx) -> NapOut | None:
    found = napping(ctx.conn, ctx.user_id)
    if found is None:
        return None
    start = to_local(parse_utc(found["start_utc"]), ctx.tz)
    return NapOut(id=found["id"], date=found["date"], start=format_local(start))


def end_at(ctx: Ctx, nap: dict, end: int) -> int:
    """The nap ended at `end`, at most four hours on; its length in minutes."""
    start = parse_utc(nap["start_utc"])
    end = min(end, start + NAP_LONGEST_MIN)
    ctx.db.update("naps", {"id": nap["id"]}, {"end_utc": format_utc(end)})
    return end - start


def wake(ctx: Ctx, moment: int) -> None:
    """A tap for the night ends the nap you're taking: then, or at your usual length when it ran on for hours."""
    nap = napping(ctx.conn, ctx.user_id)
    if nap is None or parse_utc(nap["start_utc"]) >= moment:
        return
    start = parse_utc(nap["start_utc"])
    end_at(ctx, nap, moment if moment - start <= FORGOT_MIN else start + usual(ctx))


def clash(ctx: Ctx, start: int, end: int, but: int | None = None) -> None:
    """A nap can't overlap another."""
    found = rows(
        ctx.conn,
        "SELECT * FROM naps WHERE user_id = ? AND start_utc < ? AND coalesce(end_utc, ?) > ? AND id IS NOT ?",
        [ctx.user_id, format_utc(end), ctx.now_text, format_utc(start), but],
    )
    if found:
        raise FieldError("start", f"you were napping from {said(ctx, parse_utc(found[0]['start_utc']))} then")


def check(start: int, end: int) -> None:
    if not start < end <= start + NAP_LONGEST_MIN:
        raise FieldError("end", "a nap ends after it starts, within four hours")


@command("nap_start", affects_plan=True)
def nap_start(ctx: Ctx, inp: NapStartInput) -> Changed:
    """Taking a nap, now or since the time you give: the plan keeps the time clear for as long as you usually nap."""
    tracking(ctx)
    moment = moment_of(ctx, inp.at)
    before = napping(ctx.conn, ctx.user_id)
    if before is not None:
        if moment - parse_utc(before["start_utc"]) <= FORGOT_MIN:
            raise FieldError("at", f"you're napping since {said(ctx, parse_utc(before['start_utc']))}")
        wake(ctx, moment)  # one left running hours ago: your usual nap
    day = planning_date(moment, ctx.tz, ctx.day_start)
    ctx.db.insert("naps", {"date": day.isoformat(), "start_utc": format_utc(moment), "created_utc": ctx.now_text})
    return Changed(message=f"Napping since {said(ctx, moment)}")


@command("nap_end", affects_plan=True)
def nap_end(ctx: Ctx, inp: NapEndInput) -> Changed:
    """Up from your nap, now or at the time you give."""
    tracking(ctx)
    nap = napping(ctx.conn, ctx.user_id)
    if nap is None:
        raise FieldError("at", "you aren't napping")
    end, start = moment_of(ctx, inp.at), parse_utc(nap["start_utc"])
    if end <= start:
        raise FieldError("at", "that's before you lay down")
    if inp.at is None and end - start > FORGOT_MIN:
        length = end_at(ctx, nap, start + usual(ctx))
        return Changed(
            message=f"Nap: counted as your usual {length} min (I'm up came {(end - start) // 60} h "
            f"{(end - start) % 60} min after you lay down); change it in Sleep & meals"
        )
    if inp.at is not None:
        check(start, end)
    return Changed(message=f"Nap: {end_at(ctx, nap, end)} min")


@command("nap_log", affects_plan=True)
def nap_log(ctx: Ctx, inp: NapLogInput) -> Changed:
    """A nap you didn't tap, from when you lay down to when you got up."""
    tracking(ctx)
    start, end = moment_of(ctx, inp.start, "start"), moment_of(ctx, inp.end, "end")
    check(start, end)
    clash(ctx, start, end)
    day = planning_date(start, ctx.tz, ctx.day_start)
    ctx.db.insert(
        "naps",
        {"date": day.isoformat(), "start_utc": format_utc(start), "end_utc": format_utc(end),
         "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"Logged a nap, {said(ctx, start)} to {said(ctx, end)}")


def nap_row(ctx: Ctx, nap_id: int) -> dict:
    found = one(ctx.conn, "SELECT * FROM naps WHERE user_id = ? AND id = ?", [ctx.user_id, nap_id])
    if found is None:
        raise FieldError("id", f"no nap {nap_id}")
    return found


@command("nap_edit", affects_plan=True)
def nap_edit(ctx: Ctx, inp: NapEditInput) -> Changed:
    """A nap's times put right; an end given to the nap you're taking ends it."""
    nap = nap_row(ctx, inp.id)
    start = moment_of(ctx, inp.start, "start") if inp.start else parse_utc(nap["start_utc"])
    end = moment_of(ctx, inp.end, "end") if inp.end else (parse_utc(nap["end_utc"]) if nap["end_utc"] else None)
    if end is not None:
        check(start, end)
    clash(ctx, start, end if end is not None else ctx.now_utc, but=inp.id)
    changes = {"start_utc": format_utc(start), "date": planning_date(start, ctx.tz, ctx.day_start).isoformat()}
    ctx.db.update("naps", {"id": inp.id}, changes | ({"end_utc": format_utc(end)} if end is not None else {}))
    return Changed(message=f"Nap now {said(ctx, start)}{f' to {said(ctx, end)}' if end is not None else ''}")


@command("nap_remove", affects_plan=True)
def nap_remove(ctx: Ctx, inp: NapRef) -> Changed:
    """A nap you didn't mean to record."""
    nap = nap_row(ctx, inp.id)
    ctx.db.delete("naps", {"id": inp.id})
    return Changed(message=f"Removed the nap at {said(ctx, parse_utc(nap['start_utc']))}")
