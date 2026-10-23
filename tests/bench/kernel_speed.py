"""Kernel speed (DESIGN §24.5: ≥ 300k proposals per second per core). Run on an idle machine:

    uv run python -m tests.bench.kernel_speed

Appends one row per instance to tests/bench/results.csv.
"""

import csv
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from friday.core.settings import DEFAULT_MOVE_WEIGHTS
from friday.engine.chain import run_chain, sample_deltas
from friday.engine.compile import compile_problem
from friday.engine.kernel import N_MOVES, init_state, move_cumulative, new_state, protected_items
from tests.engine.golden import plan_of, problem, read

RESULTS = Path(__file__).with_name("results.csv")
INSTANCES = ("ref20-s0", "ref60-s0", "ref150-s0")
WEIGHTS = np.array([1e6, 1e3, 1.0])
STEPS = 1_000_000


def machine() -> str:
    try:
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout
    except OSError:
        chip = ""
    return (chip.strip() or platform.processor() or platform.machine()) + f" ({os.cpu_count()} cores)"


def temperatures(c, start: np.ndarray, protected: np.ndarray) -> tuple[float, float]:  # noqa: ANN001
    """T0 = 0.1 and T1 = 0.003 × the median |Δ| of 1,500 valid moves that leave the deadlines stage alone."""
    st = new_state(c.m)
    init_state(c.m, st, start)
    out = np.zeros((1500, 3), dtype=np.int64)
    work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
    k = sample_deltas(c.m, st, protected, WEIGHTS, move_cumulative(DEFAULT_MOVE_WEIGHTS), *work, 1500, 7, out)
    deltas = np.abs(out[:k][out[:k, 0] == 0][:, 1:] @ WEIGHTS[1:])
    median = float(np.median(deltas[deltas > 0])) if (deltas > 0).any() else 1.0
    return 0.1 * median, 0.003 * median


def chain_rate(name: str) -> tuple[int, float]:
    fixture = read(name)
    p = problem(fixture)
    c = compile_problem(p)
    start = c.owner_from_plan(plan_of(fixture["plans"][0], p))
    protected = protected_items(c.m, start)
    t0, t1 = temperatures(c, start, protected)
    st = new_state(c.m)
    init_state(c.m, st, start)
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    began = time.perf_counter()
    run_chain(c.m, st, protected, WEIGHTS, np.full(3, -1, dtype=np.int64), move_cumulative(DEFAULT_MOVE_WEIGHTS),
              np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64), STEPS, t0, t1, 1, 0.0, 0,
              st.owner.copy(), stats, np.zeros(3), np.zeros(1, dtype=np.int64))  # fmt: skip
    return len(p.items), STEPS / (time.perf_counter() - began)


def cache_load_seconds() -> float:
    """A fresh process loading the compiled kernel from its on-disk cache and running one chain step."""
    script = (
        "import time; t = time.perf_counter(); import tests.bench.kernel_speed as k; "
        "k.chain_rate_tiny(); print(time.perf_counter() - t)"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True).stdout
    return float(out.strip().splitlines()[-1])


def chain_rate_tiny() -> None:
    fixture = read("tiny-s0")
    p = problem(fixture)
    c = compile_problem(p)
    st = new_state(c.m)
    init_state(c.m, st, c.owner_from_plan(plan_of(fixture["plans"][0], p)))
    run_chain(c.m, st, np.zeros(c.m.I, dtype=bool), WEIGHTS, np.full(3, -1, dtype=np.int64),
              move_cumulative(DEFAULT_MOVE_WEIGHTS), np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64), 10,
              1.0, 1.0, 1, 0.0, 0, st.owner.copy(), np.zeros((N_MOVES, 3), dtype=np.int64), np.zeros(3),
              np.zeros(1, dtype=np.int64))  # fmt: skip


def main() -> None:
    chain_rate("tiny-s0")  # compile, or load from the cache, before timing
    load = os.getloadavg()[0]
    rows = []
    for name in INSTANCES:
        items, rate = chain_rate(name)
        rows.append([datetime.now(UTC).isoformat(timespec="minutes"), machine(), f"{load:.1f}", name, items, STEPS,
                     f"{rate:.0f}"])  # fmt: skip
        print(f"{name}: {items} items, {rate / 1000:.0f}k proposals/s")
    print(f"kernel load from the cache: {cache_load_seconds():.2f} s (load average {load:.1f})")
    new_file = not RESULTS.exists()
    with RESULTS.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["at_utc", "machine", "load_1m", "instance", "items", "steps", "proposals_per_s"])
        writer.writerows(rows)


if __name__ == "__main__":
    main()
