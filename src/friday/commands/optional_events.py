"""Whether work may take an event's time, from the event's own editor (8 Nov, your answer: everything about one event
in its editor, a rule naming it shown and changed there): kept (work never takes it), optional (taken only when work
would be late otherwise), or only when you're ahead. It's written as the rule in words would write it ("Gym with Sam
is optional"): the event's exact title in one optional or only-when-ahead rule, taken out of the others. A broader
rule that still covers it ("gym is optional" for "Gym with Sam") isn't changed from here: the answer says so."""

from typing import Any, Literal

from friday.api.commands import Changed, EventModeInput, EventOptionalInput
from friday.api.views import EventModeOut
from friday.commands.registry import Ctx, command, query
from friday.commands.rules import event_key, keep, owned_by_file, readings, slug, taken_from, unique
from friday.commands.settings import write_setting
from friday.core.items import FieldError
from friday.core.rule_text import Reading, sentence, spec, titled
from friday.core.textnorm import identity_text, norm
from friday.engine.rules.prices import has_words
from friday.planner.store import area_names

Mode = Literal["kept", "optional", "ahead"]


def mode_of(rules: list[dict[str, Any]], title: str) -> tuple[Mode, str | None]:
    """How this event is treated now, and the rule that says so (as it reads), by its exact title."""
    for r in rules:
        named = any(event_key(t) == event_key(title) for t in r["params"].get("titles", []))
        if r["type"] == "skippable" and r.get("enabled", True) and named:
            return ("ahead" if r["params"].get("ahead") else "optional"), r.get("reason")
    return "kept", None


def covering(ctx: Ctx, rules: list[dict[str, Any]], title: str) -> list[str]:
    """Rules that still reach this event by a word of its title, not by its title: changed on the Rules page."""
    text = ctx.settings["text"].rules()
    said = identity_text(norm(title, text))
    out = []
    for r in rules:
        if r["type"] != "skippable" or not r.get("enabled", True):
            continue
        words = [t for t in r["params"].get("titles", []) if event_key(t) != event_key(title)]
        if any(has_words(said, identity_text(norm(w, text))) for w in words):
            out.append(r.get("reason") or r["name"])
    return out


@command("event_optional", affects_plan=True)
def event_optional(ctx: Ctx, inp: EventOptionalInput) -> Changed:
    """Whether work may take this event's time: kept, optional, or only when you're ahead."""
    owned_by_file(ctx)
    title = " ".join(inp.title.split())
    if not title:
        raise FieldError("title", "Which event? Give its title")
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    mine = readings(ctx)
    rules, _ = taken_from(rules, {"params": {"titles": [title]}}, mine)
    said = f"{title}: work keeps off it"
    if inp.mode != "kept":
        reading = Reading(inp.mode, "events", events=(title,))
        name = unique(f"you:{slug(sentence(reading))}", {r["name"] for r in rules})
        areas, presets = list(area_names(ctx.conn, ctx.user_id).values()), list(ctx.settings["presets"])
        made = spec(reading, "Prefer", name, areas, presets)
        made["reason"] = made["reason"].replace(titled(title), title)  # your title as you wrote it, not "Gym With Sam"
        rules.append(made)
        mine[name] = {"reading": reading.to_dict(), "strength": "Prefer", "text": made["reason"]}
        said = made["reason"]
    write_setting(ctx, "rules", rules)
    keep(ctx, mine)
    still = covering(ctx, rules, title)
    if still:
        said += f". Your rule “{still[0]}” still covers it: change that one in Rules"
    return Changed(message=said)


@query("event_mode")
def event_mode(ctx: Ctx, inp: EventModeInput) -> EventModeOut:
    """How an event is treated now: its own setting, the rule that says it, and broader rules that reach it too."""
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    mode, rule = mode_of(rules, inp.title)
    return EventModeOut(mode=mode, rule=rule, covered_by=covering(ctx, rules, inp.title))
