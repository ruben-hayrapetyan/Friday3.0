"""Where what Friday learned disagrees with what you said, asked in the Inbox with which side Friday would change
(29 Oct: "make sure that there is guards against any of friday's learned behaviours and the rules contradicting (and
whether the rules need to be updated or the behaviours)").

Four kinds, each a decision with its answers, asked again only when what it's about changes:

- A rule you wrote, or one your answers set, that learning would weigh at under half or over double what you set
  (learn/guard.py holds it within that meanwhile). Friday would keep the rule: you said it; drags are a noisy hint.
- Your sleep times leaving less than your sleep rule's hours asleep once you've wound down. Friday would move your
  bedtime: the times were learned, the rule you wrote.
- "Wind down before bed" starting far from when you wind down: its time came from an older bedtime. Friday would
  move the rule.
- A meal your rule says is never skipped that you skip on most days. Friday would keep the rule (it's what you asked
  for) and lets you turn it off.

What the planner does on its own needs no question: your morning routine is never planned in, a night counts back
from an early event you go to (planner/build.py), and learning stays within half and double of what you said."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from friday.api.commands import Changed, ConflictInput
from friday.commands.registry import Ctx, command
from friday.commands.settings import write_setting
from friday.core.db import one
from friday.core.items import FieldError
from friday.core.rule_text import days_spoken
from friday.core.time import WEEKDAYS, ampm
from friday.learn import guard
from friday.planner.store import kv_get

ANSWERED = "conflicts_answered"  # kv: decision key → what it was about when answered
WIND_OFF_BY = 45  # minutes "Wind down before bed" may start away from when you wind down
SKIPPED_MOSTLY = 0.5  # a meal skipped this often is one you skip


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    detail: str
    recommended: bool = False


@dataclass(frozen=True)
class Clash:
    key: str
    title: str
    detail: str
    update: Literal["rule", "learned"]  # which side Friday would change
    about: str  # what it's about: asked again when this changes
    options: tuple[Option, ...]
    apply: Callable[[Ctx, str], str] = field(compare=False, repr=False)


def clashes(ctx: Ctx) -> list[Clash]:
    """Every disagreement between what Friday learned and what you said, not yet answered as it stands."""
    answered = kv_get(ctx.conn, ANSWERED, {}, ctx.user_id) or {}
    found = [*weights(ctx), *sleep_short(ctx), *wind_down(ctx), *meals(ctx)]
    return [c for c in found if answered.get(c.key) != c.about]


@command("conflict_resolve", affects_plan=True)
def conflict_resolve(ctx: Ctx, inp: ConflictInput) -> Changed:
    """Answer a disagreement between what Friday learned and a rule: the change the answer names, and it isn't asked
    again until what it's about changes."""
    found = next((c for c in clashes(ctx) if c.key == inp.key), None)
    if found is None:
        raise FieldError("key", "that's settled already")
    if inp.option not in {o.id for o in found.options}:
        raise FieldError("option", f"no answer {inp.option!r} to that")
    message = found.apply(ctx, inp.option)
    answered = kv_get(ctx.conn, ANSWERED, {}, ctx.user_id) or {}
    put(ctx, ANSWERED, answered | {found.key: found.about})
    return Changed(message=message)


# Learned weights against what you said.


def weights(ctx: Ctx) -> list[Clash]:
    row = one(
        ctx.conn,
        "SELECT theta FROM learned_profile WHERE user_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
        [ctx.user_id],
    )
    if row is None or not row["theta"]:
        return []
    held, freed = (
        kv_get(ctx.conn, guard.HELD, [], ctx.user_id) or [],
        kv_get(ctx.conn, guard.FREED, [], ctx.user_id) or [],
    )
    from friday.commands.rules import readings, strength_of, words  # noqa: PLC0415 (rules imports the planner)

    mine = readings(ctx)
    out = []
    for rule, theta in guard.outside(json.loads(row["theta"]), ctx.settings["rules"], held, freed):
        said = words(rule, mine)
        less = theta < guard.BAND[0]
        yours = str(rule.name).startswith("you:")
        how = f"{fraction(theta)} what {'you set' if yours else 'your answers set'}"
        options = [
            Option("keep", "Keep it as written", "Friday plans with it as you set it, and stops learning it.", True),
            Option(
                "free", "Weigh it as Friday learned", f"It counts {'less' if less else 'more'}, as your moves suggest."
            ),
        ]
        if yours and less and strength_of(rule, mine) == "Strongly":
            options.append(Option("prefer", "Make it a preference", "From Strongly to Prefer: it gives way sooner."))
        out.append(
            Clash(
                key=f"weight:{rule.name}",
                title=f"Your moves go {'against' if less else 'far beyond'} “{said}”",
                detail=f"From how you've moved things, Friday learned to weigh it at {how}. "
                f"Until you decide, it counts at {'half' if less else 'double'}.",
                update="learned",
                about=f"{rule.name}:{'low' if less else 'high'}",
                options=tuple(options),
                apply=lambda ctx_, option, name=rule.name: answer_weight(ctx_, name, option),
            )
        )
    return out


