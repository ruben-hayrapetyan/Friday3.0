"""Rules in your words (v22 Rules, M11): the planner's rules as sentences with a strength and a switch, and new ones
read from what you type by a fixed grammar (`core/rule_text.py`). Every change is a `rules` settings write, so it is
logged and undoable; your sentence and reading are kept in kv `rule_readings` to change the strength later."""

import json
import re
from dataclasses import replace
from typing import Any

from friday.api.commands import (
    Changed,
    RuleAddInput,
    RuleRef,
    RuleSetInput,
    RuleTextInput,
    RuleWinInput,
    SeriesSpacingInput,
)
from friday.api.types import Empty
from friday.api.views import RuleClashOut, RuleConflict, RuleOut, RuleReadOut
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.rule_text import Reading, days_spoken, read, read_all, sentence, spec, with_overrides, with_singulars
from friday.core.settings import REFERENCE_RULES
from friday.core.textnorm import identity_text, norm
from friday.core.time import ampm_in
from friday.engine.rules.prices import has_words
from friday.planner.contradictions import Conflict, against, contradictions
from friday.planner.learning import learnable
from friday.planner.snapshot import take_snapshot
from friday.planner.store import area_names, current_plan, kv_get
from friday.planner.views import rule_clash as find_clash

DEFAULT_WEIGHT = {r.name: r.weight for r in REFERENCE_RULES}
LEARNED_WEIGHT = 1.0  # a rule a yes to a proposal adds (`learn/proposals.py`) starts at this weight
ALWAYS = {"late_work", "late_tasks", "quota"}  # deadlines: they never bend
SAID = {
    "late_work": "Deadlines come first",
    "late_tasks": "Fewer tasks late, and none very late",
    "quota": "Keep pace with long work, week by week",
    "late_night": "Wind down before bed",
    "deep_run": "No more than {threshold} of focused work in a row",
    "daily_load": "At most {threshold} of work a day",
    "even_load": "Spread hard work evenly before it’s due",
    "energy": "Deep work when you’re at your best",
    "soft_late": "Soft deadlines when there’s room",
    "unscheduled": "Get to things with no deadline",
    "chunk_cost": "Fewer, longer sessions",
    "same_course": "Stay on one course for a stretch",
    "buffer": "Breathing room between blocks",
    "spread": "Spread out what you marked spread",
    "cluster": "Keep clustered work on few days",
    "target_shortfall": "Reach weekly targets",
    "elastic_shortfall": "Give flexible items their ideal time",
    "elastic_minimum": "Don't skip meals and routines",
    "open_value": "Side projects fill free time",
    "minimize_changes": "Keep the plan steady",
    "finish_early": "Finish work a day before it’s due",
}
# Built-in rules that are how the planner works rather than how you like your days: shown folded, below the rest.
BACKGROUND = {"quota", "energy", "soft_late", "unscheduled", "spread", "cluster", "target_shortfall",
              "elastic_shortfall", "open_value", "minimize_changes"}  # fmt: skip
EFFECT = {
    "spacing": "Friday plans each time at least that long after the last one you did",
    "late_cutoff": "Once it's overdue, Friday plans it as soon as it can and never on a later day; when that day "
    "comes and it isn't done, it's left off the plan",
    "time_preference": "Friday avoids those hours",
    "reserve": "Friday keeps that time free",
    "daily_load": "Friday plans less on full days",
    "finish_early": "Friday aims to finish early",
    "after_event": "Friday places it right after",
    "pace": "Every week, Friday plans less on Easy days and more on Push days",
    "skippable": "Friday plans around them as usual, and uses their time only when work would be late otherwise; "
    "the plan says when one gives way",
    "before_event": "Friday ends those days early when you're going (not when it plans work into that event)",
    "travel": "Friday keeps that time free around them, to get there and back, on top of each kind's",
    "fit_gaps": "Friday puts short tasks in the short gaps between events and keeps long free stretches for long work",
    "runs_while_working": "Friday starts a task that runs by itself (laundry) only where the time it runs misses your "
    "events and your sleep, so you're there to see to it",
    "sleep_min": "Friday keeps that much of the night before you wake for sleep, so work past your bedtime doesn't "
    "cut into it",
    "meals_kept": "Work never takes that time: when it would, the work is late instead. When events fill a meal's "
    "usual time, Friday plans it just outside",
    "meal_learned": "From what you track in Insights → Meals, each night Friday plans it or stops, and moves it to "
    "when you eat and how long you take",
    "close_to_due": "Friday plans it in the last free time before it's due (prep: before its exam), each day earlier "
    "costing a little more; a buffer you name is kept clear",
    "ahead": "Friday plans work into that time first and leaves it free only when everything fits without it; each "
    "week the plan says go or skip",
    "late_work": "Already built in and always on: when work would be late, Friday plans past your pace and your "
    "preferences, Easy days too. Only your sleep, your daily limit and rules set to Always hold",
}


