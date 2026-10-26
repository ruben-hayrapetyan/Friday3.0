"""A world to stress: a fresh database driven through the registry as the app drives it, a clock moved by hand, every
replan timed stage by stage (snapshot, solve, assemble, save) and its plan checked, and every command's own time
(with the executor's quick placement the app shows at once) recorded too.

Isolation is the tests' (tests/conftest.py), set up by `isolated()`: friday.toml in a temporary folder, no Anthropic
key, no `claude` command, no Google sign-in page."""

import contextlib
import json
import os
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from friday.commands.all import REGISTRY  # noqa: F401  (registers the commands)
from friday.commands.registry import run
from friday.core.db import connect, rows
from friday.core.quickadd import MEAL
from friday.core.time import format_utc, parse_local, parse_utc, to_utc
from friday.engine.checker import check
from friday.planner.assemble import assemble
from friday.planner.build import MEAL_REACH_MIN
from friday.planner.service import lock_conflicts, save_plan
from friday.planner.snapshot import take_snapshot
from friday.planner.solve import solve


@contextlib.contextmanager
def isolated() -> Iterator[Path]:
    """The tests' isolation for a whole run: nothing reads your config, calls the AI or reaches Google."""
    import google_auth_oauthlib.flow

    from friday.ingest import llm

    def no_google_page(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("stress runs don't open Google's sign-in page")

    saved = (os.environ.get("FRIDAY_CONFIG"), os.environ.get("ANTHROPIC_API_KEY"), llm.cli_path,
             google_auth_oauthlib.flow.InstalledAppFlow.run_local_server)  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="friday-stress-") as folder:
        os.environ["FRIDAY_CONFIG"] = str(Path(folder) / "friday.toml")
        os.environ.pop("ANTHROPIC_API_KEY", None)
        llm.cli_path = lambda: None
        google_auth_oauthlib.flow.InstalledAppFlow.run_local_server = no_google_page  # type: ignore[method-assign]
        try:
            yield Path(folder)
        finally:
            llm.cli_path = saved[2]
            google_auth_oauthlib.flow.InstalledAppFlow.run_local_server = saved[3]  # type: ignore[method-assign]
            for key, value in (("FRIDAY_CONFIG", saved[0]), ("ANTHROPIC_API_KEY", saved[1])):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@dataclass
class Replan:
    """One replan: what it was after, how long each stage took, what the solver said and what the checks found."""

    scenario: str
    step: str
    open_items: int
    events: int
    snapshot_s: float
    solve_s: float
    assemble_s: float
    save_s: float
    total_s: float
    solver: dict[str, Any]
    late: int
    blocks: int
    overloaded: bool
    status: str
    issues: list[str] = field(default_factory=list)
    moved_share: float | None = None  # of the future plan, against the plan before (stability), when asked


@dataclass
class Command:
    scenario: str
    command: str
    seconds: float
    provisional: int  # quick placements the app showed at once


