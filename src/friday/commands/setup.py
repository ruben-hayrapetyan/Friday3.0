"""Setup: the questions Friday asks when it first opens, so the defaults fit you rather than whoever they were made
for. Each answer sets what it's about: sleep, the daily load and limit, the longest focused stretch, the free time
kept on evenings and weekends, how early work is finished, which calendars are shown and count as busy, and the
morning brief. The questions start from what Friday does now, so answering them again changes only what you change."""

from collections import Counter
from typing import Any

from friday.api.commands import Changed, SetupInput
from friday.api.types import Empty
from friday.api.views import SetupOut
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.calendars import calendar_counts
from friday.core.dates import parse_duration
from friday.core.db import rows
from friday.core.settings import REFERENCE_RULES, RuleSpec, SleepDay, to_json
from friday.core.time import MINUTES_PER_DAY, format_utc
from friday.planner.store import event_links, kv_get

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")
WEEKEND_MORNINGS = ("sat", "sun")
WEEKEND_NIGHTS = ("fri", "sat")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
AHEAD_DAYS = 14


@query("setup")
def setup(ctx: Ctx, inp: Empty) -> SetupOut:
    """Setup's questions, answered with what Friday does now."""
    events = upcoming(ctx)
    return SetupOut(
        done=bool(kv_get(ctx.conn, "setup_done", False, ctx.user_id)), answers=answers(ctx, events), events=events
    )


@command("setup_save", affects_plan=True)
def setup_save(ctx: Ctx, inp: SetupInput) -> Changed:
    """Your answers to Setup's questions: sleep, load, focus, free time, finishing early, calendars and the brief."""
    sleep = ctx.settings["sleep"] or {}
    margin = {d: (sleep[d].margin_min if d in sleep else 60) for d in DAYS}
    write_setting(
        ctx,
        "sleep",
        {
            d: {
                "wake": inp.weekend_wake if d in WEEKEND_MORNINGS else inp.wake,
                "bedtime": inp.weekend_bedtime if d in WEEKEND_NIGHTS else inp.bedtime,
                "margin_min": margin[d],
            }
            for d in DAYS
        },
    )
    write_setting(ctx, "daily_cap", dict.fromkeys(DAYS, max(inp.most_hours, inp.normal_hours)))
    rules = list(ctx.settings["rules"])
    rules = tuned(rules, "daily_load", {"threshold": hours(inp.normal_hours)})
    rules = tuned(rules, "deep_run", {"threshold": hours(inp.focus_hours)})
    rules = tuned(
        rules, "weekday_evenings", {"start": inp.evening_from, "free": hours(inp.evening_free)}, inp.evening_free > 0
    )
    rules = tuned(rules, "weekends", {"free": hours(inp.weekend_free)}, inp.weekend_free > 0)
    rules = tuned(rules, "finish_early", {"days": inp.finish_early_days}, inp.finish_early_days > 0)
    write_setting(ctx, "rules", to_json("rules", tuple(rules)))
    if inp.calendars:
        look, busy = ctx.settings["calendar_look"], ctx.settings["busy"]
        named = {c.name for c in inp.calendars}
        hidden = [n for n in look.toolbar if n not in named] + [c.name for c in inp.calendars if not c.shown]
        write_setting(ctx, "calendar_look", {**to_json("calendar_look", look), "toolbar": hidden})
        counted = {**busy.calendars, **{c.name: c.busy for c in inp.calendars}}
        write_setting(ctx, "busy", {**to_json("busy", busy), "calendars": counted})
    notify = to_json("notify", ctx.settings["notify"])
    write_setting(ctx, "notify", {**notify, "types": {**notify["types"], "morning_brief": inp.brief}})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "setup_done"}, {"value": "true"})
    return Changed(message="Friday is set up the way you said")


def answers(ctx: Ctx, events: dict[str, int]) -> dict[str, Any]:
    """SetupInput's fields as Friday plans now: a rule switched off reads as none of it."""
    sleep = ctx.settings["sleep"] or {}

    def night(day: str) -> SleepDay:
        return sleep.get(day) or SleepDay(wake="07:30", bedtime="23:30", margin_min=60)

    rules = {r.name: r for r in ctx.settings["rules"]}

    def param(name: str, key: str, default: Any) -> Any:
        rule = rules.get(name)
        return rule.params.get(key, default) if rule and rule.enabled else None

    busy, look = ctx.settings["busy"], ctx.settings["calendar_look"]
    names = sorted(set(events) | read_calendars(ctx), key=lambda n: (-events.get(n, 0), n.lower()))
    return {
        "wake": night("mon").wake,
        "bedtime": night("mon").bedtime,
        "weekend_wake": night("sat").wake,
        "weekend_bedtime": night("fri").bedtime,
        "normal_hours": in_hours(param("daily_load", "threshold", "8h")) or ctx.settings["daily_cap"]["mon"],
        "most_hours": ctx.settings["daily_cap"]["mon"],
        "focus_hours": in_hours(param("deep_run", "threshold", "3h")) or 3.0,
        "evening_free": in_hours(param("weekday_evenings", "free", "2h")) or 0.0,
        "evening_from": param("weekday_evenings", "start", "18:00") or "18:00",
        "weekend_free": in_hours(param("weekends", "free", "4h")) or 0.0,
        "finish_early_days": param("finish_early", "days", 1) or 0,
        "brief": ctx.settings["notify"].types.get("morning_brief", True),
        "calendars": [{"name": n, "shown": n not in look.toolbar, "busy": calendar_counts(n, busy)} for n in names],
    }


def tuned(rules: list[RuleSpec], name: str, params: dict[str, Any], enabled: bool = True) -> list[RuleSpec]:
    """The rule with these params and switched on or off; a built-in one you'd removed comes back to take them."""
    if not any(r.name == name for r in rules):
        reference = next((r for r in REFERENCE_RULES if r.name == name), None)
        if reference is None or not enabled:
            return rules
        rules = [*rules, reference]
    return [
        r.model_copy(update={"params": {**r.params, **params} if enabled else r.params, "enabled": enabled})
        if r.name == name
        else r
        for r in rules
    ]


def hours(value: float) -> str:
    return f"{value:g}h"


def in_hours(text: Any) -> float | None:
    """`3h`, `1.5h`, `90m` or `1h30m` in hours; None when there's nothing to read."""
    minutes = parse_duration(text) if isinstance(text, str) else None
    return round(minutes / 60, 2) if minutes else None


def upcoming(ctx: Ctx) -> dict[str, int]:
    """Each calendar's events in the next two weeks."""
    links = event_links(ctx.conn, ctx.user_id)
    found = rows(
        ctx.conn,
        "SELECT id FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' AND start_utc >= ? "
        "AND start_utc < ?",
        [ctx.user_id, format_utc(ctx.now_utc), format_utc(ctx.now_utc + AHEAD_DAYS * MINUTES_PER_DAY)],
    )
    return dict(Counter(links[r["id"]].calendar for r in found if r["id"] in links))


def read_calendars(ctx: Ctx) -> set[str]:
    found = rows(
        ctx.conn,
        "SELECT name FROM sources WHERE user_id = ? AND kind IN ('gcal', 'mac') AND enabled = 1",
        [ctx.user_id],
    )
    return {r["name"] for r in found}
