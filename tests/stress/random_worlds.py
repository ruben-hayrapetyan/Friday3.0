"""Random worlds (24 Nov, the user: "stress test on a lot of sample settings, schedules, and situations to see if there
is any unexpected behavior because of any changes"; "the randomly generated situation/settings tester which should be
exhaustive in and of itself"). A seed makes one world, the same every time: its settings (time zone, sleep by night,
day start, horizon, meals, rules typed in words), its schedule (classes, events all-day and overlapping, to-dos of every
kind, projects with waits, repeating to-dos, ongoing projects) and a stream of changes (add, edit, finish, delete,
skip, pin, lock, wait for, time, progress, undo, pace, breaks, one-day changes, rules, late accepted) with the clock
moving on. After each change Friday plans again and every check runs: what a plan must never do (harness.plan_issues),
every page's query answering, the late lists agreeing, sleep kept; an error that isn't a refusal with a reason is a
crash. Each replan leaves a fingerprint (the week's blocks, what's late), so two versions of Friday can be run on the
same seeds and compared (`compare`): a difference no change explains is the "unexpected behavior".

    PYTHONPATH=src:. uv run python -m tests.stress.random_worlds --seeds 0-199 --changes 30 --out DIR [--jobs 5]
    PYTHONPATH=src:. uv run python -m tests.stress.random_worlds --compare OLD_DIR NEW_DIR

DIR gets issues.json (every check that failed, by seed and step, with the change before it) and fingerprints.jsonl.
Exit 1 if any check failed. tests/test_random_worlds.py runs a few seeds in the ordinary suite."""

import argparse
import json
import os
import random
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from friday.core.items import FieldError
from tests.stress.harness import World, isolated

ZONES = [
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Asia/Kolkata",
    "Australia/Adelaide",
    "America/Sao_Paulo",
    "Asia/Tokyo",
    "Pacific/Auckland",
]  # fmt: skip  (half-hour, southern, far east)
# Mondays, some across a daylight-saving change in some zones
STARTS = ["2026-10-19", "2026-10-26", "2026-11-02", "2026-03-02", "2026-03-30", "2026-09-28"]
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
RULES = [
    "no work after 10pm", "readings in the morning", "at most 6 hours of work a day", "no work on Saturdays",
    "problem sets in the afternoon", "keep 2 hours free on weekday evenings", "finish work a day before it's due",
    "laundry must not run during lunch", "no meetings before 10am", "always take a break after 2 hours",
    "gym three times a week", "work in sessions of at least an hour",
]  # fmt: skip
TITLES = ["Essay", "Problem set", "Lab report", "Reading", "Slides", "Code review", "Study for prelim", "Laundry",
          "Groceries", "Emails", "Paper draft", "Thesis chapter", "Flashcards", "Write-up", "Research"]  # fmt: skip
VIEWS = [("status", {}), ("now", {}), ("plan", {}), ("items", {"status": "all"}), ("projects", {}), ("exams", {}),
         ("inbox", {}), ("insights", {"weeks": 4}), ("week_review", {}), ("sleep", {}), ("triage", {}),
         ("load", {"weeks": 2}), ("rules", {}), ("settings", {}), ("vacations", {}), ("tips", {}), ("meals", {}),
         ("ongoing_projects", {}), ("learning", {}), ("brief", {})]  # fmt: skip


# How full a world's weeks are (24 Nov, the user: "make sure to stress test on very loaded schedules"): classes a week,
# one-off events, to-dos, how long they are (times), and the days they're due within. Overloaded: more work due within
# days than the week holds, so Friday has to say what's late and what doesn't fit, and say it the same everywhere.
LOADS: dict[str, dict[str, Any]] = {
    "light": {"classes": (0, 3), "events": (0, 2), "todos": (1, 6), "longer": 1, "due_days": (2, 16), "projects": 1},
    "usual": {"classes": (2, 7), "events": (0, 4), "todos": (3, 25), "longer": 1, "due_days": (-2, 16), "projects": 1},
    "heavy": {"classes": (6, 11), "events": (3, 9), "todos": (25, 60), "longer": 2, "due_days": (-2, 10),
              "projects": 3},
    "overloaded": {"classes": (8, 13), "events": (5, 12), "todos": (50, 90), "longer": 3, "due_days": (0, 5),
                   "projects": 4},
}  # fmt: skip
LOAD_ODDS = {"light": 2, "usual": 4, "heavy": 3, "overloaded": 2}
# When you sleep (24 Nov: asleep 11:15am-7:15pm, an ongoing project never got time: no world here slept by day)
SLEEPERS = {"usual": 6, "night owl": 2, "day sleeper": 1, "short nights": 1}