def readings(ctx: Ctx) -> dict[str, dict[str, Any]]:
    return kv_get(ctx.conn, "rule_readings", {}, ctx.user_id) or {}


def owned_by_file(ctx: Ctx) -> None:
    if "rules" in (kv_get(ctx.conn, "config_keys", [], ctx.user_id) or []):
        raise FieldError("rules", "rules are set in friday.toml; change them there")


def described(ctx: Ctx, text: str, overrides: dict[str, Any]) -> tuple[Reading | None, str]:
    found, strength = read(text) if text.strip() else (None, "Prefer")
    if found is None and overrides.get("kind"):
        found = Reading(overrides["kind"])
    return (with_overrides(found, overrides) if found else None), strength


@query("rule_read")
def rule_read(ctx: Ctx, inp: RuleTextInput) -> RuleReadOut:
    """How a sentence reads as a rule, with any fields you set yourself; nothing is saved."""
    try:
        overrides = json.loads(inp.overrides or "{}")
    except json.JSONDecodeError as error:
        raise FieldError("overrides", "not JSON") from error
    chain, said = read_all(inp.text) if inp.text.strip() and not overrides else ([], "Prefer")
    if len(chain) > 1:  # "no work 7:10–7:20 and 7:30–7:40": a rule for each, the first with the rest beside it
        first, *rest = (read_out(ctx, r, said) for r in chain)
        return first.model_copy(update={"also": rest})
    reading, strength = described(ctx, inp.text, {k: v for k, v in overrides.items() if v is not None or k == "days"})
    if reading is None:
        return RuleReadOut(reading=None, strength=strength, sentence="", effect="Friday can’t read that as a rule yet.")
    return read_out(ctx, reading, strength)


def read_out(ctx: Ctx, reading: Reading, strength: str) -> RuleReadOut:
    """What one rule would be and do, and the rules it would contradict."""
    areas, presets = list(area_names(ctx.conn, ctx.user_id).values()), list(ctx.settings["presets"])
    new = spec(reading, strength, "preview", areas, presets, ctx.settings["time"].day_start)
    effect = EFFECT.get(reading.kind if reading.kind in ("ahead", "meals_kept") else new["type"], "")
    if reading.kind == "meals_learned" and not ctx.settings["meal_tracking"].on:
        effect += ". Meal tracking is off: turn it on in Insights → Meals so Friday has something to learn from"
    if reading.events:
        found = events_named(ctx, reading.events)
        effect += f". Matches {', '.join(found)}" if found else ". No event has those words in its title yet"
    if reading.kind == "pace":
        effect += replaced_paces(ctx, dict(reading.paces or ()))
    if reading.kind == "spacing":
        found = repeats_named(ctx, reading.subject)
        effect += f". Sets it on {', '.join(t for _, t in found)}" if found else ". No repeating task has that name yet"
    mine = readings(ctx)
    if new["type"] == "skippable":
        _, moved = taken_from([r.model_dump() for r in ctx.settings["rules"]], new, dict(mine))
        effect += "".join(f". Takes it out of “{m}”" for m in moved)
    said = {r.name: words(r, mine) for r in ctx.settings["rules"]}
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    conflicts = [conflict_out(c, said) for c in against(new, rules)] if reading.kind not in NOT_COMPARED else []
    return RuleReadOut(
        reading=reading.to_dict(), strength=strength, sentence=sentence(reading), effect=effect, conflicts=conflicts
    )


NOT_COMPARED = {
    "spacing",
    "late_cutoff",
    "pace",
    "deadlines",
    "meals_kept",
    "meals_learned",
}  # settings, not rules: a pace replaces that day's, and deadlines are built in


