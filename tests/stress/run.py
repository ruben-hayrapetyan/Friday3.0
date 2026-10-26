"""Run the stress set and write what it found:

    PYTHONPATH=src:. nice -n 19 uv run python -m tests.stress.run --out DIR [--only students,synthetic,edges]
        [--sizes 20,60,150,300] [--seeds 3]

DIR gets replans.csv (one row per replan: scenario, change, sizes, each stage's seconds, what the solver did,
what the checks found), commands.csv (each command's own time and how many blocks it placed at once), issues.json
(every check that failed, by scenario) and summary.md. Each scenario is a fresh database in a temporary folder; one
that fails is recorded and the rest go on."""

import argparse
import csv
import json
import os
import platform
import statistics
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from tests.stress.harness import Command, Replan, World, isolated
from tests.stress.scenarios import EDGES, student, synthetic, week

STUDENTS = ("maya", "alex", "jordan", "elena", "priya", "daniel", "riley")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default="students,synthetic,edges")
    parser.add_argument("--sizes", default="20,60,150,300")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--match", default="", help="only scenarios whose name has this in it")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(","))
    jobs: list[tuple[str, Callable[[Path], World], Callable[[World], list[str]] | None, set[str] | None]] = []
    if "students" in only:
        jobs += [(f"student {k}", lambda f, k=k: student(f, k), None, None) for k in STUDENTS]
    if "synthetic" in only:
        for size in (int(s) for s in args.sizes.split(",")):
            for seed in range(args.seeds):
                for policy in ("done", "not_done") if seed == 0 else ("done",):
                    name = (
                        f"synthetic {size} tasks seed {seed} ({'plan again' if policy == 'not_done' else 'count done'})"
                    )
                    jobs.append(
                        (name, lambda f, n=name, s=size, d=seed, p=policy: synthetic(f, n, s, d, p), None, None)
                    )
    if "edges" in only:
        jobs += [(f"edge: {e.name}", e.build, e.check, e.steps) for e in EDGES]

    jobs = [j for j in jobs if args.match.lower() in j[0].lower()]
    replans: list[Replan] = []
    commands: list[Command] = []
    issues: dict[str, list[str]] = {}
    started, load = time.time(), os.getloadavg()
    with isolated() as folder:
        for n, (name, build, check, steps) in enumerate(jobs, 1):
            print(f"[{n}/{len(jobs)}] {name}", flush=True)
            found: list[str] = []
            world = None
            try:
                world = build(folder)
                world.name = name
                world.replan("cold", warm=False)
                if check is not None:
                    found += [f"expectation: {m}" for m in check(world)]
                week(world, steps, cold=False)
            except Exception as error:  # noqa: BLE001  (one scenario failing mustn't stop the rest)
                found.append(f"crash: {type(error).__name__}: {error}\n{traceback.format_exc(limit=6)}")
            if world is not None:
                replans += world.replans
                commands += world.commands
                found += world.errors
                for r in world.replans:
                    found += [f"[{r.step}] {i}" for i in r.issues]
                world.conn.close()
            if found:
                issues[name] = found
                print(f"    {len(found)} issue(s): {found[0][:160]}", flush=True)

    write_csv(
        args.out / "replans.csv",
        [asdict(r) | {"solver": json.dumps(r.solver), "issues": len(r.issues)} for r in replans],
    )
    write_csv(args.out / "commands.csv", [asdict(c) for c in commands])
    (args.out / "issues.json").write_text(json.dumps(issues, indent=2))
    summary = summarize(replans, commands, issues, time.time() - started, load, os.getloadavg())
    (args.out / "summary.md").write_text(summary)
    print(summary)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def spread(values: list[float]) -> str:
    if not values:
        return "—"
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return f"{statistics.median(ordered):.2f} / {p90:.2f} / {ordered[-1]:.2f}"


def family(name: str) -> str:
    return name.split(" ")[0].rstrip(":")


def bucket(n: int) -> str:
    for edge in (25, 75, 175, 350):
        if n <= edge:
            return f"≤{edge}"
    return ">350"


def summarize(replans: list[Replan], commands: list[Command], issues: dict[str, list[str]], took: float,
              load_before: tuple, load_after: tuple) -> str:  # fmt: skip
    lines = [
        "# Stress run",
        "",
        f"{len(replans)} replans and {len(commands)} commands over {len({r.scenario for r in replans})} scenarios in "
        f"{took / 60:.1f} min on {platform.machine()} ({os.cpu_count()} cores), nice 19, load {load_before[0]:.1f} → "
        f"{load_after[0]:.1f}. Times are seconds: median / 90th percentile / worst.",
        "",
        "## By change",
        "",
        "| change | n | whole replan | solve | fallback used |",
        "|---|---|---|---|---|",
    ]
    steps = sorted({r.step for r in replans}, key=lambda s: [r.step for r in replans].index(s))
    for step in steps:
        got = [r for r in replans if r.step == step]
        fell = sum(1 for r in got if str(r.solver.get("fallback", "none")) not in ("none", "None", ""))
        lines.append(
            f"| {step} | {len(got)} | {spread([r.total_s for r in got])} | {spread([r.solve_s for r in got])} "
            f"| {fell} |"
        )
    lines += [
        "",
        "## By size (open tasks)",
        "",
        "| open tasks | n | whole replan | overloaded share |",
        "|---|---|---|---|",
    ]
    for b in ("≤25", "≤75", "≤175", "≤350", ">350"):
        got = [r for r in replans if bucket(r.open_items) == b]
        if got:
            share = sum(r.overloaded for r in got) / len(got)
            lines.append(f"| {b} | {len(got)} | {spread([r.total_s for r in got])} | {share:.0%} |")
    lines += ["", "## Overloaded or not", "", "| plan | n | whole replan | solve |", "|---|---|---|---|"]
    for label, flag in (("everything fits", False), ("overloaded (something late)", True)):
        got = [r for r in replans if r.overloaded == flag]
        lines.append(
            f"| {label} | {len(got)} | {spread([r.total_s for r in got])} | {spread([r.solve_s for r in got])} |"
        )
    lines += ["", "## By family", "", "| family | n | whole replan |", "|---|---|---|"]
    for fam in sorted({family(r.scenario) for r in replans}):
        got = [r for r in replans if family(r.scenario) == fam]
        lines.append(f"| {fam} | {len(got)} | {spread([r.total_s for r in got])} |")
    stages = ("snapshot_s", "solve_s", "assemble_s", "save_s")
    lines += ["", "## Where the time goes (all replans)", ""]
    lines += [f"- {s.removesuffix('_s')}: {spread([getattr(r, s) for r in replans])}" for s in stages]
    quick = [c for c in commands if c.command in ("add", "edit", "done", "start", "stop")]
    lines += ["", "## What you see at once (the command and its quick placement, before the full replan)", ""]
    for name in ("add", "edit", "done", "start", "stop"):
        got = [c.seconds for c in quick if c.command == name]
        if got:
            lines.append(f"- {name}: {spread(got)} ({len(got)})")
    moved = [r.moved_share for r in replans if r.moved_share is not None]
    if moved:
        lines += ["", f"Stability: a replan with nothing changed moved {statistics.median(moved):.0%} of the plan "
                      f"(median; worst {max(moved):.0%})."]  # fmt: skip
    lines += ["", f"## Issues ({sum(len(v) for v in issues.values())} in {len(issues)} scenarios)", ""]
    for name, found in issues.items():
        lines.append(f"- **{name}**")
        lines += [f"  - {m.splitlines()[0][:220]}" for m in found[:8]]
        if len(found) > 8:
            lines.append(f"  - … {len(found) - 8} more")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
