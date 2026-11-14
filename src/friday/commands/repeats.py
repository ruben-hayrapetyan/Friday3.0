"""Repeating calendar events (v22): each series comes in as one repeat, not as separate events, with the tag and kind
you pick. Until then its instances wait here rather than as suggestions one by one; once imported, the calendar keeps
making its occurrences (`series.external_id`). Each waits in the Inbox as one message (29 Oct: "what does this mean?
1 repeating event to bring in. i don't see any concrete action"): plan around it, or leave it out, which holds for its
later weeks too (`suggesting.said_of_series`). Settings → Repeating imports them as well."""

import json
from typing import Any

from friday.api.commands import Changed, RepeatBatch, RepeatsImportInput
from friday.api.types import Empty
from friday.api.views import RepeatFound
from friday.commands.inbox import apply
from friday.commands.registry import Ctx, command, query
from friday.commands.series import calendar_rule, weekdays_rule
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.recurrence import describe
from friday.core.textnorm import course_tag
from friday.core.time import clock_time
from friday.planner.store import area_names


def waiting(ctx: Ctx) -> dict[str, list[dict[str, Any]]]:
    """Pending instances by repeating event, earliest first."""
    found = rows(
        ctx.conn,
        "SELECT s.*, src.name AS calendar FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "JOIN sources src ON src.id = r.source_id WHERE s.user_id = ? AND s.status = 'pending' "
        "AND s.batch LIKE 'repeat:%' ORDER BY s.id",
        [ctx.user_id],
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for s in found:
        s["fields"] = json.loads(s["input"])
        out.setdefault(s["batch"], []).append(s)
    for instances in out.values():
        instances.sort(key=when)
    return out


def when(s: dict[str, Any]) -> str:
    return s["fields"].get("start") or s["fields"].get("due") or ""


def lead(instances: list[dict[str, Any]]) -> dict[str, Any]:
    """The event itself, rather than the exam prep a repeating quiz brings along."""
    return next((s for s in instances if s["fields"].get("preset") != "Exam prep"), instances[0])


def pattern(ctx: Ctx, batch: str, instances: list[dict[str, Any]]) -> str:
    """The repeat in words, like "Every Mon, Wed and Fri, 12:20pm–1:10pm" or "Yearly, all day": the calendar's own
    rule (the instances' weekdays when it is unknown) and the first's times."""
    seen = weekdays_rule([when(s) for s in instances])
    rule = calendar_rule(ctx, batch) or seen
    if "FREQ=WEEKLY" in rule and "BYDAY=" not in rule and "BYDAY=" in seen:
        rule += ";BYDAY=" + seen.split("BYDAY=")[1]  # a calendar's plain weekly event is on its first day's weekday
    words = describe(rule)
    first = lead(instances)["fields"]
    if first.get("blocks_time") is False and first.get("start", "").endswith("T00:00"):
        return f"{words}, all day"
    if first.get("start") and first.get("end"):
        return f"{words}, {clock_time(first['start'])}–{clock_time(first['end'])}"
    return f"{words}, due {clock_time(first['due'])}" if first.get("due") else words


@query("calendar_repeats")
def calendar_repeats(ctx: Ctx, inp: Empty) -> list[RepeatFound]:
    """Repeating events in your calendars waiting to be imported, each as one repeat."""
    out = []
    tags = list(area_names(ctx.conn, ctx.user_id).values())
    for batch, instances in waiting(ctx).items():
        first = lead(instances)
        out.append(
            RepeatFound(
                batch=batch,
                title=first["fields"].get("title", ""),
                kind=first["fields"].get("preset") or "Event",
                calendar=first["calendar"],
                pattern=pattern(ctx, batch, instances),
                count=len({when(s)[:10] for s in instances}),
                first=when(instances[0]) or None,
                tag=first["fields"].get("area") or course_tag(first["fields"].get("title", ""), tags),
                location=first["fields"].get("location"),
            )
        )
    return sorted(out, key=lambda r: (r.calendar, r.title))


@command("repeats_import", affects_plan=True)
def repeats_import(ctx: Ctx, inp: RepeatsImportInput) -> Changed:
    """Import repeating calendar events, each as one repeat with the tag and kind you pick."""
    found = waiting(ctx)
    for pick in inp.repeats:
        if pick.batch not in found:
            raise FieldError("repeats", "that repeating event isn't waiting any more; sync and look again")
        lead_kind = lead(found[pick.batch])["fields"].get("preset")
        for s in found[pick.batch]:
            fields = dict(s["fields"])
            if pick.area:
                fields["area"] = pick.area
            if pick.kind and fields.get("preset") == lead_kind:  # its exam prep stays exam prep
                fields["preset"] = pick.kind
            item_id = apply(ctx, s, fields)
            ctx.db.update(
                "suggestions", {"id": s["id"]}, {"status": "accepted", "decided_utc": ctx.now_text, "item_id": item_id}
            )
    count = len(inp.repeats)
    return Changed(message=f"Imported {count} repeat{'s' if count != 1 else ''}")


@command("repeats_leave_out", affects_plan=True)
def repeats_leave_out(ctx: Ctx, inp: RepeatBatch) -> Changed:
    """A repeating calendar event you don't go to: its weeks aren't planned around, now or as they come in."""
    found = waiting(ctx).get(inp.batch)
    if not found:
        raise FieldError("batch", "that repeating event isn't waiting any more; sync and look again")
    for s in found:
        ctx.db.update("suggestions", {"id": s["id"]}, {"status": "rejected", "decided_utc": ctx.now_text})
    title = lead(found)["fields"].get("title", "it")
    return Changed(message=f"Left out {title}, its later weeks too")