def replaced_paces(ctx: Ctx, days: dict[str, str]) -> str:
    """ ". Replaces Push on Saturdays": a weekday's pace is one setting, so a new one takes the old one's place."""
    weekly = ctx.settings["pace"].weekly
    gone: dict[str, list[str]] = {}
    for day, pace in days.items():
        if weekly.get(day) not in (None, pace):
            gone.setdefault(weekly[day], []).append(day)
    if not gone:
        return ""
    return ". Replaces " + " and ".join(f"{pace} on {days_spoken(tuple(d))}" for pace, d in gone.items())


def conflict_out(c: Conflict, said: dict[str, str]) -> RuleConflict:
    return RuleConflict(
        other=c.other, other_sentence=said.get(c.other, c.other), why=c.why, days=list(c.days), overlap=c.overlap
    )


def events_named(ctx: Ctx, words: tuple[str, ...]) -> list[str]:
    """The upcoming events a rule's words find, as the planner matches them: by the words in their titles."""
    rules = ctx.settings["text"].rules()
    wanted = [identity_text(norm(w, rules)) for w in with_singulars(words)]  # "exams" finds "Biology Exam"
    titles = [
        r["title"]
        for r in rows(
            ctx.conn,
            "SELECT DISTINCT title FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' "
            "AND start_utc >= ? ORDER BY title",
            [ctx.user_id, ctx.now_text],
        )
    ]
    return [t for t in titles if any(has_words(identity_text(norm(t, rules)), w) for w in wanted)][:6]


@command("rule_add", affects_plan=True)
def rule_add(ctx: Ctx, inp: RuleAddInput) -> Changed:
    """Add a rule in your words; Friday plans with it from now. A sentence that says several stretches of the day
    adds a rule for each (8 Nov), in one command, so one Undo takes them all back."""
    chain = chained(inp.text) if not inp.overrides else []
    if len(chain) > 1:
        owned_by_file(ctx)
        for reading in chain:
            add_reading(ctx, reading, inp.text, inp.strength)
        return Changed(message=f"Added {len(chain)} rules: " + "; ".join(sentence(r) for r in chain))
    return added(ctx, inp.text, inp.strength, inp.overrides)


def chained(text: str) -> list[Reading]:
    """The rules a sentence says when it says more than one stretch of the day; one or none otherwise."""
    return read_all(text)[0] if text.strip() else []


def added(ctx: Ctx, text: str, strength: str, overrides: dict[str, Any] | None = None) -> Changed:
    """A rule in your words added, as the Rules page adds it (also what a learned habit you keep becomes)."""
    owned_by_file(ctx)
    reading, _ = described(ctx, text, overrides or {})
    if reading is None:
        raise FieldError("text", "Friday can’t read that as a rule; try one of the examples")
    return add_reading(ctx, reading, text, strength)


def add_reading(ctx: Ctx, reading: Reading, text: str, strength: str) -> Changed:
    if reading.kind == "pace":
        return weekly_pace(ctx, dict(reading.paces or ()), sentence(reading))
    if reading.kind == "deadlines":
        return deadlines_first(ctx)
    if reading.kind == "spacing":
        return spaced_repeats(ctx, reading)
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    name = unique(f"you:{slug(sentence(reading))}", {r["name"] for r in rules})
    areas, presets = list(area_names(ctx.conn, ctx.user_id).values()), list(ctx.settings["presets"])
    new = spec(reading, strength, name, areas, presets, ctx.settings["time"].day_start)  # type: ignore[arg-type]
    mine = readings(ctx)
    rules, moved = taken_from(rules, new, mine) if new["type"] == "skippable" else (rules, [])
    write_setting(ctx, "rules", [*rules, new])
    keep(ctx, {**mine, name: {"reading": reading.to_dict(), "strength": strength, "text": text}})
    return Changed(message=f"Added: {sentence(reading)}" + "".join(f". Taken out of “{m}”" for m in moved))


