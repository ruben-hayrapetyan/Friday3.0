"""The simulation loop (DESIGN §24.4): a student lives a term with Friday, through the command registry, on a fake
clock in 15-minute steps.

Each day: the nightly jobs (close the day, materialize series), what the student tells Friday as it comes up, a
morning replan, then the day itself. When a block starts the student skips it, takes a safe swap, or starts it a
little late with the timer. Work takes its own true time: when Friday's estimate runs out first, the student adds
time to the item, as the Now bar's +30m does. Untimed blocks (meals, goals) are lived or skipped. A replan follows
any change within the hour. The evening review answers each block as it went: what the student never got to is
"not done".
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from friday.commands.all import REGISTRY  # noqa: F401  (registers every command)
from friday.commands.delivery import deliver
from friday.commands.learned import learn_nightly
from friday.commands.refit import prepare_questions
from friday.commands.registry import run
from friday.core.db import connect, rows
from friday.core.items import FieldError
from friday.core.settings import DEFAULTS, validate_value
from friday.core.time import format_local, format_utc, parse_local, parse_utc, to_local, to_utc
from friday.planner.learning import learnable
from friday.planner.store import current_plan
from friday.sim.generate import Event, Term, TermConfig, generate_term, local
from friday.sim.users import SimUser, Taste

TZ = "America/New_York"
WAKE, BED = "07:30", "23:30"
SLEEP = {d: {"bedtime": "23:30", "wake": "07:30", "margin_min": 60} for d in ("mon", "tue", "wed", "thu", "fri")} | {
    d: {"bedtime": "00:30", "wake": "09:00", "margin_min": 60} for d in ("sat", "sun")
}
REPLAN_AFTER_MIN = 60


@dataclass
class Metrics:
    days: int = 0
    hard_due: int = 0
    hard_missed: int = 0
    late_hours: float = 0.0
    plan_seconds: list[float] = field(default_factory=list)
    moved_hours: float = 0.0  # hours of blocks replans moved: churn
    lived_minutes: int = 0  # planned time the student did: timer sessions and untimed blocks lived
    missed_minutes: int = 0  # planned blocks the student never got to or skipped
    errors: list[str] = field(default_factory=list)
    notifications: int = 0
    wall_seconds: float = 0.0
    predicted: list[bool] = field(default_factory=list)  # per question: did the weights in use call it right
    recovery: float | None = None  # cosine of the learned weights with the true ones, at the end
    accepted: list[str] = field(default_factory=list)  # rules added from proposals

    def summary(self) -> dict[str, Any]:
        seconds = sorted(self.plan_seconds) or [0.0]
        return {
            "days": self.days,
            "hard deadlines": self.hard_due,
            "hard deadlines missed": self.hard_missed,
            "late hours": round(self.late_hours, 1),
            "replans": len(self.plan_seconds),
            "plan seconds p50": round(seconds[len(seconds) // 2], 2),
            "plan seconds p90": round(seconds[int(len(seconds) * 0.9)], 2),
            "churn hours per day": round(self.moved_hours / max(1, self.days), 2),
            "adherence": round(self.lived_minutes / max(1, self.lived_minutes + self.missed_minutes), 2),
            "command errors": len(self.errors),
            "notifications": self.notifications,
            "questions": len(self.predicted),
            "accuracy of the weights in use": round(sum(self.predicted) / len(self.predicted), 2)
            if self.predicted
            else None,
            "weight recovery": None if self.recovery is None else round(self.recovery, 2),
            "rules accepted": self.accepted,
            "wall minutes": round(self.wall_seconds / 60, 1),
        }


@dataclass
class Working:
    item_id: int
    until: int  # UTC minutes
    minutes: int


class World:
    def __init__(self, folder: Path, term: Term, user: SimUser, taste: Taste | None = None) -> None:
        self.conn = connect(folder / "friday.db")
        self.folder = folder
        self.term, self.user, self.taste = term, user, taste
        self.events = list(term.events)
        self.metrics = Metrics()
        self.now = 0
        self.dirty = False
        self.last_replan = -(10**9)
        self.working: Working | None = None
        self.waiting: tuple[int, int, int, str | None] | None = None  # item, start at, planned minutes, area
        self.idle_until = 0
        self.handled: set[tuple[int, str]] = set()  # blocks (item, start) the student has reacted to
        self.lived: set[tuple[int, str]] = set()  # untimed blocks the student lived
        self.true_left: dict[int, int] = {}  # each started item's real minutes left
        self.at(local(term.config.start, "04:00"))
        self.do("settings_set", key="time", value={"timezone": TZ, "horizon_days": 14})
        self.do("settings_set", key="sleep", value=SLEEP)

    def at(self, moment: str) -> None:
        self.now = to_utc(parse_local(moment), TZ)

    def local_now(self) -> str:
        return format_local(to_local(self.now, TZ))

    def do(self, command: str, /, **payload: Any) -> Any:
        try:
            out = run(self.conn, command, payload, now_utc=self.now, provisional=False).result
        except FieldError as error:
            self.metrics.errors.append(f"{self.local_now()} {command}: {error}")
            return None
        if REGISTRY[command].affects_plan:
            self.dirty = True
        return out

    def replan(self) -> None:
        self.do("replan")
        self.dirty, self.last_replan = False, self.now
        saved = current_plan(self.conn)
        if saved is None:
            return
        report = json.loads(saved["report"])
        self.metrics.plan_seconds.append(report["solve"]["seconds"].get("total", 0.0))
        for moved in report["changes"].get("moved", []):
            self.metrics.moved_hours += given_up(moved["before"], moved["after"]) / 60

    def tell(self) -> None:
        """Run every event whose time has come."""
        while self.events and self.events[0].at <= self.local_now():
            event: Event = self.events.pop(0)
            self.do(event.command, **event.payload)

    def live_day(self, day: date) -> None:
        self.at(local(day, "04:00"))
        if day > self.term.config.start:
            self.do("close_day", date=(day - timedelta(days=1)).isoformat())
            self.do("materialize")
            learn_nightly(self.conn, self.now)
        self.at(local(day, WAKE))
        self.tell()
        sick = day in self.term.sick_days
        if sick and self.user.rng.random() < 0.5:
            self.do("pace", name="Easy", for_days=2)
        self.replan()
        while self.local_now() < local(day, BED):
            self.tell()
            self.notifications()
            if not sick:
                self.step()
            if self.dirty and self.now - self.last_replan >= REPLAN_AFTER_MIN:
                self.replan()
            self.now += 15
        if self.working:
            self.finish(self.working)
        if self.taste:
            self.answer_questions(day)
        self.review(day)
        self.metrics.days += 1

    def notifications(self) -> None:
        """The real notify job, on the in-app channel. A "did you finish it?" check comes only when nothing was
        recorded for the block, so the truthful answer is "not yet"."""
        for key in deliver(self.conn, self.now, self.folder):
            self.metrics.notifications += 1
            if key.startswith("check:"):
                self.do("settle", block_key=key.removeprefix("check:"), status="not_done")

    def step(self) -> None:
        if self.working:
            if self.now >= self.working.until:
                self.finish(self.working)
            return
        if self.waiting:
            item_id, start_at, planned, area = self.waiting
            if self.now >= start_at:
                self.waiting = None
                self.begin(item_id, planned, area)
            return
        if self.now < self.idle_until:
            return
        now = self.do("now")
        block = now and now["current"]
        if not block or block.get("fixed") or (block["item_id"], block["start"]) in self.handled:  # a class: sit it
            return
        self.handled.add((block["item_id"], block["start"]))
        self.react(now, block)

    def react(self, now: dict[str, Any], block: dict[str, Any]) -> None:
        left = minutes_between(self.local_now(), block["end"])
        item = self.do("item", id=block["item_id"])["item"]
        if self.user.skips():
            self.idle_until = self.now + left
            return
        if item["amount"] != "fixed":  # meals, goals, habits with no timer: lived as planned
            self.lived.add((block["item_id"], block["start"]))
            self.metrics.lived_minutes += left
            self.idle_until = self.now + left
            return
        if now["swaps"] and self.user.swaps():
            swap = now["swaps"][int(self.user.rng.integers(len(now["swaps"])))]
            self.begin(swap["item_id"], min(left, swap["minutes"]), None)
            return
        delay = self.user.delay()  # a late start shifts the work; it doesn't cancel it (skips do that)
        if delay:
            self.waiting = (block["item_id"], self.now + delay, left, block.get("area"))
        else:
            self.begin(block["item_id"], left, block.get("area"))

    def begin(self, item_id: int, planned: int, area: str | None) -> None:
        detail = self.do("item", id=item_id)
        if not detail or detail["item"]["status"] != "todo" or self.do("start", id=item_id) is None:
            return
        remaining = detail["item"]["remaining_min"] or planned
        if item_id not in self.true_left:
            self.true_left[item_id] = self.user.work_minutes(remaining, area)
        # Work the planned stretch; past Friday's estimate, keep going up to an hour if the item isn't finished.
        session = min(self.true_left[item_id], planned if self.true_left[item_id] <= remaining else planned + 60)
        self.working = Working(item_id, self.now + max(15, session), max(15, session))

    def finish(self, working: Working) -> None:
        self.do("stop")
        self.working = None
        self.metrics.lived_minutes += working.minutes
        self.true_left[working.item_id] -= working.minutes
        detail = self.do("item", id=working.item_id)
        if detail is None:
            return
        if self.true_left[working.item_id] <= 0:
            self.do("done", id=working.item_id)
        elif detail["item"]["remaining_min"] == 0:  # Friday thinks it's finished; it isn't
            extra = -(-self.true_left[working.item_id] // 15) * 15
            self.do("edit", id=working.item_id, duration_min=(detail["item"]["duration_min"] or 0) + extra)

    def answer_questions(self, day: date) -> None:
        """The student's side of learning: today's comparisons by their true taste, a proposal only when it is
        their real missing preference, the check-in, and on Sundays the week's suggestion approved."""
        assert self.taste is not None
        if day.weekday() == 0:
            self.taste.step_mood()
        prepare_questions(self.conn, self.now)
        asked = self.do("questions") or {"comparisons": [], "proposal": None, "checkin": False}
        theta = (self.do("learning") or {}).get("multipliers") or {}
        for q in asked["comparisons"]:
            row = self.conn.execute("SELECT features_a, features_b FROM comparisons WHERE id = ?", [q["id"]]).fetchone()
            a, b = json.loads(row[0]), json.loads(row[1])
            truth = self.taste.energy(a) < self.taste.energy(b)
            guess = sum(theta.get(r, 1.0) * v for r, v in a["rules"].items()) < sum(
                theta.get(r, 1.0) * v for r, v in b["rules"].items()
            )
            self.metrics.predicted.append(truth == guess)
            self.do("compare_answer", id=q["id"], answer="a" if self.taste.prefers_a(a, b) else "b")
        if asked["proposal"]:
            name = asked["proposal"]["name"]
            days, window, scope = name.split(":")
            yes = (
                self.taste.family == "missing"
                and days == "fri_sat"
                and window in ("late", "night", "evening")
                and scope == "any"
            )
            self.do("proposal_answer", kind="rule", name=name, yes=yes)
            if yes:
                self.metrics.accepted.append(name)
        if asked["checkin"]:
            mood = (
                self.taste.mood
                if self.user.rng.random() < 0.7
                else str(self.user.rng.choice(("normal", "tired", "motivated")))
            )
            self.do("checkin", state=mood)

    def approve(self) -> None:
        learned = self.do("learning") or {}
        if learned.get("suggested"):
            self.do("learn_apply", version=learned["suggested"]["version"])

    def review(self, day: date) -> None:
        sheet = self.do("review", date=day.isoformat())
        if sheet is None:
            return
        entries = []
        for block in sheet["blocks"]:
            truth = "done" if (block["item_id"], block["start"]) in self.lived else "not_done"
            if truth == "not_done":
                self.metrics.missed_minutes += minutes_between(block["start"], block["end"])
            entries.append({"block_key": block["key"], "status": self.user.answer(truth), "share": 0.5})
        self.do("review_submit", date=day.isoformat(), entries=entries)
        for item in sheet["finished"]:
            self.do("done", id=item["id"])
        if self.taste and day.weekday() == 6:
            self.approve()

    def deadlines(self) -> None:
        """Hard items due inside the term, and how late each finished (or still is)."""
        end = self.now
        for r in rows(
            self.conn,
            "SELECT status, due_utc, completed_utc FROM items WHERE firmness = 'hard' AND due_utc IS NOT NULL "
            "AND when_kind != 'fixed' AND due_utc <= ?",
            [format_utc(end)],
        ):
            self.metrics.hard_due += 1
            finished = parse_utc(r["completed_utc"]) if r["completed_utc"] else end
            late = (finished - parse_utc(r["due_utc"])) / 60
            if r["status"] != "done" or late > 0:
                self.metrics.hard_missed += 1
                self.metrics.late_hours += max(0.0, late)


