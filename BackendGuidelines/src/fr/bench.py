"""Shared experiment helpers: seed sets, statistics, best-known references, gap metrics."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

TUNING_SEEDS = range(0, 100)
REPORT_SEEDS = range(1000, 1100)
ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "experiments" / "refs"


def boot_ci(x: Iterable[float], stat: Callable = np.median, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    x = np.asarray(list(x), dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    s = [stat(rng.choice(x, size=len(x))) for _ in range(n)]
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def summarize(x: Iterable[float]) -> dict:
    """median, IQR and 95% bootstrap CI of the median; the format every table in the report uses."""
    a = np.asarray(list(x), dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return dict(n=0, median=float("nan"), q25=float("nan"), q75=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"))
    lo, hi = boot_ci(a)
    return dict(n=len(a), median=float(np.median(a)), q25=float(np.percentile(a, 25)), q75=float(np.percentile(a, 75)),
                ci_lo=lo, ci_hi=hi)


def gap(value: float, best: float, floor: float = 1000.0) -> float:
    """Relative excess over the best known value. `floor` (10 points) keeps a best of 0 from exploding."""
    return (value - best) / max(abs(best), floor)


def load_refs(name: str) -> dict:
    f = REFS / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_refs(name: str, data: dict) -> None:
    REFS.mkdir(parents=True, exist_ok=True)
    (REFS / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True))


class Timer:
    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.s = time.perf_counter() - self.t