def taken_from(
    rules: list[dict[str, Any]], new: dict[str, Any], mine: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """One event, one rule: a new optional (or only-when-ahead) rule takes its events out of the other such rules,
    which then say what's left, or go when nothing is (`mine`, the kept readings, is updated to match). Returns the
    rules and what each one that gave something up said before."""
    wanted = {event_key(t) for t in new["params"]["titles"]}
    out, moved = [], []
    for r in rules:
        titles = r["params"].get("titles", []) if r["type"] == "skippable" else []
        left = [t for t in titles if event_key(t) not in wanted]
        if left == titles:
            out.append(r)
            continue
        moved.append(words_of(r, mine))
        if not left:
            mine.pop(r["name"], None)
            continue
        stored = mine.get(r["name"])
        kind = "ahead" if r["params"].get("ahead") else "optional"
        reading = Reading(**{**stored["reading"], "days": None, "paces": None}) if stored else Reading(kind, "events")
        reading = replace(reading, events=tuple(left))
        if stored:
            mine[r["name"]] = {**stored, "reading": reading.to_dict()}
        out.append(r | {"params": r["params"] | {"titles": left}, "reason": sentence(reading)})
    return out, moved


def event_key(title: str) -> str:
    return re.sub(r"^(?:the|my) ", "", " ".join(title.lower().split()))


def words_of(rule: dict[str, Any], mine: dict[str, Any]) -> str:
    return ampm_in(rule.get("reason") or mine.get(rule["name"], {}).get("text") or rule["name"])


def deadlines_first(ctx: Ctx) -> Changed:
    """Built in and on unless you switched it off: switched back on, never added twice."""
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    off = [r for r in rules if r["type"] in ("late_work", "late_tasks") and not r["enabled"]]
    if off:
        write_setting(ctx, "rules", [r | {"enabled": True} if r in off else r for r in rules])
        return Changed(message="Deadlines come first is back on: Friday works more when it must, so nothing is late")
    return Changed(message="Already on: Friday works more when it must, so nothing is late")


def repeats_named(ctx: Ctx, words: str) -> list[tuple[int, str]]:
    """Your active repeating tasks whose title has these words in it, as (id, title)."""
    wanted = identity_text(norm(words, ctx.settings["text"].rules())).rstrip("s")
    found = []
    for r in rows(ctx.conn, "SELECT id, template FROM series WHERE user_id = ? AND active = 1", [ctx.user_id]):
        template = json.loads(r["template"])
        title = template.get("title", "")
        if template.get("when_kind", template.get("when")) != "fixed" and has_words(
            identity_text(norm(title, ctx.settings["text"].rules())), wanted
        ):
            found.append((r["id"], title))
    return found


def spaced_repeats(ctx: Ctx, reading: Reading) -> Changed:
    """A rule keeping a repeat's times apart is that repeat's `min_gap_days` (C50), set as its field sets it."""
    found = repeats_named(ctx, reading.subject)
    if not found:
        raise FieldError("text", f"no repeating task is called “{reading.subject}”: make it repeat first")
    from friday.commands.series import series_spacing

    for series_id, _ in found:
        series_spacing(ctx, SeriesSpacingInput(id=series_id, days=reading.amount))
    return Changed(message=f"Added: {sentence(reading)} ({', '.join(t for _, t in found)})")


def weekly_pace(ctx: Ctx, days: dict[str, str], said: str) -> Changed:
    """Those weekdays' pace, every week (`pace.weekly`); Normal clears a day back to the default."""
    pace = ctx.settings["pace"]
    unknown = sorted({p for p in days.values() if p not in ctx.settings["paces"]})
    if unknown:
        raise FieldError("text", f"no pace named {unknown[0]}")
    weekly = {d: p for d, p in {**pace.weekly, **days}.items() if p != pace.default}
    write_setting(ctx, "pace", pace.model_dump() | {"weekly": weekly})
    return Changed(message=f"Every week: {said}")


@command("rule_set", affects_plan=True)
def rule_set(ctx: Ctx, inp: RuleSetInput) -> Changed:
    """Change a rule's strength, or switch it off or on."""
    owned_by_file(ctx)
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    found = next((r for r in rules if r["name"] == inp.name), None)
    if found is None:
        raise FieldError("name", f"no rule named {inp.name}")
    if inp.enabled is not None:
        found["enabled"] = inp.enabled
    if inp.strength is not None:
        restrength(ctx, found, inp.strength)
    write_setting(ctx, "rules", rules)
    return Changed(message="Saved")


def restrength(ctx: Ctx, rule: dict[str, Any], strength: str) -> None:
    mine = readings(ctx).get(rule["name"])
    if mine:
        areas, presets = list(area_names(ctx.conn, ctx.user_id).values()), list(ctx.settings["presets"])
        rule.update(
            spec(
                Reading(**{**mine["reading"], "days": tuple(mine["reading"]["days"] or ()) or None}),
                strength,
                rule["name"],
                areas,
                presets,
                ctx.settings["time"].day_start,
            )
        )  # type: ignore[arg-type]
        keep(ctx, {**readings(ctx), rule["name"]: {**mine, "strength": strength}})
        return
    if rule["name"] in ALWAYS or strength == "Always":
        raise FieldError("strength", "this rule's strength can be Prefer or Strongly")
    base = base_weight(rule["name"])
    rule["weight"] = (rule["weight"] if base is None else base) * (3 if strength == "Strongly" else 1)


def base_weight(name: str) -> float | None:
    """A rule's weight at Prefer: a default's, or a learned rule's (12 Nov: each Strongly on a learned rule tripled
    it again, and Prefer never brought it back), None for one Friday doesn't know the start of."""
    if name in DEFAULT_WEIGHT:
        return DEFAULT_WEIGHT[name]
    return LEARNED_WEIGHT if name.startswith("learned:") else None


@command("rule_remove", affects_plan=True)
def rule_remove(ctx: Ctx, inp: RuleRef) -> Changed:
    """Delete a rule (a default one comes back only by adding it again in Settings → Advanced)."""
    owned_by_file(ctx)
    if inp.name in ALWAYS:
        raise FieldError("name", "deadlines are what Friday plans around, so this rule stays")
    rules = [r.model_dump() for r in ctx.settings["rules"] if r.name != inp.name]
    if len(rules) == len(ctx.settings["rules"]):
        raise FieldError("name", f"no rule named {inp.name}")
    write_setting(ctx, "rules", rules)
    return Changed(message="Deleted")


@query("rules")
def rules(ctx: Ctx, inp: Empty) -> list[RuleOut]:
    """Every rule in your words: where it came from, its strength, whether it's on and how often the plan keeps it."""
    mine = readings(ctx)
    report = current_report(ctx)
    by_day = report.get("rule_totals_by_day", {})
    wins = kv_get(ctx.conn, "rule_wins", [], ctx.user_id)
    said = {r.name: words(r, mine) for r in ctx.settings["rules"]}
    against_each = contradictions([r.model_dump() for r in ctx.settings["rules"]], wins)
    out = []
    for r in ctx.settings["rules"]:
        source = "you" if r.name.startswith("you:") else "default" if r.name in DEFAULT_WEIGHT else "learned"
        days_bent = sum(1 for totals in by_day.values() if totals.get(r.name, 0) > 0)
        kept = f"kept {len(by_day) - days_bent} of {len(by_day)} days" if by_day and r.enabled else ""
        out.append(
            RuleOut(
                name=r.name,
                type=r.type,
                sentence=said[r.name],
                source=source,
                strength=strength_of(r, mine),
                enabled=r.enabled,
                kept=kept,
                effect=("Gives way in this plan" if days_bent else "Kept throughout this plan")
                if by_day and r.enabled
                else "Off",
                editable=r.name not in ALWAYS,
                background=source == "default" and (r.type in BACKGROUND or unset_buffer(r)),
                wins_over=[w["loser"] for w in wins if w["winner"] == r.name],
                gives_way_to=[w["winner"] for w in wins if w["loser"] == r.name],
                contradicts=[conflict_out(c, said) for c in against_each.get(r.name, [])],
            )
        )
    return out


@query("rule_clash")
def rule_clash(ctx: Ctx, inp: RuleRef) -> RuleClashOut:
    """What a rule the plan bends is up against: plans once more with it weighed far more (a few seconds)."""
    rule = next((r for r in ctx.settings["rules"] if r.name == inp.name), None)
    if rule is None:
        raise FieldError("name", f"no rule named {inp.name}")
    mine = readings(ctx)
    said = {r.name: words(r, mine) for r in ctx.settings["rules"]}
    if inp.name not in learnable(ctx.settings):
        return RuleClashOut(rule=inp.name, other=None, sentence=said[inp.name])
    found = find_clash(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), inp.name)
    if found is None:
        return RuleClashOut(rule=inp.name, other=None, sentence=said[inp.name])
    return RuleClashOut(
        rule=inp.name,
        other=found.other,
        days=found.days,
        sentence=said[inp.name],
        other_sentence=said.get(found.other, found.other),
    )