def answer_weight(ctx: Ctx, name: str, option: str) -> str:
    if option == "keep":
        put(ctx, guard.HELD, sorted({*(kv_get(ctx.conn, guard.HELD, [], ctx.user_id) or []), name}))
        return "Kept as written"
    if option == "free":
        put(ctx, guard.FREED, sorted({*(kv_get(ctx.conn, guard.FREED, [], ctx.user_id) or []), name}))
        return "Weighed as Friday learned"
    from friday.commands.rules import restrength  # noqa: PLC0415

    rules = [r.model_dump() for r in ctx.settings["rules"]]
    restrength(ctx, next(r for r in rules if r["name"] == name), "Prefer")
    write_setting(ctx, "rules", rules)
    return "Made a preference"


def fraction(theta: float) -> str:
    """0.033 → "about a thirtieth of"; 0.4 → "about half"; 3.2 → "about 3.2 times"."""
    if theta >= 1:
        return f"about {theta:.1f} times"
    n = round(1 / theta)
    return "about half" if n <= 2 else "about a third of" if n == 3 else f"about 1/{n} of"


# Your sleep times against your sleep rule.


def nights_learned(ctx: Ctx) -> tuple[dict[str, int], dict[str, int]]:
    """Learned wind-down (by evening) and routine (by morning), in minutes; empty without sleep tracking."""
    if not ctx.settings["sleep_tracking"].on or ctx.settings["sleep"] is None:
        return {}, {}
    from friday.commands.sleeping import LEARN_DAYS, recorded  # noqa: PLC0415
    from friday.learn.sleep import learn  # noqa: PLC0415

    learned = learn(recorded(ctx, LEARN_DAYS).values(), ctx.settings["sleep_tracking"].min_nights)
    return dict(learned.wind_down_min), dict(learned.routine_min)


def minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def clock(m: int) -> str:
    m %= 24 * 60
    return f"{m // 60:02d}:{m % 60:02d}"


def short_nights(sleep: dict[str, Any], rules: list[Any], wind: dict[str, int]) -> dict[tuple, list[str]]:
    """The evenings whose bedtime and the next morning's wake leave less than a sleep rule's hours asleep after
    winding down, grouped by (bedtime, wake, wind-down, hours, rule): what `sleep` would do against `rules`. `sleep`
    maps each weekday to its bedtime and wake ("HH:MM"), as settings or as a suggestion has them."""
    wants = [r for r in rules if r.type == "sleep_min" and r.enabled]
    groups: dict[tuple, list[str]] = {}
    for i, day in enumerate(WEEKDAYS):
        nights = [r for r in wants if not r.params.get("days") or day in r.params["days"]]
        if not nights:
            continue
        rule = max(nights, key=lambda r: float(r.params.get("hours", 7.0)))
        hours = float(rule.params.get("hours", 7.0))
        bed, wake = time_of(sleep[day], "bedtime"), time_of(sleep[WEEKDAYS[(i + 1) % 7]], "wake")
        down = wind.get(day, 0)
        if (minutes(wake) - minutes(bed)) % (24 * 60) - down < hours * 60:
            groups.setdefault((bed, wake, down, hours, rule.name), []).append(day)
    return groups


def time_of(night: Any, field_: str) -> str:
    return str(night[field_] if isinstance(night, dict) else getattr(night, field_))


