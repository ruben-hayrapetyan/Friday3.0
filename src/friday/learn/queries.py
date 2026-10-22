"""Which comparison to ask (DESIGN §21.4), ported from the research's `system.py` (`select`): query-by-committee.

Six bootstrap fits of the preference model vote on each candidate pair; the pair they split on most is asked, ties
broken by how close the pair is to a draw under the current weights. Before there are 10 answers there is no
committee: the pair closest to a draw is asked (uncertainty sampling). Asking stops when even the committee's top
pair splits it less than `stop_below`.
"""

from collections.abc import Sequence

import numpy as np

from friday.learn.preferences import Comparison, bt_fit, design

COMMITTEE = 6
COMMITTEE_FROM = 10


def committee(comparisons: Sequence[Comparison], rules: Sequence[str], seed: int = 0) -> list[np.ndarray]:
    """θ of each bootstrap copy, or none before there are enough answers."""
    if len(comparisons) < COMMITTEE_FROM:
        return []
    d = len(rules)
    x, weight = design(comparisons, rules)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(COMMITTEE):
        pick = rng.integers(0, len(x), len(x))
        out.append(bt_fit(x[pick], np.ones(d), np.ones(d), np.full(d, 0.02), weight[pick]))
    return out


def vector(features: dict[str, float], rules: Sequence[str]) -> np.ndarray:
    return np.array([features.get(r, 0.0) for r in rules])


def disagreement(members: list[np.ndarray], a: dict[str, float], b: dict[str, float], rules: Sequence[str]) -> float:
    """How split the committee is on A against B: 1 when half prefer each, 0 when all agree."""
    diff = vector(a, rules) - vector(b, rules)
    if not members or np.abs(diff).sum() < 1e-12:
        return 0.0
    share = float(np.mean([(theta @ diff) < 0 for theta in members]))  # members preferring A
    return 4 * share * (1 - share)


def choose(
    candidates: Sequence[tuple[dict[str, float], dict[str, float]]],
    comparisons: Sequence[Comparison],
    rules: Sequence[str],
    theta: dict[str, float] | None = None,
    stop_below: float = 0.2,
    seed: int = 0,
) -> int | None:
    """The candidate pair to ask, or None: no pair differs, or the committee agrees on all of them."""
    members = committee(comparisons, rules, seed)
    current = vector(theta or {}, rules) if theta else np.ones(len(rules))
    scored = []
    for k, (a, b) in enumerate(candidates):
        diff = vector(a, rules) - vector(b, rules)
        size = np.abs(diff).sum()
        if size < 1e-12:
            continue
        scored.append((-disagreement(members, a, b, rules), abs(float(current @ diff)) / size, k))
    if not scored:
        return None
    split, _, best = min(scored)
    return None if members and -split < stop_below else best