@command("rule_win", affects_plan=True)
def rule_win(ctx: Ctx, inp: RuleWinInput) -> Changed:
    """Which of two clashing rules wins from now on; a new answer for the same two replaces the old one."""
    names = set(learnable(ctx.settings))
    for field, name in (("winner", inp.winner), ("loser", inp.loser)):
        if name not in names:
            raise FieldError(
                field,
                f"{name} isn't a rule that can give way"
                if any(r.name == name for r in ctx.settings["rules"])
                else f"no rule named {name}",
            )
    if inp.winner == inp.loser:
        raise FieldError("loser", "a rule can't win over itself")
    pair = {inp.winner, inp.loser}
    kept = [w for w in kv_get(ctx.conn, "rule_wins", [], ctx.user_id) if {w["winner"], w["loser"]} != pair]
    kept.append({"winner": inp.winner, "loser": inp.loser})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "rule_wins"}, {"value": json.dumps(kept)})
    mine = readings(ctx)
    said = {r.name: words(r, mine) for r in ctx.settings["rules"]}
    return Changed(message=f"“{said[inp.winner]}” wins over “{said[inp.loser]}”")


def unset_buffer(rule: Any) -> bool:
    """Breathing room of 0 minutes everywhere does nothing until you set some (Settings → Schedule)."""
    p = rule.params
    return (
        rule.type == "buffer"
        and p.get("minutes") in (None, "0m", 0)
        and not p.get("by_area")
        and not p.get("by_preset")
    )


