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
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import format_utc
from friday.ingest import llm
from friday.planner.store import area_names

ANYTHING = (
    "add",
    "edit",
    "drop",
    "done",
    "pin",
    "unpin",
    "shove",
    "rule_add",
    "settings_set",
    "day_override",
    "repeat",
    "skip",
)
# The Rules page sends what its grammar can't read; a change to the calendar typed there is still made (27 Oct: "add
# another salsa event on saturday…" was refused as no rule).
RULES = ANYTHING
SETTINGS = (
    "kind_order", "short_term_first", "exam_focus", "pointless_late", "sittings", "busy", "daily_cap", "event_kinds",
    "pace", "sleep",
)  # fmt: skip

SYSTEM = """You turn what a student asks for into changes to Friday, a planner, as Friday's own commands. You never
plan their time: a separate engine does that. You only propose commands, each with one plain sentence saying what it
does, for the student to confirm.

Commands you may use, with their inputs (times are local "YYYY-MM-DDTHH:MM"):
- add: a task or event. Task: {title, due?, duration_min?, preset?, area?}. Event: {title, when: "fixed", start, end,
  location?}: location is where it is ("Willard Straight Hall, room 215").
  Either repeats with every: "week", "fri", "mon,wed", "other week", "day", "month" (from its first date and time), or
  "rrule:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261211T235900" to end it. A repeat whose times aren't all alike takes
  exceptions: [{date: "YYYY-MM-DD", skip: true}] for a time it doesn't happen ("except the one on 11/14"), or
  [{date, location?, start?, end?, title?}] for one that's somewhere or sometime else ("this Saturday it's in room
  601"); start it on its first real date, and give exceptions only for dates it repeats on.
  A daily break such as lunch: {title, preset: "Routine", every: "rrule:FREQ=DAILY", min_min, ideal_min, max_min,
  release and due as the window's first day start and end}.
- edit: {id, ...fields to change} — use the ids in the context; moving an event changes its start and end; location
  sets where it is. An event that repeats ("repeats": true in the context) changes that time only, or, with
  from_date: "YYYY-MM-DD", that time and every later one ("from now on chem lecture is in Baker 200").
- repeat: {id, every} makes something they already have repeat ("make salsa repeat every week"), from its own date
  and time; never for an event from their calendar.
- drop: {id}; done: {id}; pin: {id, start, end, kind: "preferred" | "locked"}; unpin: {id}.
- skip: {id} for one time of a repeating event that won't happen ("no salsa next Saturday").
- shove: {range: "HH:MM-HH:MM YYYY-MM-DD"} keeps that time free of work.
- day_override: {date, bedtime?, wake?, cap_hours?}.
- rule_add: {text, overrides: {kind, subject, rel, at, until, days, amount, event, events, before_min}, strength:
  "Prefer" | "Strongly" | "Always"}. kind: window (a time of day: rel before/after/between/not_between with
  at/until), days (days: ["mon".."sun"], rel on/not_on), free (keep a window free: at/until, days), cap (amount: hours
  a day), early (amount: days early), after (event: title words), close (work as close to its due as possible:
  subject "exam prep" for studying for an exam, quiz or interview, events: [words in that prep's title, e.g. "math
  quiz"] or none for all prep, before_min: a buffer kept clear before it, e.g. 1440 for a day), meals_kept (events:
  the meals work never takes, of "breakfast", "lunch", "dinner"), meals_learned (events: the meals Friday plans or
  stops, and times, from what meal tracking learns), fit_gaps (short tasks in short gaps between events, long ones
  in long free stretches), runs_while_working (things that run by themselves, laundry, run only while you're working:
  never through an event or the night), sleep_min (amount: hours of sleep a night that work never cuts into, e.g. 7
  for "at least 7 hours of sleep"; days: the nights it holds, by the evening's weekday). subject: "work", "deep
  work", a tag, a kind or a title. A bedtime or wake time ("bed by 11") is the sleep setting, not a rule.
- settings_set: {key, value} for these keys only: kind_order (kinds most important first, e.g. ["Assignment",
  "Reading"] for "prioritize assignments over readings"), short_term_first (true for "prioritize short-term work
  over long-term", meaning the to-do's Short term list over its Long term list), exam_focus ({on: true, days_before}
  for focusing on an exam's course in the days before it), pointless_late ({kinds, titles} for work pointless once
  late), busy, daily_cap ({mon..sun: hours}), event_kinds (time kept free of work around events, to get there or
  away: {kind: {before_min, after_min}} for the kinds "class", "meeting", "exam" and "other"; "15 minutes before and
  after events" sets all four to 15 and 15; only the kinds given change), sittings ({one_go: true, split_first:
  [kinds]} for "I like to do things in one go, but split problem sets first": problem sets are the kind
  "Assignment"), pace ({weekly: {mon..sun: "Easy" | "Normal" | "Push"}} for a pace on those weekdays every week:
  "go easier on Saturdays and harder on Sundays" is {weekly: {"sat": "Easy", "sun": "Push"}}), sleep ({mon..sun:
  {bedtime, wake, margin_min}} for "bed by 11 on weeknights" or "up at 8 on weekends": only the nights and times
  named, as "HH:MM"; a night is named by its evening, a wake time by its morning).
When they ask whether they have time for something ("can I go to poker Thursday 8 to 11?", "do I have time for a
3 h project due Friday?"), propose the command that would add it (an event, or a task with its due and length) and
say in the reply that Friday shows under it whether it fits before they apply it; don't guess the answer yourself.
One message often asks for several different things at once (rules, moves, new and repeating events, places, weeks
off): propose a command for every one, in the order asked; a change to the calendar can need several. For example,
"add a location to salsa on friday which is Willard Straight Hall, room 215. add another salsa event on saturday from
1:35 - 2:40pm in Helen Newman Hall's dance studio except for the one on saturday on 11/14 and on this saturday, its in
Willard Straight Hall, room 601", with Friday's Salsa as event 41 and this Saturday the 31st, is: edit {id: 41,
location: "Willard Straight Hall, room 215"}, then add {title: "Salsa", when: "fixed", start: "2026-10-31T13:35", end:
"2026-10-31T14:40", location: "Helen Newman Hall, dance studio", every: "sat", exceptions: [{date: "2026-11-14", skip:
true}, {date: "2026-10-31", location: "Willard Straight Hall, room 601"}]}.
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
    client = llm.client(ctx.settings["llm"])
    if client is None:
        raise FieldError("text", llm.missing(ctx.settings["llm"]))
    spend_check(ctx)
    allowed = RULES if inp.purpose == "rule" else ANYTHING
    reply = client.messages.create(
        model=ctx.settings["llm"].model,
        max_tokens=4000,
        system=SYSTEM
        + (
            "\n\nThis was typed as a rule. A rule for how to plan is rule_add, settings_set or a daily break; but if"
            " it's a change to the calendar itself (an event to add, move, place, repeat or skip), propose that."
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
    answer = json.loads(text) if text else {}
    is_event = lambda name, given: touches_event(ctx, name, given)  # noqa: E731
    return proposals(answer, allowed, is_event, llm.spoken(ctx.settings["llm"]))


EVENT_COMMANDS = ("edit", "drop", "repeat")


def touches_event(ctx: Ctx, name: str, given: dict[str, Any]) -> bool:
    """Whether a proposal only adds, moves, repeats or deletes a calendar event (27 Oct: "have the claude requesting
    approval be a toggle for changing calendar events"): a new event, or an edit, a delete or a repeat of one you have
    that stays an event. Tasks, rules, settings, pins and shoves never are."""
    if name == "add":
        return given.get("when") == "fixed"
    if name not in EVENT_COMMANDS or not isinstance(given.get("id"), int):
        return False
    row = one(ctx.conn, "SELECT when_kind FROM items WHERE id = ? AND user_id = ?", [given["id"], ctx.user_id])
    return bool(row) and row["when_kind"] == "fixed" and given.get("when") in (None, "fixed")


def proposals(
    answer: dict[str, Any], allowed: tuple[str, ...], is_event: Any = lambda name, given: False, ai: str = "Claude"
) -> AskClaudeOut:
    """The AI's answer as actions, each checked against its command's input; what isn't allowed is refused, naming
    the AI you have (`ai`, as `llm.spoken` says it)."""
    actions = []
    for a in answer.get("actions") or []:
        name, given = str(a.get("command", "")), a.get("input") or {}
        error = None
        if name not in allowed or name not in REGISTRY:
            error = f"Friday doesn't let {ai} run {name!r} here"
        elif name == "settings_set" and given.get("key") not in SETTINGS:
            error = f"{ai[:1].upper() + ai[1:]} may not change the {given.get('key')!r} setting"
        else:
            try:
                REGISTRY[name].input_type.model_validate(given)
            except ValidationError as problem:
                first = problem.errors()[0]
                error = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
        actions.append(
            ProposedAction(
                sentence=str(a.get("sentence", name)),
                command=name,
                input=given,
                error=error,
                event=error is None and is_event(name, given),
            )
        )
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
        | ({"location": r["location"]} if r["location"] else {})
        | ({"repeats": True} if r["series_id"] is not None else {})
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