@dataclass
class Outcome:
    seed: int
    issues: list[dict[str, Any]] = field(default_factory=list)
    world: dict[str, str] = field(default_factory=dict)  # its zone, load and sleep
    fingerprints: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0


def hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def pick(rng: random.Random, odds: dict[str, int]) -> str:
    return rng.choices(list(odds), weights=list(odds.values()))[0]


def settings_of(rng: random.Random, sleeper: str = "usual") -> dict[str, Any]:
    """Sleep that differs by night: usually bedtimes from 9:30pm to 2am and wakes from 5am to 10:30am; a night owl's
    2-4am to 10am-noon; a day sleeper's (night shifts) 8-11am to 4-7pm; short nights, five hours or so."""
    night = {}
    usual_bed, usual_wake = {
        "usual": (rng.randrange(21 * 60 + 30, 26 * 60, 15), rng.randrange(5 * 60, 10 * 60 + 31, 15)),
        "night owl": (rng.randrange(26 * 60, 28 * 60 + 1, 15), rng.randrange(10 * 60, 12 * 60 + 1, 15)),
        "day sleeper": (rng.randrange(8 * 60, 11 * 60 + 1, 15), rng.randrange(16 * 60, 19 * 60 + 1, 15)),
        "short nights": (b := rng.randrange(24 * 60, 25 * 60 + 31, 15), b + rng.choice([270, 300, 330]) - 24 * 60),
    }[sleeper]
    for d in DAYS:
        bed = usual_bed + (rng.choice([0, 0, 30, 60, 90]) if d in ("fri", "sat") else rng.choice([0, 0, -30, 30]))
        wake = usual_wake + (rng.choice([0, 60, 90, 120]) if d in ("sat", "sun") else rng.choice([0, 0, -30, 30]))
        night[d] = {"bedtime": hhmm(bed), "wake": hhmm(wake), "margin_min": rng.choice([30, 60, 90])}
    return night


