"""Settings and paces (DESIGN §17): settings_set, pace, pace_save, pace_delete, day_override."""

import json
from datetime import date, timedelta
from typing import Any

from friday.api.commands import (
    Changed,
    DayOverrideInput,
    PaceDeleteInput,
    PaceInput,
    PaceOut,
    PaceSaveInput,
    SettingsSetInput,
)
from friday.commands.calendars import reread_calendars
from friday.commands.registry import Ctx, command
from friday.core.dates import read_date
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.pace import Dials, PacePeriod, adjust_dials, dials_on, pace_label, switch_pace
from friday.core.settings import SleepDay, check_hhmm, to_json, validate_value
from friday.planner.snapshot import pace_periods
from friday.planner.store import kv_get, settings_version


def write_setting(ctx: Ctx, key: str, value: Any) -> Any:
    try:
        parsed = validate_value(key, value)
    except ValueError as error:
        raise FieldError("value", str(error)) from error
    version = settings_version(ctx.conn, ctx.user_id) + 1
    ctx.db.upsert(
        "settings",
        {"user_id": ctx.user_id, "key": key},
        {"value": json.dumps(to_json(key, parsed)), "version": version, "updated_utc": ctx.now_text},
    )
    ctx.settings[key] = parsed
    if key in RESHAPING:
        loosen_next_replan(ctx, 0.0)
    return parsed


@command("settings_set", affects_plan=True)
def settings_set(ctx: Ctx, inp: SettingsSetInput) -> Changed:
    """Change one settings key (validated, versioned, undoable); a key `friday.toml` sets is changed there only."""
    if ctx.actor != "config" and inp.key in kv_get(ctx.conn, "config_keys", [], ctx.user_id):
        raise FieldError("key", f"{inp.key} is set in friday.toml; change it there")
    all_day = ctx.settings["gcal"].include_all_day
    value = inp.value
    if inp.key == "event_kinds" and isinstance(value, dict):
        # Only the kinds given change ("15 minutes after classes" leaves meetings and exams as they were).
        value = {k: v.model_dump() for k, v in ctx.settings["event_kinds"].items()} | value
    if inp.key == "pace" and isinstance(value, dict):
        value = ctx.settings["pace"].model_dump() | value  # "easier on Saturdays" keeps the default pace
    write_setting(ctx, inp.key, value)
    if inp.key == "gcal" and validate_value("gcal", inp.value).include_all_day != all_day:
        reread_calendars(ctx)  # events seen before would otherwise keep the old reading
    return Changed(message=f"Saved {inp.key}")


# Keys that change what a good plan is: the next replan follows them instead of holding the old plan.
RESHAPING = {"rules", "sleep", "daily_cap", "energy_map", "kind_order", "event_kinds"}


def loosen_next_replan(ctx: Ctx, stability: float) -> None:
    """How much the next replan holds today's plan (`minimize_changes`' scale); it applies once."""
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "next_stability"}, {"value": json.dumps(stability)})


def dials_now(ctx: Ctx, periods: list[PacePeriod]) -> Dials:
    pace = ctx.settings["pace"]
    return dials_on(ctx.today, periods, ctx.settings["paces"], pace.default, pace.weekly)


def end_date(ctx: Ctx, inp: PaceInput) -> date | None:
    if inp.for_days is not None:
        if inp.for_days < 1:
            raise FieldError("for_days", "must be at least 1")
        return ctx.today + timedelta(days=inp.for_days - 1)
    if inp.until is not None:
        found = read_date(inp.until.lower().split(), 0, ctx.today)
        if found is None:
            raise FieldError("until", f"{inp.until!r} isn't a date")
        return found[0]
    return None


def given_dials(inp: PaceInput | PaceSaveInput) -> dict[str, float | None]:
    return {"capacity": inp.capacity, "rest": inp.rest, "spread": inp.spread, "growth": inp.growth}


@command("pace", affects_plan=True)
def pace(ctx: Ctx, inp: PaceInput) -> PaceOut:
    """Switch to a saved pace, or set dials directly, from today for a while or until changed (§17.6)."""
    periods = list(pace_periods(ctx.conn, ctx.user_id))
    paces = ctx.settings["paces"]
    if inp.name is not None:
        name = next((p for p in paces if p.lower() == inp.name.lower()), None)
        if name is None:
            raise FieldError("name", f"no pace called {inp.name}; saved: {', '.join(paces)}")
        base = paces[name]
    else:
        base = dials_now(ctx, periods)
    try:
        dials = adjust_dials(base, **given_dials(inp))
    except ValueError as error:
        raise FieldError("dials", str(error)) from error
    label = pace_label(dials, paces)
    until = end_date(ctx, inp)
    default = ctx.settings["pace"].default
    after = switch_pace(periods, ctx.today, dials, None if label == "Custom" else label, until, default)
    write_periods(ctx, after)
    loosen_next_replan(ctx, ctx.settings["pace"].switch_stability)
    return PaceOut(
        label=label,
        dials=dials.model_dump(),
        start_date=ctx.today.isoformat(),
        end_date=until.isoformat() if until else None,
        message=pace_message(label, until, default),
    )