@dataclass
class World:
    """A student's Friday in a throwaway database."""

    name: str
    conn: sqlite3.Connection
    now: int
    tz: str = "America/New_York"
    replans: list[Replan] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def fresh(cls, folder: Path, name: str, now_local: str, tz: str = "America/New_York", **settings: Any) -> "World":
        """An empty database set up the way setup leaves one: timezone, sleep, and whatever `settings` give."""
        conn = connect(folder / f"{name}.db")
        world = cls(name, conn, to_utc(parse_local(now_local), tz), tz)
        world.do("settings_set", key="time", value={"timezone": tz, "horizon_days": settings.pop("horizon_days", 14)})
        night = {"bedtime": settings.pop("bedtime", "23:30"), "wake": settings.pop("wake", "07:30"), "margin_min": 60}
        world.do(
            "settings_set", key="sleep", value=dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), night)
        )
        for key, value in settings.items():
            world.do("settings_set", key=key, value=value)
        return world

    def do(self, command: str, /, quick: bool = False, **payload: Any) -> Any:
        """Run a command as the app does (`quick`: with the executor's placement the app shows at once), timed."""
        began = time.perf_counter()
        out = run(self.conn, command, payload, now_utc=self.now, actor="you", provisional=quick)
        self.commands.append(Command(self.name, command, time.perf_counter() - began, len(out.provisional or [])))
        return out.result

    def try_do(self, command: str, /, **payload: Any) -> Any:
        """A command that may rightly be refused: the refusal is returned, not raised."""
        try:
            return self.do(command, **payload)
        except Exception as error:  # noqa: BLE001  (a refusal is an answer here)
            return error

    def at(self, local: str) -> "World":
        self.now = to_utc(parse_local(local), self.tz)
        return self

    def later(self, minutes: int) -> "World":
        self.now += minutes
        return self

    def replan(self, step: str, warm: bool = True, stability: bool = False) -> Replan:
        """Replan as the solver worker does, each stage timed; the plan checked; the record kept."""
        before = self.future_blocks() if stability else None
        t0 = time.perf_counter()
        snapshot = take_snapshot(self.conn, self.now)
        t1 = time.perf_counter()
        solved = solve(snapshot, warm)
        t2 = time.perf_counter()
        assembled = assemble(snapshot, solved)
        conflicts = lock_conflicts(snapshot, assembled)
        if conflicts:
            assembled.status = "waiting"
            assembled.report["conflicts"] = conflicts
        t3 = time.perf_counter()
        save_plan(self.conn, snapshot, assembled, step)
        t4 = time.perf_counter()
        issues = [f"wall {v}" for v in check(solved.problem, solved.result.plan)]
        grid = solved.problem.grid
        coarse = [int(grid.start[s]) for s in range(grid.S) if int(grid.units[s]) > 1]
        issues += plan_issues(self, assembled.status, min(coarse) if coarse else None)
        status = self.do("status")
        record = Replan(
            scenario=self.name,
            step=step,
            open_items=sum(1 for i in snapshot.items if i.status == "todo" and i.when != "fixed"),
            events=sum(1 for i in snapshot.items if i.status == "todo" and i.when == "fixed"),
            snapshot_s=t1 - t0,
            solve_s=t2 - t1,
            assemble_s=t3 - t2,
            save_s=t4 - t3,
            total_s=t4 - t0,
            solver=dict(assembled.report.get("solve", {})),
            late=len(status["late_items"]),
            blocks=len(assembled.blocks),
            overloaded=solved.overloaded,
            status=assembled.status,
            issues=issues,
        )
        if before is not None:
            record.moved_share = moved_share(before, self.future_blocks())
        self.replans.append(record)
        return record

    def future_blocks(self) -> set[tuple[int, str, str]]:
        plan = self.do("plan", start=self.local(self.now), end=self.local(self.now + 14 * 1440))
        return {(b["item_id"], b["start"], b["end"]) for b in plan["blocks"] if b["start"] >= self.local(self.now)}

    def local(self, minutes: int) -> str:
        from friday.core.time import format_local, to_local

        return format_local(to_local(minutes, self.tz))


def moved_share(before: set[tuple[int, str, str]], after: set[tuple[int, str, str]]) -> float:
    """How much of the plan a replan changed: the blocks not kept as they were, over all of them."""
    if not before and not after:
        return 0.0
    return 1 - len(before & after) / max(len(before | after), 1)


