"""Rules in your words (v22 Rules, M11): the planner's rules as sentences with a strength and a switch, and new ones
read from what you type by a fixed grammar (`core/rule_text.py`). Every change is a `rules` settings write, so it is
logged and undoable; your sentence and reading are kept in kv `rule_readings` to change the strength later."""

import json
import re
from typing import Any

from friday.api.commands import Changed, RuleAddInput, RuleRef, RuleSetInput, RuleTextInput
from friday.api.types import Empty
from friday.api.views import RuleOut, RuleReadOut
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.items import FieldError
from friday.core.rule_text import Reading, read, sentence, spec, with_overrides
from friday.core.settings import REFERENCE_RULES
from friday.planner.store import area_names, current_plan, kv_get

DEFAULT_WEIGHT = {r.name: r.weight for r in REFERENCE_RULES}
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
    "time_preference": "Friday avoids those hours",
    "reserve": "Friday keeps that time free",
    "daily_load": "Friday plans less on full days",
    "finish_early": "Friday aims to finish early",
    "after_event": "Friday places it right after",
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
    reading, strength = described(ctx, inp.text, {k: v for k, v in overrides.items() if v is not None or k == "days"})
    if reading is None:
        return RuleReadOut(reading=None, strength=strength, sentence="", effect="Friday can’t read that as a rule yet.")
    kind = spec(reading, strength, "preview", [], [])["type"]
    return RuleReadOut(
        reading=reading.to_dict(), strength=strength, sentence=sentence(reading), effect=EFFECT.get(kind, "")
    )


@command("rule_add", affects_plan=True)
def rule_add(ctx: Ctx, inp: RuleAddInput) -> Changed:
    """Add a rule in your words; Friday plans with it from now."""
    owned_by_file(ctx)
    reading, _ = described(ctx, inp.text, inp.overrides)
    if reading is None:
        raise FieldError("text", "Friday can’t read that as a rule; try one of the examples")
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    name = unique(f"you:{slug(sentence(reading))}", {r["name"] for r in rules})
    areas, presets = list(area_names(ctx.conn, ctx.user_id).values()), list(ctx.settings["presets"])
    write_setting(ctx, "rules", [*rules, spec(reading, inp.strength, name, areas, presets)])
    keep(ctx, {**readings(ctx), name: {"reading": reading.to_dict(), "strength": inp.strength, "text": inp.text}})
    return Changed(message=f"Added: {sentence(reading)}")


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
            )
        )  # type: ignore[arg-type]
        keep(ctx, {**readings(ctx), rule["name"]: {**mine, "strength": strength}})
        return
    if rule["name"] in ALWAYS or strength == "Always":
        raise FieldError("strength", "this rule's strength can be Prefer or Strongly")
    base = DEFAULT_WEIGHT.get(rule["name"], rule["weight"])
    rule["weight"] = base * (3 if strength == "Strongly" else 1)


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
    out = []
    for r in ctx.settings["rules"]:
        source = "you" if r.name.startswith("you:") else "default" if r.name in DEFAULT_WEIGHT else "learned"
        days_bent = sum(1 for totals in by_day.values() if totals.get(r.name, 0) > 0)
        kept = f"kept {len(by_day) - days_bent} of {len(by_day)} days" if by_day and r.enabled else ""
        out.append(
            RuleOut(
                name=r.name,
                type=r.type,
                sentence=words(r, mine),
                source=source,
                strength=strength_of(r, mine),
                enabled=r.enabled,
                kept=kept,
                effect=("Gives way in this plan" if days_bent else "Kept throughout this plan")
                if by_day and r.enabled
                else "Off",
                editable=r.name not in ALWAYS,
                background=source == "default" and (r.type in BACKGROUND or unset_buffer(r)),
            )
        )
    return out


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
    base = DEFAULT_WEIGHT.get(rule.name)
    return "Strongly" if base is not None and rule.weight >= 3 * base > 0 else "Prefer"


def current_report(ctx: Ctx) -> dict[str, Any]:
    saved = current_plan(ctx.conn, ctx.user_id)
    return json.loads(saved["report"]) if saved else {}


def keep(ctx: Ctx, value: dict[str, Any]) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "rule_readings"}, {"value": json.dumps(value)})


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def unique(name: str, taken: set[str]) -> str:
    n, out = 2, name
    while out in taken:
        out, n = f"{name}-{n}", n + 1
    return out
