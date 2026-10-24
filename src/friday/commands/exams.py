"""Exams ahead and their prep (the Projects & exams page): each upcoming exam with the work that prepares for it, how
much is done and left, when the last of it is planned, and whether that is before the exam."""

import re

from friday.api.types import Empty
from friday.api.views import ExamOut, ExamPrepOut
from friday.commands.fields import item_out
from friday.commands.horizon import finishes
from friday.commands.registry import Ctx, query
from friday.core.db import rows
from friday.core.guess import EXAM, course_word
from friday.core.items import Item
from friday.core.rows import item_from_row
from friday.core.time import UNIT_MIN, format_utc, parse_utc
from friday.planner.progress import minutes_by_item, remaining_minutes

AHEAD_DAYS = 120  # a term's worth: finals included, not next year's
NEAR_MIN = 3 * 1440  # exam prep due within three days of an exam is for it (planner/build.exam_due reads it so too)


@query("exams")
def exams(ctx: Ctx, inp: Empty) -> list[ExamOut]:
    """Upcoming exams, soonest first, each with its prep: what it waits on, and exam prep for its course due at it."""
    now = format_utc(ctx.now_utc)
    until = format_utc(ctx.now_utc + AHEAD_DAYS * 1440)
    events = [
        item_from_row(r)
        for r in rows(
            ctx.conn,
            "SELECT * FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' AND end_utc > ? "
            "AND start_utc < ? ORDER BY start_utc, id",
            [ctx.user_id, now, until],
        )
    ]
    work = {
        r["id"]: item_from_row(r)
        for r in rows(
            ctx.conn,
            "SELECT * FROM items WHERE user_id = ? AND when_kind != 'fixed' AND status IN ('todo', 'done')",
            [ctx.user_id],
        )
    }
    waits: dict[int, list[int]] = {}
    for r in rows(ctx.conn, "SELECT item_id, depends_on_id FROM dependencies WHERE user_id = ?", [ctx.user_id]):
        waits.setdefault(r["item_id"], []).append(r["depends_on_id"])
    prep = linked_prep(events, work, waits)
    # An event named like an exam counts once something prepares for it; a class waiting on a reading doesn't.
    found = [e for e in events if is_exam(e) or (EXAM.search(e.title) and prep.get(e.id or 0))]
    done = minutes_by_item(ctx.conn, ctx.user_id)
    left = {i: remaining_minutes(it, done.get(i, 0)) or 0 for i, it in work.items() if it.status == "todo"}
    finish = finishes(ctx, left)
    return [exam_out(ctx, e, [work[i] for i in prep.get(e.id or 0, [])], done, left, finish) for e in found]


def is_exam(event: Item) -> bool:
    return event.event_kind == "exam" or event.preset == "Exam"


def linked_prep(events: list[Item], work: dict[int, Item], waits: dict[int, list[int]]) -> dict[int, list[int]]:
    """Each event's prep: the work it waits on (prep made `before` it), then exam prep for the same course or tag due
    within three days of an exam's start, given to the nearest such exam."""
    out: dict[int, list[int]] = {}
    taken: set[int] = set()
    for event in events:
        mine = [i for i in waits.get(event.id or 0, []) if i in work]
        out[event.id or 0] = mine
        taken.update(mine)
    for item_id, item in sorted(work.items()):
        if item_id in taken or item.preset != "Exam prep" or not item.due_utc:
            continue
        due = parse_utc(item.due_utc)
        near = [
            (abs(parse_utc(e.start_utc) - due), e.id or 0)
            for e in events
            if e.start_utc and (is_exam(e) or EXAM.search(e.title)) and same_course(e, item)
            and abs(parse_utc(e.start_utc) - due) <= NEAR_MIN
        ]  # fmt: skip
        if near:
            out[min(near)[1]].append(item_id)
    return out


def same_course(event: Item, item: Item) -> bool:
    shared_tag = event.area_id is not None and event.area_id == item.area_id
    return shared_tag or course_word(event.title) == course_word(item.title)


def exam_out(
    ctx: Ctx, exam: Item, prep: list[Item], done: dict[int, int], left: dict[int, int], finish: dict[int, str]
) -> ExamOut:
    prep = sorted(prep, key=lambda p: (p.due_utc or "9999", p.id or 0))
    open_prep = [p for p in prep if p.status == "todo" and left.get(p.id or 0, 0) > 0]
    planned = [finish[p.id or 0] for p in open_prep if (p.id or 0) in finish]
    start = ctx.local(exam.start_utc) or ""
    last = max(planned) if planned and len(planned) == len(open_prep) else None
    if not prep:
        status = "no_prep"
    elif not open_prep:
        status = "ready"
    elif last is None:
        status = "unplanned"
    else:
        status = "late" if last > start else "on_track"
    return ExamOut(
        item=item_out(ctx, exam),
        prep=[
            ExamPrepOut(item=item_out(ctx, p, done.get(p.id or 0, 0)), planned_finish=finish.get(p.id or 0))
            for p in prep
        ],
        done_min=sum(done_minutes(p, done) for p in prep),
        remaining_min=sum(left.get(p.id or 0, 0) for p in open_prep),
        planned_finish=last,
        status=status,  # type: ignore[arg-type]
        focus_from=focus_from(ctx, exam),
    )


def done_minutes(prep: Item, done: dict[int, int]) -> int:
    """Time put in: what was logged, and at least its length once it's ticked off."""
    logged = done.get(prep.id or 0, 0)
    return max(logged, (prep.duration_units or 0) * UNIT_MIN) if prep.status == "done" else logged


def focus_from(ctx: Ctx, exam: Item) -> str | None:
    """When exam focus starts for this exam: the rule's days before it, if the rule is on and the title is an exam's."""
    focus = ctx.settings["exam_focus"]
    words = re.compile(r"\b(" + "|".join(re.escape(w) for w in focus.words) + r")\b", re.IGNORECASE)
    if not focus.on or not exam.start_utc or not words.search(exam.title):
        return None
    return ctx.local(format_utc(parse_utc(exam.start_utc) - focus.days_before * 1440))