def local(day: date, minutes: int) -> str:
    return (datetime.combine(day, datetime.min.time()) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def build(world: World, rng: random.Random, monday: date, load: str = "usual") -> None:
    """The schedule: classes, events, to-dos, projects with waits, repeating to-dos, an ongoing project; as many and as
    long as the load says."""
    shape = LOADS[load]
    for n in range(rng.randrange(*shape["classes"])):  # classes, on two or three weekdays
        start = rng.randrange(8 * 60, 18 * 60, 5)
        for d in rng.sample(range(5), rng.choice([2, 3])):
            day = monday + timedelta(days=d)
            for week in range(2):
                at = day + timedelta(days=7 * week)
                world.try_do("add", title=f"Class {n}", when="fixed", start=local(at, start),
                             end=local(at, start + rng.choice([50, 75, 110, 170])))  # fmt: skip
    for _ in range(rng.randrange(*shape["events"])):  # one-off events, some all day, some overlapping
        day = monday + timedelta(days=rng.randrange(0, 13))
        if rng.random() < 0.3:
            world.try_do("add", title="All-day thing", when="fixed", start=local(day, 0), end=local(day, 1440))
        else:
            s = rng.randrange(7 * 60, 21 * 60, 15)
            world.try_do(
                "add", title="Event", when="fixed", start=local(day, s), end=local(day, s + rng.choice([30, 60, 120]))
            )
    for _ in range(rng.randrange(*shape["todos"])):
        add_todo(world, rng, monday, shape)
    for _ in range(shape["projects"]):  # projects whose steps wait for each other
        if rng.random() >= 0.7:
            continue
        project = world.try_do("add", title="Project", preset="Project", firmness=rng.choice(["hard", "soft"]),
                               due=local(monday + timedelta(days=rng.randrange(3, 20)), 17 * 60))  # fmt: skip
        if isinstance(project, dict):
            steps = []
            for i in range(rng.randrange(2, 5)):
                step = world.try_do("add", title=f"Step {i}", parent_id=project["item"]["id"],
                                    duration_min=rng.choice([30, 60, 120, 240, 480]))  # fmt: skip
                if isinstance(step, dict):
                    steps.append(step["item"]["id"])
            for a, b in zip(steps, steps[1:], strict=False):
                if rng.random() < 0.7:
                    world.try_do("depend", item_id=b, depends_on_id=a)
    if rng.random() < 0.6:
        world.try_do("series_add", title=rng.choice(["Lunch", "Breakfast", "Dinner"]), preset="Routine", every="day",
                     release_offset_min=rng.choice([420, 450, 690, 1020]),
                     due_offset_min=rng.choice([600, 630, 840, 1260]),
                     min_min=20, ideal_min=30, max_min=45)  # fmt: skip
    if rng.random() < 0.4:
        every = rng.choice(["mon", "wed fri", "week"])
        world.try_do("series_add", title="Weekly reading", preset="Reading", every=every,
                     duration_min=rng.choice([30, 60, 90]))  # fmt: skip
    if rng.random() < 0.4:
        world.try_do("ongoing_add", title="Practice", hours_per_week=rng.choice([2, 4, 6]))
    for text in rng.sample(RULES, rng.randrange(0, 4)):
        world.try_do("rule_add", text=text, strength=rng.choice(["Always", "Prefer"]))


def add_todo(world: World, rng: random.Random, monday: date, shape: dict[str, Any] | None = None) -> Any:
    shape = shape or LOADS["usual"]
    fields: dict[str, Any] = {"title": f"{rng.choice(TITLES)} {rng.randrange(100)}"}
    if rng.random() < 0.8:
        fields["due"] = local(
            monday + timedelta(days=rng.randrange(*shape["due_days"])),
            rng.choice([9 * 60, 12 * 60, 17 * 60, 23 * 60 + 59]),
        )
    if rng.random() < 0.85:
        fields["duration_min"] = rng.choice([15, 30, 45, 60, 90, 120, 180, 240, 360, 600]) * shape["longer"]
    for key, choices in (("firmness", ["hard", "soft", "none"]), ("importance", [1, 2, 3, 4, 5]),
                         ("shape", ["split", "one_sitting"]), ("energy", ["deep", "light"])):  # fmt: skip
        if rng.random() < 0.4:
            fields[key] = rng.choice(choices)
    if rng.random() < 0.08:
        fields["background"] = True
    if rng.random() < 0.08:
        fields["expires"] = True
    return world.try_do("add", **fields)


def change(world: World, rng: random.Random, monday: date) -> str:
    """One random change, said in words for the report."""
    items = [i for i in world.do("items", status="all") if i["when"] != "fixed"]
    open_ = [i for i in items if i["status"] == "todo"]
    pick = rng.choice(open_) if open_ else None
    kinds = ["add", "add", "edit", "done", "drop", "pin", "lock", "unpin", "depend", "time", "progress", "undo",
             "pace", "break", "override", "rule", "late", "skip", "reopen", "later", "tick", "tick"]  # fmt: skip
    kind = rng.choice(kinds)
    now_local = world.local(world.now)
    if kind == "add" or pick is None:
        add_todo(world, rng, monday)
        return "add a to-do"
    i = pick["id"]
    if kind == "edit":
        field_, value = rng.choice([("duration_min", rng.choice([15, 60, 180, 600])),
                                    ("importance", rng.randrange(1, 6)),
                                    ("due", local(monday + timedelta(days=rng.randrange(0, 14)), 17 * 60)),
                                    ("firmness", rng.choice(["hard", "soft"]))])  # fmt: skip
        world.try_do("edit", id=i, **{field_: value})
        return f"edit T{i} {field_}"
    if kind in ("done", "drop", "skip", "reopen"):
        target = rng.choice([x for x in items if x["status"] != "todo"] or [pick]) if kind == "reopen" else pick
        world.try_do(kind, id=target["id"])
        return f"{kind} T{target['id']}"
    if kind in ("pin", "lock"):
        day = (datetime.fromisoformat(now_local) + timedelta(days=rng.randrange(0, 6))).date()
        world.try_do(
            "pin",
            id=i,
            start=local(day, rng.randrange(8 * 60, 20 * 60, 15)),
            kind="locked" if kind == "lock" else "preferred",
        )
        return f"{kind} T{i}"
    if kind == "unpin":
        world.try_do("unpin", id=i)
        return f"unpin T{i}"
    if kind == "depend" and len(open_) > 1:
        other = rng.choice([x for x in open_ if x["id"] != i])
        world.try_do("depend", item_id=i, depends_on_id=other["id"])
        return f"T{i} waits for T{other['id']}"
    if kind == "time":
        world.try_do("start", id=i)
        world.later(rng.choice([10, 25, 50, 95]))
        world.try_do("stop", id=i, done=rng.random() < 0.3)
        return f"time T{i}"
    if kind == "progress":
        world.try_do("progress", id=i, share=rng.choice([0, 0.25, 0.5, 0.9]))
        return f"progress T{i}"
    if kind == "undo":
        done_ = world.conn.execute("SELECT MAX(id) FROM command_log").fetchone()[0]
        if done_:
            world.try_do("undo", command_id=done_)
        return "undo the last change"
    if kind == "pace":
        world.try_do("pace", name=rng.choice(["easy", "push", "normal"]), for_days=rng.choice([1, 2, 7]))
        return "pace"
    if kind == "break":
        day = (datetime.fromisoformat(now_local) + timedelta(days=rng.randrange(0, 10))).date()
        end = (day + timedelta(days=rng.randrange(0, 4))).isoformat()
        made = world.try_do("vacation_add", name="Break", start=day.isoformat(), end=end,
                            mode=rng.choice(["light", "off"]))  # fmt: skip
        if isinstance(made, dict) and rng.random() < 0.3:
            world.try_do("vacation_delete", id=made["vacation"]["id"])
        return "a break"
    if kind == "override":
        day = (datetime.fromisoformat(now_local) + timedelta(days=rng.randrange(0, 5))).date()
        world.try_do("day_override", date=day.isoformat(), wake=hhmm(rng.randrange(5 * 60, 10 * 60, 30)))
        return "a one-day wake time"
    if kind == "rule":
        world.try_do("rule_add", text=rng.choice(RULES), strength=rng.choice(["Always", "Prefer"]))
        return "a rule"
    if kind == "late":
        late = [x["item_id"] for x in world.do("status")["late_items"]]
        if late:
            world.try_do("late_accept", item_ids=late[:1])
        return "accept lateness"
    if kind == "tick":
        world.later(15)
        return TICK
    world.later(rng.choice([60, 180, 600, 1440]))
    return "time passes"


TICK = "15 minutes pass"


def deadlines_now(world: World) -> int:
    row = world.conn.execute("SELECT stage_values FROM plans ORDER BY id DESC LIMIT 1").fetchone()
    return int(json.loads(row["stage_values"])["deadlines"]) if row else 0


def tick_kept(before: int, after: int, step: str) -> list[str]:
    """Only the clock moved (the worker's tick): the plan may not get much worse (24 Nov, the user's Laundry: a tick at
    10:04pm saved a plan scoring 9.8 million against 186 thousand the tick before, then went back)."""
    if any(part != TICK for part in step.split("; ")):
        return []
    if after > before * 1.05 + 1000:
        return [f"a tick with nothing changed made the plan worse: deadlines {before:,} -> {after:,}"]
    return []


def checks(world: World, step: str, load: str = "usual") -> list[str]:
    """What the plan report doesn't already check: every page's query answers, the late lists agree, sleep is kept,
    and in a light week an ongoing project gets time."""
    out = []
    if load == "light":
        out += ongoing_get_time(world)
    for name, params in VIEWS:
        try:
            world.do(name, **params)
        except FieldError:
            pass
        except Exception as error:  # noqa: BLE001  (a crash is what this looks for)
            out.append(f"query {name} crashed: {type(error).__name__}: {error}")
    try:
        late = {i["title"] for i in world.do("status")["late_items"]}
        triage = set(world.do("triage")["late"])
        if late != triage:
            out.append(f"late lists disagree: Plan page {sorted(late)}, See options {sorted(triage)}")
    except Exception as error:  # noqa: BLE001
        out.append(f"late lists couldn't be compared: {error}")
    out += sleep_kept(world)
    return out


def ongoing_get_time(world: World) -> list[str]:
    """A light week has room: an ongoing project with three days or more of its week left gets some of them (24 Nov:
    asleep by day, one got none at all)."""
    out = []
    for o in world.do("ongoing_projects"):
        week = o.get("week")
        if not o["active"] or not week or week["planned_min"] + week["done_min"] > 0:
            continue
        left = datetime.fromisoformat(week["end"]) - datetime.fromisoformat(world.local(world.now))
        if left >= timedelta(days=3):
            out.append(f"{o['title']}: no time this week with {left.days} days of it left, in a light week")
    return out


def sleep_kept(world: World) -> list[str]:
    """No work planned inside a night's sleep, as the planner itself has the night (overrides kept; from bedtime plus
    the margin past it, which Settings → Schedule gives the plan), except what you pinned there, what runs by itself,
    and break days (a break may plan its own sleep)."""
    from friday.core.settings import minutes_of
    from friday.core.time import parse_utc
    from friday.planner.build import night_times
    from friday.planner.snapshot import day_overrides
    from friday.planner.store import load_settings

    settings = load_settings(world.conn)
    overrides = day_overrides(world.conn, 1)
    plan = world.do("plan", start=world.local(world.now), end=world.local(world.now + 7 * 1440))
    breaks = {
        d["date"] for d in world.do("calendar", start=world.local(world.now)[:10], days=8)["days"] if d.get("vacation")
    }
    day_start = minutes_of(settings["time"].day_start)
    out = []
    first = datetime.fromisoformat(world.local(world.now)).date() - timedelta(days=1)
    planner = getattr(getattr(world, "problem", None), "nights", {})
    fixed = [
        parse_utc(r[0])
        for r in world.conn.execute(  # classes and events (the to-do list hasn't them)
            "SELECT start_utc FROM items WHERE when_kind = 'fixed' AND status = 'todo' AND start_utc IS NOT NULL"
        )
    ]
    nights = []
    for n in range(9):
        d = first + timedelta(days=n)
        try:
            bed, wake, margin = night_times(settings, overrides, d, world.tz, day_start)
        except Exception:  # noqa: BLE001,S112  (a night the setting has no times for: nothing to check)
            continue
        night = planner.get(d)
        if night is not None and night.wake_utc < wake:
            # woken early for an event you go to (planner.build.early_event): one must start then, within the
            # morning's routine of the new wake (24 Nov: day sleepers' worlds had work inside their sleep, all of it
            # after an event the planner had rightly woken them for; the check now knows, and checks the reason)
            if not any(night.wake_utc <= start <= night.wake_utc + 180 for start in fixed):
                out.append(f"the night of {d} ends at {world.local(night.wake_utc)}, before {world.local(wake)}, "
                           "with no event to get up for")  # fmt: skip
            wake = night.wake_utc
        nights.append((d, bed + margin, wake))  # the margin past bedtime is the plan's to use (Settings → Schedule)
    for b in plan["blocks"]:
        if b.get("background") or b.get("pinned") or b.get("state"):
            continue
        lo, hi = parse_utc(world_utc(world, b["start"])), parse_utc(world_utc(world, b["end"]))
        for d, bed, wake in nights:
            if d.isoformat() in breaks or (d + timedelta(days=1)).isoformat() in breaks:
                continue
            if lo < wake and bed < hi:
                out.append(
                    f"T{b['item_id']} {b['start']}–{b['end']} inside the night of {d} "
                    f"({world.local(bed)}–{world.local(wake)})"
                )
    return out


def world_utc(world: World, local_text: str) -> str:
    from friday.core.time import format_utc, parse_local, to_utc

    return format_utc(to_utc(parse_local(local_text), world.tz))


def fingerprint(world: World) -> dict[str, Any]:
    plan = world.do("plan", start=world.local(world.now), end=world.local(world.now + 7 * 1440))
    titles = {i["id"]: i["title"] for i in world.do("items", status="all")}
    return {"blocks": sorted(f"{titles.get(b['item_id'], b['item_id'])}|{b['start']}|{b['end']}" for b in plan["blocks"]
                             if not b.get("state")),
            "late": sorted(f"{i['title']}|{i['hours']}" for i in world.do("status")["late_items"])}  # fmt: skip


def play(seed: int, changes: int = 30) -> Outcome:
    """One world, start to end; nothing raised: what went wrong is in the outcome."""
    rng = random.Random(seed)
    out = Outcome(seed)
    with isolated() as folder:
        monday = date.fromisoformat(rng.choice(STARTS))
        tz = rng.choice(ZONES)
        try:
            world = World.fresh(folder, f"seed{seed}", f"{monday}T{hhmm(rng.randrange(7 * 60, 22 * 60, 30))}", tz=tz,
                                horizon_days=rng.choice([7, 14, 21]))  # fmt: skip
            load, sleeper = pick(rng, LOAD_ODDS), pick(rng, SLEEPERS)
            out.world = {"zone": tz, "load": load, "sleep": sleeper}
            world.do("settings_set", key="sleep", value=settings_of(rng, sleeper))
            build(world, rng, monday, load)
            step = "the starting week"
            for n in range(changes + 1):
                before = deadlines_now(world) if n else 0
                record = world.replan(step)
                found = [*record.issues, *checks(world, step, load)]
                if n:
                    found += tick_kept(before, deadlines_now(world), step)
                out.issues += [{"seed": seed, "step": n, "after": step, **out.world, "issue": i} for i in found]
                out.fingerprints.append({"seed": seed, "step": n, "after": step, **fingerprint(world)})
                out.steps = n
                if n < changes:
                    # several changes before Friday plans again, as when you're quick (the user, 24 Nov: "varying
                    # input speeds"): the plan must come out right from any pile of changes, not only one at a time
                    burst = rng.choice([1, 1, 1, 2, 3, 6])
                    step = "; ".join(change(world, rng, monday) for _ in range(burst))
        except Exception as error:  # noqa: BLE001
            out.issues.append({"seed": seed, "step": out.steps, "after": "?", "zone": tz, **out.world,
                               "issue": f"crash: {type(error).__name__}: {error}",
                               "trace": traceback.format_exc()[-1500:]})  # fmt: skip
    return out


def seeds_of(text: str) -> list[int]:
    out = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    return out


def compare(old: Path, new: Path) -> int:
    """The same seeds' plans on two versions: each step where they differ, and how much."""

    def load(d: Path) -> dict[tuple[int, int], dict]:
        return {(r["seed"], r["step"]): r for r in map(json.loads, (d / "fingerprints.jsonl").read_text().splitlines())}

    a, b = load(old), load(new)
    common = sorted(set(a) & set(b))
    differ = [k for k in common if a[k]["blocks"] != b[k]["blocks"] or a[k]["late"] != b[k]["late"]]
    late_changed = [k for k in common if a[k]["late"] != b[k]["late"]]
    print(f"{len(common)} plans compared: {len(differ)} differ, {len(late_changed)} with different late work")
    for k in late_changed[:20]:
        print(f"  seed {k[0]} step {k[1]} after {b[k]['after']!r}: late {a[k]['late']} → {b[k]['late']}")
    return 0


def main() -> int:
    # 3 search chains unless said: the planner runs one a performance core, so the same seed planned differently on
    # debian's 8 cores than on a Mac, and two runs compared on different machines differed for that alone (25 Nov)
    os.environ.setdefault("FRIDAY_CHAINS", "3")
    # and a fixed effort, as the screen and browser tests: the deadline solver runs to a budget of work, not seconds
    # (engine/cpsat_deadlines.py), so a busy machine plans the same week the same way. Without it two runs of the same
    # code differed by hundreds of late hours in the overloaded worlds, as much as the changes being compared (26 Nov)
    os.environ.setdefault("FRIDAY_FIXED_EFFORT", "1")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0-49")
    parser.add_argument("--changes", type=int, default=30)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args()
    if args.compare:
        return compare(*args.compare)
    seeds = seeds_of(args.seeds)
    with ProcessPoolExecutor(args.jobs) as pool:
        outcomes = list(pool.map(play, seeds, [args.changes] * len(seeds)))
    issues = [i for o in outcomes for i in o.issues]
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "issues.json").write_text(json.dumps(issues, indent=1))
        (args.out / "fingerprints.jsonl").write_text("\n".join(json.dumps(f) for o in outcomes for f in o.fingerprints))
    plans = sum(o.steps + 1 for o in outcomes)
    print(
        f"{len(seeds)} worlds, {plans} plans checked, {len(issues)} issues in {len({i['seed'] for i in issues})} worlds"
    )
    kinds: dict[str, int] = {}
    for i in issues:
        key = i["issue"].split(":")[0].split(" T")[0][:60]
        kinds[key] = kinds.get(key, 0) + 1
    for key, n in sorted(kinds.items(), key=lambda kv: -kv[1])[:25]:
        print(f"  {n:5d}  {key}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