def plan_issues(world: World, status: str, coarse_from: int | None = None) -> list[str]:
    """What the saved plan gets wrong, checked from the database rather than the engine: work over events that hold
    their time, blocks over each other or before now, more planned than is left, a due passed without saying so,
    work before its release or before what it waits on, a locked pin not kept."""
    conn, now = world.conn, world.now
    plan = rows(conn, "SELECT id FROM plans WHERE user_id = 1 ORDER BY id DESC LIMIT 1")
    if not plan:
        return []
    cut = -(-now // 15) * 15
    blocks = [
        (r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), bool(r["tentative"]))
        for r in rows(conn, "SELECT * FROM blocks WHERE plan_id = ? AND end_utc > ?", [plan[0]["id"], format_utc(cut)])
    ]
    items = {r["id"]: r for r in rows(conn, "SELECT * FROM items WHERE user_id = 1")}
    out: list[str] = []
    future = [b for b in blocks if b[1] >= cut]
    # Blocks over each other.
    ordered = sorted(future, key=lambda b: b[1])
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b[1] < a[2] and not (a[3] or b[3]):
            out.append(f"overlap T{a[0]} and T{b[0]} at {world.local(b[1])}")
    # Work over an event that holds its time.
    events = [
        (parse_utc(i["start_utc"]), parse_utc(i["end_utc"]), i["title"])
        for i in items.values()
        if i["when_kind"] == "fixed"
        and i["status"] == "todo"
        and i["blocks_time"]
        and not i["free"]
        and i["start_utc"]
        and i["end_utc"]
    ]
    optional = optional_titles(world)
    for item_id, start, end, _ in future:
        for es, ee, title in events:
            if start < ee and end > es and not any(o in title.lower() for o in optional):
                out.append(f"T{item_id} over event {title!r} at {world.local(max(start, es))}")
                break
    # More planned than is left; a due passed without being reported late; before release.
    late = {i["item_id"] for i in world.do("status")["late_items"]}
    left = remaining(world)
    # Beyond the fine days the grid's slots are 30 minutes, so a 45-minute task fills an hour there: allowed.
    fine_end = coarse_from if coarse_from is not None else now + fine_days(conn) * 1440
    per_item: dict[int, int] = {}
    coarse: dict[int, int] = {}
    for item_id, start, end, tentative in future:
        if not tentative:
            per_item[item_id] = per_item.get(item_id, 0) + end - start
            if start >= fine_end:
                coarse[item_id] = coarse.get(item_id, 0) + 1
    for item_id, minutes in per_item.items():
        item = items.get(item_id)
        if item is None or item["status"] != "todo":
            out.append(f"T{item_id} planned though it isn't open ({item and item['status']})")
            continue
        rest = left.get(item_id)
        if rest is not None and item["amount"] == "fixed" and minutes > rest + 14 + 15 * coarse.get(item_id, 0):
            out.append(f"T{item_id} planned {minutes}m but only {rest}m left")
    for item_id, start, end, _ in future:
        item = items.get(item_id)
        if item is None:
            continue
        if item["due_utc"] and item["firmness"] == "hard" and end > parse_utc(item["due_utc"]) and item_id not in late:
            out.append(f"T{item_id} planned past its due ({world.local(parse_utc(item['due_utc']))}) and not said late")
        # A meal may reach up to MEAL_REACH_MIN outside its window when events fill it (planner/build.meal_room).
        reach = MEAL_REACH_MIN if item["preset"] == "Routine" and MEAL.search(item["title"]) else 0
        if item["release_utc"] and start < parse_utc(item["release_utc"]) - reach:
            out.append(f"T{item_id} planned before its release")
    # What it waits on comes first.
    by_item: dict[int, list[tuple[int, int]]] = {}
    for item_id, start, end, _ in future:
        by_item.setdefault(item_id, []).append((start, end))
    for dep in rows(conn, "SELECT item_id, depends_on_id, lag_min FROM dependencies"):
        mine, theirs = by_item.get(dep["item_id"]), by_item.get(dep["depends_on_id"])
        if mine and theirs and min(s for s, _ in mine) < max(e for _, e in theirs) + (dep["lag_min"] or 0):
            out.append(f"T{dep['item_id']} starts before T{dep['depends_on_id']} it waits on is done")
    # Locked pins kept (unless the plan is waiting on a lock it can't keep).
    if status != "waiting":
        for pin in rows(conn, "SELECT * FROM pins WHERE kind = 'locked' AND start_utc >= ?", [format_utc(cut)]):
            got = by_item.get(pin["item_id"], [])
            kept = any(s <= parse_utc(pin["start_utc"]) and e >= parse_utc(pin["end_utc"]) for s, e in got)
            said = any("lock on" in n for n in world.do("status")["notices"])  # a lock the plan said it couldn't keep
            if not kept and not said and items.get(pin["item_id"], {}).get("status") == "todo":
                out.append(f"locked pin of T{pin['item_id']} at {world.local(parse_utc(pin['start_utc']))} not kept")
    return out


def fine_days(conn: sqlite3.Connection) -> int:
    found = rows(conn, "SELECT value FROM settings WHERE user_id = 1 AND key = 'time'")
    return int(json.loads(found[0]["value"]).get("fine_days", 7)) if found else 7


def remaining(world: World) -> dict[int, int]:
    found = world.do("items", status="todo")
    listed = found if isinstance(found, list) else found.get("items", [])
    return {i["id"]: i["remaining_min"] for i in listed if i.get("remaining_min") is not None}


def optional_titles(world: World) -> list[str]:
    rules = json.loads(
        (rows(world.conn, "SELECT value FROM settings WHERE user_id = 1 AND key = 'rules'") or [{"value": "[]"}])[0][
            "value"
        ]
    )
    return [t.lower() for r in rules if r.get("type") == "skippable" for t in r.get("params", {}).get("titles", [])]
