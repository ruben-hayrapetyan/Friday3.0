"""Allocator, `now()` and provisional placement times (DESIGN §24.5: allocator ≤ 1 s; the other two ≤ 50 ms at 100
items). Run on an idle machine:

    PYTHONPATH=src:. uv run python -m tests.bench.allocator_executor_speed

Appends one row per instance to tests/bench/results_allocator_executor.csv.
"""

import csv
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from friday.engine.allocator import allocate
from friday.engine.construct import prepare_start
from friday.engine.executor import now, provisional_plan
from friday.planner.inputs import allocator_input, executor_input, now_settings
from tests.bench.generator import Scenario, many_dependencies, reference_instance
from tests.bench.kernel_speed import machine

RESULTS = Path(__file__).with_name("results_allocator_executor.csv")
FIELDS = ["at_utc", "machine", "load_1m", "case", "seed", "items", "allocator_s", "now_ms", "provisional_ms"]


def measure(sc: Scenario) -> tuple[int, float, float, float]:
    p = sc.build()
    inp = sc.build_input()
    began = time.perf_counter()
    allocate(allocator_input(inp, p))
    allocator_s = time.perf_counter() - began
    start = prepare_start(p)
    plan = start.c.plan_from_owner(start.owner)
    began = time.perf_counter()
    now(p, plan, executor_input(inp, p), now_settings(sc.settings))
    now_ms = (time.perf_counter() - began) * 1000
    changed = set(list(p.items)[:3])
    began = time.perf_counter()
    provisional_plan(p, plan, changed)
    provisional_ms = (time.perf_counter() - began) * 1000
    return len(p.items), allocator_s, now_ms, provisional_ms


def main() -> None:
    cases = [("ref100", s, reference_instance(100, s)) for s in range(10)]
    cases += [("ref150", s, reference_instance(150, s)) for s in range(10)]
    cases += [("deps", s, many_dependencies(s)) for s in range(10)]
    rows = []
    for name, seed, sc in cases:
        items, allocator_s, now_ms, provisional_ms = measure(sc)
        rows.append({"at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M+00:00"), "machine": machine(),
                     "load_1m": round(os.getloadavg()[0], 1), "case": name, "seed": seed, "items": items,
                     "allocator_s": round(allocator_s, 3), "now_ms": round(now_ms, 1),
                     "provisional_ms": round(provisional_ms, 1)})  # fmt: skip
        print(f"{name:>7} s{seed}: {items} items, allocator {allocator_s:.3f} s, now {now_ms:.1f} ms, "
              f"provisional {provisional_ms:.1f} ms")  # fmt: skip
    for key, unit in (("allocator_s", "s"), ("now_ms", "ms"), ("provisional_ms", "ms")):
        values = sorted(r[key] for r in rows)
        print(f"{key}: p50 {values[len(values) // 2]} {unit}, worst {values[-1]} {unit}")
    new_file = not RESULTS.exists()
    with RESULTS.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