def given_up(before: list[list[str]], after: list[list[str]]) -> int:
    """Minutes of an item's old blocks that its new blocks don't cover: a shifted chunk counts its shift only."""
    old = [(parse_utc(a), parse_utc(b)) for a, b in before]
    new = [(parse_utc(a), parse_utc(b)) for a, b in after]
    kept = sum(max(0, min(b, d) - max(a, c)) for a, b in old for c, d in new)
    return max(0, sum(b - a for a, b in old) - kept)


def minutes_between(start: str, end: str) -> int:
    return int((parse_local(end) - parse_local(start)).total_seconds() // 60)


def run_term(
    folder: Path,
    config: TermConfig | None = None,
    seed: int = 0,
    days: int | None = None,
    on_day: Callable[[int, Metrics], None] | None = None,
    family: str | None = None,
) -> Metrics:
    """Live `days` days (the whole term when None) and return the metrics; `on_day` hears after each day. With a
    `family` the student also has a hidden taste and answers the review's questions (DESIGN §24.4)."""
    config = config or TermConfig()
    term = generate_term(config, seed)
    rules = learnable({"rules": validate_value("rules", [r.model_dump() for r in DEFAULTS["rules"]])})
    taste = Taste.make(seed + 20_000, family, rules) if family else None
    world = World(folder, term, SimUser.make(seed + 10_000, term.areas), taste)
    began = time.perf_counter()
    for d in range(days if days is not None else config.weeks * 7):
        world.live_day(config.start + timedelta(days=d))
        if on_day:
            on_day(d + 1, world.metrics)
    world.deadlines()
    if taste:
        world.metrics.recovery = recovery(world, taste)
    world.metrics.wall_seconds = time.perf_counter() - began
    return world.metrics


def recovery(world: World, taste: Taste) -> float:
    """Cosine between the weights Friday now plans with and the student's true ones."""
    learned = (world.do("learning") or {}).get("multipliers") or {}
    rules = sorted(taste.theta)
    a = [learned.get(r, 1.0) for r in rules]
    b = [taste.theta[r] for r in rules]
    norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