def pace_message(label: str, until: date | None, default: str) -> str:
    if label == default:
        return f"{label} pace from today."
    if until is None:
        return f"{label} pace from today until you change it."
    return f"{label} pace, today through {until:%a %b} {until.day}. Then back to {default}."


def write_periods(ctx: Ctx, after: list[PacePeriod]) -> None:
    """Make the stored periods equal `after`: matching rows keep their id (with a new end date if it moved),
    rows with no match are deleted, and the periods left over are inserted."""
    left = list(after)
    for row in rows(ctx.conn, "SELECT * FROM pace_periods WHERE user_id = ?", [ctx.user_id]):
        match = next((p for p in left if same_period(p, row)), None)
        if match is None:
            ctx.db.delete("pace_periods", {"id": row["id"]})
            continue
        left.remove(match)
        ending = match.end_date.isoformat() if match.end_date else None
        ctx.db.update("pace_periods", {"id": row["id"]}, {"end_date": ending})
    for period in left:
        ctx.db.insert(
            "pace_periods",
            {
                "pace_name": period.pace_name,
                "dials": period.dials.model_dump_json(),
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat() if period.end_date else None,
                "created_utc": ctx.now_text,
            },
        )


def same_period(period: PacePeriod, row: dict[str, Any]) -> bool:
    return (
        period.start_date.isoformat() == row["start_date"]
        and period.pace_name == row["pace_name"]
        and period.dials == Dials.model_validate(json.loads(row["dials"]))
    )


@command("pace_save", affects_plan=True)
def pace_save(ctx: Ctx, inp: PaceSaveInput) -> Changed:
    """Create or change a saved pace; dials left out keep the pace's values, or the dials in effect now."""
    paces = dict(ctx.settings["paces"])
    name = next((p for p in paces if p.lower() == inp.name.lower()), inp.name)
    base = paces.get(name) or dials_now(ctx, list(pace_periods(ctx.conn, ctx.user_id)))
    try:
        paces[name] = adjust_dials(base, **given_dials(inp))
    except ValueError as error:
        raise FieldError("dials", str(error)) from error
    write_setting(ctx, "paces", {k: v.model_dump() for k, v in paces.items()})
    d = paces[name]
    return Changed(
        message=f"Saved pace {name}: capacity {d.capacity:g} · rest {d.rest:g} · spread {d.spread:g} · "
        f"growth {d.growth:g}"
    )


@command("pace_delete")
def pace_delete(ctx: Ctx, inp: PaceDeleteInput) -> Changed:
    """Delete a saved pace (not the default, nor the one in use)."""
    paces = dict(ctx.settings["paces"])
    name = next((p for p in paces if p.lower() == inp.name.lower()), None)
    if name is None:
        raise FieldError("name", f"no pace called {inp.name}")
    if name == ctx.settings["pace"].default:
        raise FieldError("name", f"{name} is the default pace")
    periods = list(pace_periods(ctx.conn, ctx.user_id))
    if pace_label(dials_now(ctx, periods), paces) == name:
        raise FieldError("name", f"{name} is in use now")
    del paces[name]
    write_setting(ctx, "paces", {k: v.model_dump() for k, v in paces.items()})
    return Changed(message=f"Deleted pace {name}")


@command("day_override", affects_plan=True)
def day_override(ctx: Ctx, inp: DayOverrideInput) -> Changed:
    """One date's bedtime, wake, sleep margin or daily cap, over the weekday settings; what you leave out stays."""
    try:
        day = date.fromisoformat(inp.date)
        for name in ("bedtime", "wake"):
            if getattr(inp, name) is not None:
                check_hhmm(getattr(inp, name))
    except ValueError as error:
        raise FieldError("date", str(error)) from error
    if inp.margin_min is not None:
        SleepDay(bedtime="23:00", wake="07:00", margin_min=inp.margin_min)
    # Only the fields given (null clears one): Thursday's cap stays when its sleep margin is set later.
    fields = ("bedtime", "wake", "margin_min", "cap_hours")
    values = {name: getattr(inp, name) for name in fields if name in inp.model_fields_set}
    if values:
        ctx.db.upsert("day_overrides", {"user_id": ctx.user_id, "date": day.isoformat()}, values)
    return Changed(message=f"Set {day:%a %b} {day.day}")
