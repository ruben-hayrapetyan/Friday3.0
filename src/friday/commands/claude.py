"""Ask Claude (personal's, COMBINED.md 20, 37): say what you want in your own words ("move my 5pm to Thursday",
"prioritize assignments over readings", "I want to focus on an exam before it") and Claude proposes the changes as
Friday's own commands, each with a sentence. Nothing runs until you apply it, one or all, through the same commands
as everything else, so each can be undone. The Rules page sends what its grammar can't read here with purpose "rule".

Claude only proposes. Each proposal is checked against its command's input before you see it, and one the command
wouldn't take carries the reason. Claude never plans: the engine does (DESIGN §21, principle 7).
"""

import json
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from friday.api.commands import AskClaudeInput, AskClaudeOut, ProposedAction
from friday.commands.inbox import record_spend, spend_check
from friday.commands.registry import REGISTRY, Ctx, command
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.time import format_utc
from friday.ingest import llm
from friday.planner.store import area_names

ANYTHING = ("add", "edit", "drop", "done", "pin", "unpin", "shove", "rule_add", "settings_set", "day_override")
RULES = ("rule_add", "settings_set", "add")
SETTINGS = (
    "kind_order", "short_term_first", "exam_focus", "pointless_late", "sittings", "busy", "daily_cap", "event_kinds",
    "pace",
)  # fmt: skip

SYSTEM = """You turn what a student asks for into changes to Friday, a planner, as Friday's own commands. You never
plan their time: a separate engine does that. You only propose commands, each with one plain sentence saying what it
does, for the student to confirm.

Commands you may use, with their inputs (times are local "YYYY-MM-DDTHH:MM"):
- add: a task or event. Task: {title, due?, duration_min?, preset?, area?}. Event: {title, when: "fixed", start, end}.
  A daily break such as lunch: {title, preset: "Routine", every: "rrule:FREQ=DAILY", min_min, ideal_min, max_min,
  release and due as the window's first day start and end}.
- edit: {id, ...fields to change} — use the ids in the context; moving an event changes its start and end.
- drop: {id}; done: {id}; pin: {id, start, end, kind: "preferred" | "locked"}; unpin: {id}.
- shove: {range: "HH:MM-HH:MM YYYY-MM-DD"} keeps that time free of work.
- day_override: {date, bedtime?, wake?, cap_hours?}.
- rule_add: {text, overrides: {kind, subject, rel, at, until, days, amount, event, events, before_min}, strength:
  "Prefer" | "Strongly" | "Always"}. kind: window (a time of day: rel before/after/between/not_between with
  at/until), days (days: ["mon".."sun"], rel on/not_on), free (keep a window free: at/until, days), cap (amount: hours
  a day), early (amount: days early), after (event: title words), close (work as close to its due as possible:
  subject "exam prep" for studying for an exam, quiz or interview, events: [words in that prep's title, e.g. "math
  quiz"] or none for all prep, before_min: a buffer kept clear before it, e.g. 1440 for a day). subject: "work",
  "deep work", a tag, a kind or a title.
- settings_set: {key, value} for these keys only: kind_order (kinds most important first, e.g. ["Assignment",
  "Reading"] for "prioritize assignments over readings"), short_term_first (true for "prioritize short-term work
  over long-term", meaning the to-do's Short term list over its Long term list), exam_focus ({on: true, days_before}
  for focusing on an exam's course in the days before it), pointless_late ({kinds, titles} for work pointless once
  late), busy, daily_cap ({mon..sun: hours}), event_kinds (time kept free of work around events, to get there or
  away: {kind: {before_min, after_min}} for the kinds "class", "meeting", "exam" and "other"; "15 minutes before and
  after events" sets all four to 15 and 15; only the kinds given change), sittings ({one_go: true, split_first:
  [kinds]} for "I like to do things in one go, but split problem sets first": problem sets are the kind
  "Assignment"), pace ({weekly: {mon..sun: "Easy" | "Normal" | "Push"}} for a pace on those weekdays every week:
  "go easier on Saturdays and harder on Sundays" is {weekly: {"sat": "Easy", "sun": "Push"}}).
If something can't be expressed with these, say so in the reply and propose nothing for it. Never invent ids."""

SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "command": {"type": "string"},
                    "input": {"type": "object"},
                },
                "required": ["sentence", "command", "input"],
            },
        },
    },
    "required": ["reply", "actions"],
}


@command("ask_claude", logged=False)
def ask_claude(ctx: Ctx, inp: AskClaudeInput) -> AskClaudeOut:
    """What Claude would change for what you asked, as commands for you to confirm; nothing is changed."""
    client = llm.client()
    if client is None:
        raise FieldError("text", "no AI: install Claude Code (the claude command) or set an Anthropic API key")
    spend_check(ctx)
    allowed = RULES if inp.purpose == "rule" else ANYTHING
    reply = client.messages.create(
        model=ctx.settings["llm"].model,
        max_tokens=4000,
        system=SYSTEM
        + (
            "\n\nThis is a rule for how to plan: answer only with rule_add, settings_set or a daily break."
            if inp.purpose == "rule"
            else ""
        ),  # fmt: skip
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {"role": "user", "content": [{"type": "text", "text": context(ctx) + "\n\nThe student asks:\n" + inp.text}]}
        ],
    )
    used = reply.usage.input_tokens + reply.usage.output_tokens
    record_spend(ctx.conn, ctx.user_id, ctx.today.isoformat(), used)
    text = next((b.text for b in reply.content if getattr(b, "type", "") == "text"), "")
    return proposals(json.loads(text) if text else {}, allowed)


def proposals(answer: dict[str, Any], allowed: tuple[str, ...]) -> AskClaudeOut:
    """Claude's answer as actions, each checked against its command's input; what isn't allowed is refused."""
    actions = []
    for a in answer.get("actions") or []:
        name, given = str(a.get("command", "")), a.get("input") or {}
        error = None
        if name not in allowed or name not in REGISTRY:
            error = f"Friday doesn't let Claude run {name!r} here"
        elif name == "settings_set" and given.get("key") not in SETTINGS:
            error = f"Claude may not change the {given.get('key')!r} setting"
        else:
            try:
                REGISTRY[name].input_type.model_validate(given)
            except ValidationError as problem:
                first = problem.errors()[0]
                error = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
        actions.append(ProposedAction(sentence=str(a.get("sentence", name)), command=name, input=given, error=error))
    return AskClaudeOut(reply=str(answer.get("reply", "")), actions=actions)


def context(ctx: Ctx) -> str:
    """What Claude needs to name things right: now, your tags and kinds, open tasks, and the next two weeks' events."""
    now = ctx.local(format_utc(ctx.now_utc))
    tasks = [
        {"id": r["id"], "title": r["title"], "due": ctx.local(r["due_utc"]), "kind": r["preset"]}
        for r in rows(
            ctx.conn,
            "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' "
            "ORDER BY coalesce(due_utc, '9999') LIMIT 80",
            [ctx.user_id],
        )  # fmt: skip
    ]
    until = format_utc(ctx.now_utc + int(timedelta(days=14).total_seconds() // 60))
    events = [
        {"id": r["id"], "title": r["title"], "start": ctx.local(r["start_utc"]), "end": ctx.local(r["end_utc"])}
        for r in rows(
            ctx.conn,
            "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind = 'fixed' "
            "AND start_utc >= ? AND start_utc < ? ORDER BY start_utc LIMIT 120",
            [ctx.user_id, format_utc(ctx.now_utc - 1440), until],
        )  # fmt: skip
    ]
    return "Context:\n" + json.dumps(
        {
            "now": now,
            "today": ctx.today.isoformat(),
            "tags": sorted(area_names(ctx.conn, ctx.user_id).values()),
            "kinds": list(ctx.settings["presets"]),
            "tasks": tasks,
            "events": events,
            "notes": list(ctx.settings["notes"]),
        }
    )
