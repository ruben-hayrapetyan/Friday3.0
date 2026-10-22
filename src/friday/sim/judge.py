"""A plan judged as a student would read it (M15): from the `plan` and `items` queries, each piece of work's
sittings, how early it ends, scraps and marathons, each day's hours, and the meals (routines with a length that
gives: when each is planned, for how long, inside its window or not). Shared by tests/scenarios/test_cornell.py and
`python -m friday.sim.agenda`.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any

SCRAP_MIN = 60  # a sitting shorter than this, of work longer than it, is a scrap
MARATHON_MIN = 180  # longer than this in one go is more than anyone sits through


@dataclass(frozen=True)
class Sitting:
    start: datetime
    end: datetime
    item_id: int
    title: str

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class Meal:
    title: str
    day: str
    minutes: int  # planned; 0 when it isn't
    inside: bool  # every block of it inside its window
    start: str | None = None  # its first block, "12:15"


@dataclass
class Verdict:
    sittings: dict[int, list[Sitting]]
    late: dict[str, float] = field(default_factory=dict)  # hard work ending after its due: hours of it after
    scraps: list[Sitting] = field(default_factory=list)
    marathons: list[Sitting] = field(default_factory=list)
    day_hours: dict[str, float] = field(default_factory=dict)  # work per day, open items left out
    open_hours: float = 0.0
    margins_h: list[float] = field(default_factory=list)  # how many hours before its due each piece of work ends
    unplanned: list[str] = field(default_factory=list)  # due inside the window, nothing planned
    meals: list[Meal] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        busiest = max(self.day_hours.values(), default=0.0)
        return {
            "late": self.late,
            "scraps": len(self.scraps),
            "marathons": len(self.marathons),
            "busiest_day_h": round(busiest, 2),
            "median_margin_h": round(median(self.margins_h), 1) if self.margins_h else None,
            "tight": sum(m < 6 for m in self.margins_h),  # ends within 6 hours of its due
            "open_h": round(self.open_hours, 1),
            "unplanned": self.unplanned,
        }


def sittings_of(blocks: list[dict[str, Any]]) -> dict[int, list[Sitting]]:
    """Each item's back-to-back blocks joined into sittings, in order."""
    out: dict[int, list[Sitting]] = defaultdict(list)
    for b in sorted(blocks, key=lambda b: (b["item_id"], b["start"])):
        start, end = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
        found = out[b["item_id"]]
        if found and found[-1].end == start:
            found[-1] = Sitting(found[-1].start, end, b["item_id"], b["title"])
        else:
            found.append(Sitting(start, end, b["item_id"], b["title"]))
    return out


def judge(plan: dict[str, Any], items: list[dict[str, Any]], until: datetime) -> Verdict:
    """The plan's work up to `until` (local), against the items it is for."""
    by_id = {i["id"]: i for i in items}
    verdict = Verdict(sittings_of(plan["blocks"]))
    hours: dict[str, float] = defaultdict(float)
    for item_id, found in verdict.sittings.items():
        item = by_id.get(item_id)
        if item is None or item["amount"] == "elastic":  # meals and routines: judged as meals, not work
            continue
        for s in found:
            if s.start >= until:
                continue
            if item["amount"] == "open":
                verdict.open_hours += s.minutes / 60
                continue
            hours[s.start.date().isoformat()] += s.minutes / 60
            if s.minutes < SCRAP_MIN and (item["remaining_min"] or 0) > s.minutes:
                verdict.scraps.append(s)
            if s.minutes > MARATHON_MIN:
                verdict.marathons.append(s)
        judge_due(verdict, item, found, until)
    verdict.day_hours = dict(hours)
    for item in items:
        due = item["due"] and datetime.fromisoformat(item["due"])
        flexible = item["status"] == "todo" and item["when"] != "fixed"
        if due and due < until and flexible and item["amount"] == "elastic" and item["release"]:
            verdict.meals.append(meal(item, verdict.sittings.get(item["id"], [])))
        elif due and due < until and flexible and item["id"] not in verdict.sittings:
            verdict.unplanned.append(item["title"])
    return verdict


def meal(item: dict[str, Any], found: list[Sitting]) -> Meal:
    release, due = datetime.fromisoformat(item["release"]), datetime.fromisoformat(item["due"])
    inside = all(release <= s.start and s.end <= due for s in found)
    start = f"{found[0].start:%H:%M}" if found else None
    return Meal(item["title"], release.date().isoformat(), sum(s.minutes for s in found), inside, start)


def judge_due(verdict: Verdict, item: dict[str, Any], found: list[Sitting], until: datetime) -> None:
    due = item["due"] and datetime.fromisoformat(item["due"])
    if not due or due > until or not found:
        return
    after = sum((s.end - max(s.start, due)).total_seconds() / 3600 for s in found if s.end > due)
    if after > 0 and item["firmness"] == "hard":
        verdict.late[item["title"]] = round(after, 2)
    verdict.margins_h.append((due - max(s.end for s in found)) / timedelta(hours=1))