def sleep_short(ctx: Ctx) -> list[Clash]:
    sleep = ctx.settings["sleep"]
    if sleep is None:
        return []
    wind, _ = nights_learned(ctx)
    groups = short_nights(sleep, ctx.settings["rules"], wind)
    out = []
    for (bed, wake, down, hours, name), days in groups.items():
        bedtime = clock(minutes(wake) - round(hours * 60) - down)
        asleep = (minutes(wake) - minutes(bed)) % (24 * 60) - down
        lower = max(4.0, asleep // 15 * 15 / 60)
        said = f"{hours:g} h"
        out.append(
            Clash(
                key=f"sleep:{','.join(days)}",
                title=f"Your sleep times leave {asleep // 60} h {asleep % 60:02d} m asleep; your rule asks for {said}",
                detail=f"{days_spoken(tuple(days))}: bed at {ampm(bed)}, up at {ampm(wake)}"
                + (f", about {down} min winding down first" if down else "")
                + ". The times are what Friday learned; the rule is what you wrote.",
                update="learned",
                about=f"{bed}-{wake}-{down}-{hours}",
                options=(
                    Option(
                        "bedtime", f"Go to bed at {ampm(bedtime)}", f"Your {said} asleep, after winding down.", True
                    ),
                    Option("rule", f"Lower the rule to {lower:g} h", "Keep these times; plan with less sleep."),
                ),
                apply=lambda ctx_, option, days=days, bedtime=bedtime, name=name, lower=lower: answer_sleep(
                    ctx_, option, days, bedtime, name, lower
                ),
            )
        )
    return out


def answer_sleep(ctx: Ctx, option: str, days: list[str], bedtime: str, name: str, lower: float) -> str:
    if option == "bedtime":
        sleep = {d: s.model_dump() for d, s in ctx.settings["sleep"].items()}
        for day in days:
            sleep[day]["bedtime"] = bedtime
        write_setting(ctx, "sleep", sleep)
        return f"Bed at {ampm(bedtime)} on {days_spoken(tuple(days))}"
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    rule = next(r for r in rules if r["name"] == name)
    rule["params"] = {**rule["params"], "hours": lower}
    rule["reason"] = f"At least {lower:g} h of sleep a night"
    write_setting(ctx, "rules", rules)
    return f"At least {lower:g} h of sleep a night"


# "Wind down before bed" against when you wind down.


def wind_down(ctx: Ctx) -> list[Clash]:
    rule = next((r for r in ctx.settings["rules"] if r.type == "late_night" and r.enabled), None)
    sleep = ctx.settings["sleep"]
    if rule is None or sleep is None:
        return []
    wind, _ = nights_learned(ctx)
    school = ("sun", "mon", "tue", "wed", "thu")
    beds = [sleep[d].bedtime for d in school]
    bed = max(set(beds), key=beds.count)  # most school nights'
    down = next((wind[d] for d in school if sleep[d].bedtime == bed and d in wind), None)
    if down is None:
        return []
    start = str(rule.params.get("gradient_start") or "22:00")
    since_noon = lambda hhmm: (minutes(hhmm) - 12 * 60) % (24 * 60)  # noqa: E731 (11:30pm and 12:30am are an hour apart)
    expected = clock(minutes(bed) - down)
    if abs(since_noon(start) - since_noon(expected)) < WIND_OFF_BY:
        return []
    return [
        Clash(
            key="wind_down",
            title=f"“Wind down before bed” starts at {ampm(start)}, but you wind down from about {ampm(expected)}",
            detail=f"Your bedtime is {ampm(bed)} and you wind down for about {down} min, as Friday learned. The rule's "
            f"time came from an earlier bedtime.",
            update="rule",
            about=f"{start}-{expected}",
            options=(
                Option("rule", f"Start winding down at {ampm(expected)}", "Late work costs from then on.", True),
                Option("keep", f"Keep {ampm(start)}", "Late work costs from the earlier time, as now."),
            ),
            apply=lambda ctx_, option, expected=expected: answer_wind(ctx_, option, expected),
        )
    ]


def answer_wind(ctx: Ctx, option: str, expected: str) -> str:
    if option == "keep":
        return "Kept as it is"
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    rule = next(r for r in rules if r["type"] == "late_night")
    rule["params"] = {**rule["params"], "gradient_start": expected}
    write_setting(ctx, "rules", rules)
    return f"Winding down from {ampm(expected)}"


# Meals your rule keeps that you skip.


def meals(ctx: Ctx) -> list[Clash]:
    if not ctx.settings["meal_tracking"].on:
        return []
    kept = [
        r
        for r in ctx.settings["rules"]
        if r.type == "elastic_shortfall"
        and r.enabled
        and str(r.name).startswith("you:")
        and (r.scope or {}).get("title_regex")
    ]
    if not kept:
        return []
    from friday.commands.eating import learned  # noqa: PLC0415

    out = []
    for meal in learned(ctx):
        if meal.skip_share is None or meal.skip_share < SKIPPED_MOSTLY:
            continue
        rule = next((r for r in kept if any(re.search(p, meal.kind) for p in r.scope["title_regex"])), None)
        if rule is None:
            continue
        out.append(
            Clash(
                key=f"meal:{meal.kind}:{meal.group}",
                title=f"You skip {meal.kind} on most {meal.group}, but your rule says it's never skipped",
                detail=f"Skipped on {round(meal.skip_share * 100)}% of {meal.days} {meal.group} Friday recorded. "
                "The rule keeps planning it; turning it off lets work take its time.",
                update="learned",
                about=f"{meal.kind}:{meal.group}",
                options=(
                    Option("keep", f"Keep planning {meal.kind}", "The rule stands; Friday keeps its time.", True),
                    Option("off", "Turn the rule off", "Work may take meal times when it needs them."),
                ),
                apply=lambda ctx_, option, name=rule.name: answer_meal(ctx_, option, name),
            )
        )
    return out


def answer_meal(ctx: Ctx, option: str, name: str) -> str:
    if option == "keep":
        return "Kept the rule"
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    next(r for r in rules if r["name"] == name)["enabled"] = False
    write_setting(ctx, "rules", rules)
    return "Turned the rule off"


def put(ctx: Ctx, key: str, value: Any) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": key}, {"value": json.dumps(value)})
