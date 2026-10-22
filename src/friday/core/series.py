"""Series → occurrences (DESIGN §6.3). Pure: the caller says which occurrences already exist."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from friday.core.items import ITEM_FIELDS, Item
from friday.core.recurrence import next_occurrence, occurrences
from friday.core.time import format_utc, local_midnight, parse_local, parse_utc, to_utc


@dataclass(frozen=True)
class Series:
    id: int
    template: dict[str, Any]  # item fields; a fixed series also has length_min
    rrule: str
    dtstart_local: str
    created_utc: str
    per_window: int = 1
    release_offset_min: int | None = None
    due_offset_min: int | None = None
    active: bool = True


def materialize(series: Series, today: date, days: int, tz: str, existing: set[tuple[str, int]]) -> list[Item]:
    """New occurrences from today to `days` ahead. `existing` holds (occurrence_date, n) already made,
    detached or not, so regenerating never touches them."""
    if not series.active:
        return []
    start = parse_local(series.dtstart_local)
    lo, hi = local_midnight(today), local_midnight(today + timedelta(days=days))
    # A window that opened before today is still open until it closes: this week's problem set, started on Tuesday.
    since = lo if series.template.get("when") == "fixed" else max(start, lo - timedelta(days=366))
    today_opens = to_utc(lo + (start - local_midnight(start.date())), tz)  # today's occurrence time
    created = parse_utc(series.created_utc)
    made = []
    for moment in occurrences(series.rrule, start, since, hi):
        timing = occurrence_timing(series, moment, tz)
        if moment < lo and parse_utc(timing.get("due_utc", timing["release_utc"])) <= today_opens:
            continue  # closed already
        if "due_utc" in timing and parse_utc(timing["due_utc"]) < created:
            continue  # no backfilling
        for n in range(1, series.per_window + 1):
            if (moment.date().isoformat(), n) not in existing:
                made.append(make_occurrence(series, moment, n, timing))
    return made


def occurrence_timing(series: Series, moment: datetime, tz: str) -> dict[str, str]:
    if series.template.get("when") == "fixed":
        length = timedelta(minutes=series.template["length_min"])
        return {
            "start_utc": format_utc(to_utc(moment, tz)),
            "end_utc": format_utc(to_utc(moment + length, tz)),
        }
    if series.release_offset_min is not None or series.due_offset_min is not None:
        release = moment + timedelta(minutes=series.release_offset_min or 0)
        due = moment + timedelta(minutes=series.due_offset_min) if series.due_offset_min is not None else None
    else:
        release, due = moment, following_occurrence(series, moment)
        if due is not None and "BYDAY=" in series.rrule.upper():
            # "gym every mon, wed and fri" is gym on those days, not some time before the next one.
            due = min(due, moment + timedelta(days=1))
    timing = {"release_utc": format_utc(to_utc(release, tz))}
    if due is not None:
        timing["due_utc"] = format_utc(to_utc(due, tz))
    return timing


def following_occurrence(series: Series, moment: datetime) -> datetime | None:
    # The last occurrence before UNTIL still gets a full period, so the end date is ignored here.
    open_ended = ";".join(p for p in series.rrule.split(";") if not p.upper().startswith(("UNTIL=", "COUNT=")))
    return next_occurrence(open_ended, parse_local(series.dtstart_local), moment)


def make_occurrence(series: Series, moment: datetime, n: int, timing: dict[str, str]) -> Item:
    template = {k: v for k, v in series.template.items() if k in ITEM_FIELDS}
    return Item(
        **template | timing | {"series_id": series.id, "occurrence_date": moment.date().isoformat(), "occurrence_n": n}
    )