def words(rule: Any, mine: dict[str, Any]) -> str:
    return ampm_in(written(rule, mine))  # rules saved before the 12-hour clock read the same as new ones


def written(rule: Any, mine: dict[str, Any]) -> str:
    if rule.name in mine or (rule.reason and rule.reason != rule.name):
        return rule.reason or rule.name
    said = SAID.get(rule.type) or rule.name.replace("_", " ").capitalize()
    params = {k: hours(v) for k, v in rule.params.items()}
    if rule.type == "reserve":
        span = f"{rule.params.get('start')}–{rule.params.get('end')}"
        return f"Keep {params.get('free', '')} free {rule.name.replace('_', ' ')} ({span})"
    if rule.type == "buffer" and rule.params.get("minutes") not in (None, "0m", 0):
        return f"{said}: {rule.params['minutes']}"
    try:
        return said.format(**params)
    except KeyError:
        return said


def hours(value: Any) -> Any:
    return value.replace("h", " h") if isinstance(value, str) and re.fullmatch(r"\d+(\.\d+)?h", value) else value


def strength_of(rule: Any, mine: dict[str, Any]) -> str:
    if rule.name in mine:
        return mine[rule.name]["strength"]
    if rule.name in ALWAYS or rule.params.get("price") == "forbid":
        return "Always"
    base = base_weight(rule.name)
    return "Strongly" if base is not None and rule.weight >= 3 * base > 0 else "Prefer"


def current_report(ctx: Ctx) -> dict[str, Any]:
    saved = current_plan(ctx.conn, ctx.user_id)
    return json.loads(saved["report"]) if saved else {}


def keep(ctx: Ctx, value: dict[str, Any]) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "rule_readings"}, {"value": json.dumps(value)})


# Which end of a rule's hours is your day's start: "no work after 10pm" runs from 10pm to it, "before 9am" from it.
DAY_START_END = {"before": "end", "after": "start"}


def follow_day_start(ctx: Ctx, old: str, new: str) -> None:
    """A new day start moves the rules whose hours ran to the old one (audit, 12 Nov: they kept 4am whatever your day
    start): your "before" and "after" rules, read from your words; an end you set to another time yourself stays,
    and so do rules friday.toml sets."""
    if old == new or "rules" in (kv_get(ctx.conn, "config_keys", [], ctx.user_id) or []):
        return
    mine, moved = readings(ctx), False
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    for rule in rules:
        reading = mine.get(rule["name"], {}).get("reading") or {}
        end = DAY_START_END.get(reading.get("rel")) if reading.get("kind") == "window" else None
        if end and rule["type"] == "time_preference" and rule["params"].get(end) == old:
            rule["params"][end], moved = new, True
    if moved:
        write_setting(ctx, "rules", rules)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def unique(name: str, taken: set[str]) -> str:
    n, out = 2, name
    while out in taken:
        out, n = f"{name}-{n}", n + 1
    return out
