"""Learned durations (DESIGN §21.7): log minutes = μ + area + preset + kind + noise, each level's offsets drawn
from N(0, τ²), fitted by empirical Bayes. A kind seen twenty times stands on its own; one seen twice is pulled
toward its area and preset, the more so the less kinds differ in your history. Pure: numpy only; the kinds
(title clusters) are computed by the caller.

The fit alternates posterior means of the offsets given the variances (backfitting) with the variances given the
offsets and their posterior variances (an EM step for crossed random effects).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

LEVELS = ("area", "preset", "kind")
Z80 = 0.8416  # the standard normal's 80th percentile


@dataclass(frozen=True)
class Done:
    minutes: float
    area: str | None
    preset: str | None
    kind: str


@dataclass
class Model:
    mu: float
    sigma2: float
    tau2: dict[str, float]  # per level
    offsets: dict[str, dict[str, float]] = field(default_factory=dict)  # level → value → posterior mean
    variances: dict[str, dict[str, float]] = field(default_factory=dict)  # level → value → posterior variance
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    n: int = 0

    def predict(self, area: str | None, preset: str | None, kind: str | None) -> tuple[float, float]:
        """Posterior predictive mean and sd of log minutes."""
        mean, var = self.mu, self.sigma2
        for level, value in zip(LEVELS, (area, preset, kind), strict=True):
            if value is not None and value in self.offsets.get(level, {}):
                mean += self.offsets[level][value]
                var += self.variances[level][value]
            else:
                var += self.tau2[level]
        return mean, float(np.sqrt(var))

    def minutes(self, area: str | None, preset: str | None, kind: str | None, cautious: bool) -> float:
        """p50, or p80 for work that mustn't be squeezed."""
        mean, sd = self.predict(area, preset, kind)
        return float(np.exp(mean + (Z80 * sd if cautious else 0.0)))

    def to_json(self) -> dict:
        return {"mu": self.mu, "sigma2": self.sigma2, "tau2": self.tau2, "offsets": self.offsets,
                "variances": self.variances, "counts": self.counts, "n": self.n}  # fmt: skip

    @staticmethod
    def from_json(data: dict) -> "Model":
        return Model(**data)


def key(done: Done, level: str) -> str | None:
    return getattr(done, level)


def fit(rows: Sequence[Done], rounds: int = 30) -> Model:
    y = np.log(np.array([max(1.0, r.minutes) for r in rows]))
    mu = float(y.mean())
    sigma2 = float(max(y.var(), 0.01))
    tau2 = dict.fromkeys(LEVELS, sigma2 / 2)
    groups = {level: defaultdict(list) for level in LEVELS}
    for i, r in enumerate(rows):
        for level in LEVELS:
            if key(r, level) is not None:
                groups[level][key(r, level)].append(i)
    offsets = {level: dict.fromkeys(groups[level], 0.0) for level in LEVELS}
    variances = {level: dict.fromkeys(groups[level], 0.0) for level in LEVELS}
    for _ in range(rounds):
        effect = np.zeros(len(rows))
        for level in LEVELS:
            for value, idx in groups[level].items():
                effect[idx] += offsets[level][value]
        for level in LEVELS:
            for value, idx in groups[level].items():
                rest = y[idx] - mu - (effect[idx] - offsets[level][value])
                precision = len(idx) / sigma2 + 1 / tau2[level]
                new = float(rest.sum() / sigma2 / precision)
                effect[idx] += new - offsets[level][value]
                offsets[level][value], variances[level][value] = new, 1 / precision
        mu = float((y - effect).mean())
        residual = y - mu - effect
        posterior = sum(variances[level][key(r, level)] for r in rows for level in LEVELS if key(r, level) is not None)
        sigma2 = float(max((np.sum(residual**2) + posterior) / len(rows), 1e-3))
        for level in LEVELS:
            if offsets[level]:
                values = np.array(list(offsets[level].values())) ** 2 + np.array(list(variances[level].values()))
                tau2[level] = float(max(values.mean(), 1e-3))
    counts = {level: {v: len(idx) for v, idx in groups[level].items()} for level in LEVELS}
    return Model(mu, sigma2, tau2, offsets, variances, counts, len(rows))


def abs_log_error(predicted: Sequence[float], actual: Sequence[float]) -> float:
    """The median absolute log error: 0.1 means typically about 10% off."""
    p, a = np.log(np.maximum(predicted, 1.0)), np.log(np.maximum(actual, 1.0))
    return float(np.median(np.abs(p - a))) if len(p) else float("inf")
