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


def update_best(name: str, lex: tuple[int, int, int], source: str) -> bool:
    """Record `lex` as the best known value of instance `name` if it beats the stored one (lexicographic)."""
    refs = load_refs("best_known")
    cur = refs.get(name)
    if cur is None or tuple(lex) < tuple(cur["lex"]):
        refs[name] = dict(lex=[int(v) for v in lex], source=source)
        save_refs("best_known", refs)
        return True
    return False


def best_known(name: str) -> tuple[int, int, int] | None:
    cur = load_refs("best_known").get(name)
    return None if cur is None else tuple(cur["lex"])


def lex_gaps(lex: tuple[int, int, int], best: tuple[int, int, int]) -> dict:
    """Per-stage gaps in lexicographic reading: a stage is only compared when the stages before it match the best.

    Returns late_gap (absolute scaled points), wellbeing_gap and preferences_gap (relative, floor 1000), the last two
    NaN when an earlier stage is already worse (the comparison would not mean anything).
    """
    nan = float("nan")
    late_gap = lex[0] - best[0]
    w = gap(lex[1], best[1]) if lex[0] <= best[0] else nan
    p = gap(lex[2], best[2]) if (lex[0] <= best[0] and lex[1] <= best[1]) else nan
    return dict(late_gap=late_gap, wellbeing_gap=w, preferences_gap=p)
