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
from friday.commands.settings import write_setting as save_setting
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
        done=bool(kv_get(ctx.conn, "setup_done", False, ctx.user_id)),
        toured=bool(kv_get(ctx.conn, "tour_offered", False, ctx.user_id)),
        answers=answers(ctx, events),
        events=events,
    )


@command("tour_offered", logged=False)  # a flag of the app's, nothing of yours to undo
def tour_offered(ctx: Ctx, inp: Empty) -> Changed:
    """The tour was offered: it opens by itself once, after setup, and never again on its own (31 Oct: "make sure
    that when the initialization screen gets merged into the main, that it doesn't run every time"); the ? opens it
    whenever you want it."""
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "tour_offered"}, {"value": "true"})
    return Changed(message="Offered")


@command("setup_save", affects_plan=True)
def setup_save(ctx: Ctx, inp: SetupInput) -> Changed:
    """Your answers to Setup's questions: sleep, load, focus, free time, finishing early, calendars and the brief.
    Only what you changed is written (the audit, 31 Oct: going through again, or Skip, wrote Monday's sleep and cap
    over every day and switched rules you'd turned off back on): an answer the same as the question showed leaves
    what it's about as it is, a day that differs from the rest included."""
    owned = set(kv_get(ctx.conn, "config_keys", [], ctx.user_id) or [])

    def write_setting(ctx: Ctx, key: str, value: Any) -> None:  # one friday.toml sets is changed there only
        if key not in owned:
            save_setting(ctx, key, value)

    before = answers(ctx, {})
    changed = {k for k, v in inp.model_dump().items() if k != "calendars" and differs(before.get(k), v)}
    sleep = ctx.settings["sleep"] or {}
    if not sleep or changed & {"wake", "bedtime", "weekend_wake", "weekend_bedtime"}:
        night = lambda d: sleep.get(d) or SleepDay(wake="07:30", bedtime="23:30", margin_min=60)  # noqa: E731
        weekend_morning, weekend_night = (lambda d: d in WEEKEND_MORNINGS), (lambda d: d in WEEKEND_NIGHTS)
        write_setting(
            ctx,
            "sleep",
            {
                d: {
                    "wake": (inp.weekend_wake if weekend_morning(d) else inp.wake)
                    if not sleep or ("weekend_wake" if weekend_morning(d) else "wake") in changed
                    else night(d).wake,
                    "bedtime": (inp.weekend_bedtime if weekend_night(d) else inp.bedtime)
                    if not sleep or ("weekend_bedtime" if weekend_night(d) else "bedtime") in changed
                    else night(d).bedtime,
                    "margin_min": night(d).margin_min,
                }
                for d in DAYS
            },
        )
    if changed & {"most_hours", "normal_hours"}:
        write_setting(ctx, "daily_cap", dict.fromkeys(DAYS, max(inp.most_hours, inp.normal_hours)))
    rules = list(ctx.settings["rules"])
    if "normal_hours" in changed:
        rules = tuned(rules, "daily_load", {"threshold": hours(inp.normal_hours)})
    if "focus_hours" in changed:
        rules = tuned(rules, "deep_run", {"threshold": hours(inp.focus_hours)})
    if changed & {"evening_free", "evening_from"}:
        rules = tuned(
            rules,
            "weekday_evenings",
            {"start": inp.evening_from, "free": hours(inp.evening_free)},
            inp.evening_free > 0,
        )
    if "weekend_free" in changed:
        rules = tuned(rules, "weekends", {"free": hours(inp.weekend_free)}, inp.weekend_free > 0)
    if "finish_early_days" in changed:
        rules = tuned(rules, "finish_early", {"days": inp.finish_early_days}, inp.finish_early_days > 0)
    if rules != list(ctx.settings["rules"]):
        write_setting(ctx, "rules", to_json("rules", tuple(rules)))
    if inp.calendars:
        look, busy = ctx.settings["calendar_look"], ctx.settings["busy"]
        named = {c.name for c in inp.calendars}
        hidden = [n for n in look.toolbar if n not in named] + [c.name for c in inp.calendars if not c.shown]
        write_setting(ctx, "calendar_look", {**to_json("calendar_look", look), "toolbar": hidden})
        counted = {**busy.calendars, **{c.name: c.busy for c in inp.calendars}}
        write_setting(ctx, "busy", {**to_json("busy", busy), "calendars": counted})
    if "brief" in changed:
        write_setting(ctx, "notify", {**to_json("notify", ctx.settings["notify"]), "morning_brief": inp.brief})
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
        "brief": ctx.settings["notify"].morning_brief,
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


def differs(was: Any, now: Any) -> bool:
    """Whether an answer isn't the one the question showed (hours compared as numbers)."""
    if isinstance(was, (int, float)) and isinstance(now, (int, float)) and not isinstance(was, bool):
        return abs(was - now) > 1e-6
    return was != now


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
