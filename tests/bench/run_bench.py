"""The scheduler benchmark (DESIGN §24.5). Run on an idle machine for the M3 gate:

    PYTHONPATH=src:. uv run python -m tests.bench.run_bench            # the full set
    PYTHONPATH=src:. uv run python -m tests.bench.run_bench --quick    # two seeds per case

Appends one row per solve to tests/bench/results_scheduler.csv and prints a summary against the targets.
"""

import argparse
import csv
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from friday.core.settings import DEFAULTS
from friday.engine.checker import check
from friday.engine.construct import construct, prepare_start
from friday.engine.cpsat_deadlines import DeadlineModel
from friday.engine.evaluate import evaluate
from friday.engine.scheduler import Schedule, schedule
from friday.planner.build import id_of, scheduler_config
from tests.bench.generator import ADVERSARIAL, Scenario, reference_instance, warm_variant
from tests.bench.kernel_speed import machine

RESULTS = Path(__file__).with_name("results_scheduler.csv")
SIZES = (20, 40, 60, 150)
COLUMNS = ["at_utc", "machine", "load_1m", "case", "seed", "items", "kind", "chains", "steps", "construct_s",
           "construct_only_ms", "repair_s", "fallback_s", "anneal_s", "total_s", "deadlines", "wellbeing",
           "preferences", "late_items", "fallback", "valid", "lateness"]  # fmt: skip
PROOF_SECONDS = 60.0


def previous_blocks(p, result: Schedule) -> dict[int, list[tuple[int, int]]]:  # noqa: ANN001
    return {id_of(k): [(int(p.grid.start[s]), int(p.grid.end[s])) for s in slots] for k, slots in result.plan.items()}


def construct_only_ms(p) -> float:  # noqa: ANN001
    start = prepare_start(p)
    began = time.perf_counter()
    construct(start.c)
    return (time.perf_counter() - began) * 1000


def row(case: str, seed: int, kind: str, p, result: Schedule, load: float) -> list:  # noqa: ANN001
    sv, s = result.stage_values, result.seconds
    return [datetime.now(UTC).isoformat(timespec="minutes"), machine(), f"{load:.1f}", case, seed, len(p.items), kind,
            result.chains, result.steps_per_chain, f"{s['construct']:.3f}", f"{construct_only_ms(p):.1f}",
            f"{s['repair']:.3f}", f"{s['fallback']:.3f}", f"{s['anneal']:.3f}", f"{s['total']:.3f}", sv["deadlines"],
            sv["wellbeing"], sv["preferences"], len(result.evaluation.deadline_misses), result.fallback,
            int(check(p, result.plan, result.protected) == []), lateness_class(p, result, case)]  # fmt: skip


def lateness_class(p, result: Schedule, case: str) -> str:  # noqa: ANN001
    """For a late plan, a long CP-SAT solve says whether zero was possible (avoidable: a gate failure), whether
    the plan is the least lateness possible (unavoidable), or that less was possible (above-optimum)."""
    late = result.stage_values["deadlines"]
    if late == 0:
        return "none"
    if case == "overload":
        return "overload"
    proof = DeadlineModel(p).solve(result.plan, PROOF_SECONDS, 8)
    best = evaluate(p, proof.plan).stage_values["deadlines"] if proof.plan else None
    if best == 0:
        return "avoidable"
    if best is not None and best < late:
        return f"above-optimum:{best}" if proof.status == "OPTIMAL" else f"above-best-known:{best}"
    return "unavoidable" if proof.status == "OPTIMAL" else f"unknown:{proof.status.lower()}"


def cases(seeds: range) -> list[tuple[str, int, Scenario]]:
    out = [(f"ref{n}", s, reference_instance(n, s)) for n in SIZES for s in seeds]
    return out + [(name, s, make(s)) for name, make in ADVERSARIAL.items() for s in seeds]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--only", nargs="*", help="case:seed pairs to run, e.g. ref40:7 tight:3")
    args = parser.parse_args()
    seeds = range(2) if args.quick else range(10)
    config = scheduler_config(DEFAULTS)
    schedule(reference_instance(20, 0).build(), config)  # load the kernel before timing
    rows = []
    chosen = {tuple(x.split(":")) for x in args.only} if args.only else None
    for case, seed, sc in cases(seeds):
        if chosen is not None and (case, str(seed)) not in chosen:
            continue
        load = os.getloadavg()[0]
        p = sc.build()
        cold = schedule(p, config)
        rows.append(row(case, seed, "cold", p, cold, load))
        warm_sc = warm_variant(sc, seed)
        q = warm_sc.build(current=previous_blocks(p, cold))
        warm = schedule(q, config, warm=True)
        rows.append(row(case, seed, "warm", q, warm, os.getloadavg()[0]))
        print(f"{case:>10} s{seed}: cold {cold.seconds['total']:.2f}s warm {warm.seconds['total']:.2f}s "
              f"late {len(cold.evaluation.deadline_misses)} fallback {cold.fallback}", flush=True)  # fmt: skip
    write(rows)
    summarize(rows)


def write(rows: list[list]) -> None:
    new_file = not RESULTS.exists()
    with RESULTS.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(COLUMNS)
        writer.writerows(rows)


def summarize(rows: list[list]) -> None:
    col = {name: k for k, name in enumerate(COLUMNS)}
    p90 = lambda xs: float(np.percentile(xs, 90)) if xs else float("nan")  # noqa: E731
    for case in sorted({r[col["case"]] for r in rows}):
        for kind in ("cold", "warm"):
            times = [float(r[col["total_s"]]) for r in rows if r[col["case"]] == case and r[col["kind"]] == kind]
            if times:
                print(f"{case:>10} {kind}: p50 {np.median(times):.2f}s p90 {p90(times):.2f}s")
    invalid = sum(1 for r in rows if not r[col["valid"]])
    avoidable = [(r[col["case"]], r[col["seed"]], r[col["kind"]]) for r in rows if r[col["lateness"]] == "avoidable"]
    above = [(r[col["case"]], r[col["seed"]], r[col["kind"]], r[col["lateness"]]) for r in rows
             if r[col["lateness"]].startswith(("above", "unknown"))]  # fmt: skip
    unavoidable = sum(1 for r in rows if r[col["lateness"]] == "unavoidable")
    construct_150 = max([float(r[col["construct_only_ms"]]) for r in rows if r[col["case"]] == "ref150"] or [0.0])
    print(f"invalid plans: {invalid}; avoidable lateness: {avoidable or 'none'}; late and optimal: {unavoidable}; "
          f"late above the optimum or unproven: {above or 'none'}; construction at 150 items, worst "
          f"{construct_150:.0f} ms")  # fmt: skip
    cold60 = [float(r[col["total_s"]]) for r in rows if r[col["case"]] == "ref60" and r[col["kind"]] == "cold"]
    warm60 = [float(r[col["total_s"]]) for r in rows if r[col["case"]] == "ref60" and r[col["kind"]] == "warm"]
    print(f"targets: cold 60 p90 {p90(cold60):.2f}s (≤ 3), warm 60 p90 {p90(warm60):.2f}s (≤ 1), "
          f"construction {construct_150:.0f} ms (≤ 50)")  # fmt: skip
    sys.stdout.flush()


if __name__ == "__main__":
    main()
