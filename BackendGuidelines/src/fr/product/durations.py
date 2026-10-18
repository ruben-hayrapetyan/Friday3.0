"""Predicting how long a task will take from the user's preliminary estimate and recorded actual lengths (RQ11, RQ12).

Every model returns a log-normal predictive distribution N(m, s^2) over log minutes. The hierarchical models follow
ENGINE_REFERENCE section 11 (item kind -> course -> all, partial pooling): two Bayesian ridge regressions with
group-level priors, one for the *ratio* actual / estimate (used when the user gave an estimate) and one for the length
itself (used when they did not, or fused with the first). Old evidence can fade (a half-life in weeks), so a drifting
habit is followed. With no data every model returns the user's own estimate: the preliminary predictions are the start.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm

# population defaults (minutes) Friday ships with, for tasks with no estimate and no history
POPULATION = {"pset": 240.0, "reading": 80.0, "essay": 300.0, "lab": 180.0, "exam_prep": 360.0, "project": 600.0,
              "email": 15.0, "other": 90.0}


@dataclass
class Obs:
    course: str | None
    kind: str
    est: float | None  # minutes
    actual: float  # minutes
    week: float


class Model:
    name = "model"

    def predict(self, course: str | None, kind: str, est: float | None, week: float) -> tuple[float, float]:
        raise NotImplementedError

    def observe(self, o: Obs) -> None:
        pass


class AsGiven(Model):
    """The user's estimate, with a fixed spread; population defaults without one. Never learns."""

    name = "as_given"

    def __init__(self, sigma: float = 0.35, sigma_none: float = 0.6):
        self.sigma, self.sigma_none = sigma, sigma_none

    def predict(self, course, kind, est, week):
        if est:
            return math.log(est), self.sigma
        return math.log(POPULATION.get(kind, POPULATION["other"])), self.sigma_none


@dataclass
class _Ridge:
    """Bayesian linear regression with a diagonal Gaussian prior and a shared noise variance (estimated)."""

    mu0: np.ndarray
    tau: np.ndarray
    sigma0: float = 0.35
    n0: float = 4.0
    X: list = field(default_factory=list)
    y: list = field(default_factory=list)
    t: list = field(default_factory=list)
    _cache: tuple | None = None

    def add(self, x: np.ndarray, y: float, t: float) -> None:
        self.X.append(x)
        self.y.append(y)
        self.t.append(t)
        self._cache = None

    def fit(self, now: float, half_life: float | None):
        key = (now if half_life else None, len(self.y))
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1:]
        P = 1.0 / self.tau ** 2
        if not self.y:
            out = (self.mu0.copy(), np.diag(self.tau ** 2), self.sigma0 ** 2)
            self._cache = (key,) + out
            return out
        X, y = np.array(self.X), np.array(self.y)
        w = np.ones(len(y)) if not half_life else 0.5 ** ((now - np.array(self.t)) / half_life)
        s2 = self.sigma0 ** 2
        for _ in range(3):
            A = X.T @ (X * w[:, None]) / s2 + np.diag(P)
            b = X.T @ (w * y) / s2 + P * self.mu0
            cov = np.linalg.inv(A)
            mean = cov @ b
            r = y - X @ mean
            s2 = (self.n0 * self.sigma0 ** 2 + float(np.sum(w * r ** 2))) / (self.n0 + float(np.sum(w)))
        out = (mean, cov, s2)
        self._cache = (key,) + out
        return out

    def predict(self, x: np.ndarray, now: float, half_life: float | None) -> tuple[float, float]:
        mean, cov, s2 = self.fit(now, half_life)
        return float(x @ mean), math.sqrt(s2 + float(x @ cov @ x))


class Hier(Model):
    """Partial pooling over (all, kind, course, course x kind) for the log ratio actual / estimate and the log length.

    levels: group effects of the ratio model ("kind", "course", "ck"); the length model always has at least kind effects
    (it starts from the population defaults per kind). fuse: with an estimate, combine the ratio prediction with the
    length prediction (precision-weighted), which shrinks noisy estimates toward the user's history. half_life: weeks
    after which an observation counts half (None = never fades). bias_prior: prior mean of log(actual / estimate)."""

    def __init__(self, kinds, courses, levels=("kind", "course", "ck"), fuse=False, half_life=None, bias_prior=0.0,
                 tau_bias=(0.5, 0.3, 0.2, 0.15), tau_len=(0.3, 0.5, 0.3, 0.2), sigma0=0.35, trend=False,
                 tau_trend=0.05, fuse_after=0, name=None):
        self.kinds, self.courses = list(kinds), list(courses) + [None]
        self.trend = trend
        self.fuse_after = fuse_after  # E020 round 3: fuse only once this many lengths are recorded (cold start = estimate)
        self.levels = tuple(levels)
        self.len_levels = tuple(sorted(set(levels) | {"kind"}, key=["kind", "course", "ck"].index))
        self.fuse, self.half_life = fuse, half_life
        self.name = name or "hier"
        mu = np.zeros(self._dim(self.levels))
        mu[0] = bias_prior
        self.ratio = _Ridge(mu, self._taus(tau_bias, self.levels), sigma0)
        mu = np.zeros(self._dim(self.len_levels))
        for i, k in enumerate(self.kinds):  # the length model starts at the population default for each kind
            mu[1 + i] = math.log(POPULATION.get(k, POPULATION["other"]))
        taus = self._taus(tau_len, self.len_levels)
        if trend:  # lengths change over the term (harder material): one slope per week, prior N(0, tau_trend^2)
            mu, taus = np.append(mu, 0.0), np.append(taus, tau_trend)
        self.length = _Ridge(mu, taus, sigma0 * 1.5)

    def xl(self, course, kind, week) -> np.ndarray:
        v = self.x(course, kind, self.len_levels)
        return np.append(v, week) if self.trend else v

    def _sizes(self, levels) -> list[int]:
        size = {"kind": len(self.kinds), "course": len(self.courses), "ck": len(self.kinds) * len(self.courses)}
        return [size[lv] for lv in levels]

    def _dim(self, levels) -> int:
        return 1 + sum(self._sizes(levels))

    def _taus(self, tau, levels) -> np.ndarray:
        ix = {"kind": 1, "course": 2, "ck": 3}
        t = [tau[0]]
        for lv, n in zip(levels, self._sizes(levels)):
            t += [tau[ix[lv]]] * n
        return np.array(t)

    def x(self, course, kind, levels) -> np.ndarray:
        v = np.zeros(self._dim(levels))
        v[0] = 1.0
        o = 1
        ki = self.kinds.index(kind) if kind in self.kinds else None
        ci = self.courses.index(course) if course in self.courses else len(self.courses) - 1
        for lv, n in zip(levels, self._sizes(levels)):
            if lv == "kind" and ki is not None:
                v[o + ki] = 1.0
            elif lv == "course":
                v[o + ci] = 1.0
            elif lv == "ck" and ki is not None:
                v[o + ki * len(self.courses) + ci] = 1.0
            o += n
        return v

    def observe(self, o: Obs) -> None:
        if o.est:
            self.ratio.add(self.x(o.course, o.kind, self.levels), math.log(o.actual) - math.log(o.est), o.week)
        self.length.add(self.xl(o.course, o.kind, o.week), math.log(o.actual), o.week)

    def predict(self, course, kind, est, week):
        ml, sl = self.length.predict(self.xl(course, kind, week), week, self.half_life)
        if not est:
            return ml, sl
        mr, sr = self.ratio.predict(self.x(course, kind, self.levels), week, self.half_life)
        mr += math.log(est)
        if not self.fuse or len(self.length.y) < self.fuse_after:
            return mr, sr
        wr, wl = 1 / sr ** 2, 1 / sl ** 2
        return (wr * mr + wl * ml) / (wr + wl), math.sqrt(1 / (wr + wl))


class Oracle(Model):
    """Reference only: the simulator substitutes the true length (see sim.term)."""

    name = "oracle"
    oracle = True

    def predict(self, course, kind, est, week):
        raise RuntimeError("the oracle is resolved by the simulator")


class Recalibrated(Model):
    """Online recalibration of any model from its own one-step-ahead errors: before each recorded length is learned,
    the model's current prediction for that task is scored; the running mean error shifts later medians and the running
    RMS of standardized errors scales later spreads (both shrunk toward no change by `n0` pseudo-observations)."""

    def __init__(self, inner: Model, n0: float = 5.0, name: str | None = None):
        self.inner, self.n0 = inner, n0
        self.name = name or inner.name + "_recal"
        self.res: list[float] = []
        self.z2: list[float] = []

    def _adj(self) -> tuple[float, float]:
        n = len(self.res)
        shift = sum(self.res) / (self.n0 + n)
        k = math.sqrt((self.n0 + sum(self.z2)) / (self.n0 + n))
        return shift, k

    def predict(self, course, kind, est, week):
        m, s = self.inner.predict(course, kind, est, week)
        shift, k = self._adj()
        return m + shift, s * k

    def observe(self, o: Obs) -> None:
        m, s = self.inner.predict(o.course, o.kind, o.est, o.week)
        shift, _ = self._adj()
        r = math.log(o.actual) - m
        self.res.append(r)
        self.z2.append(((r - shift) / s) ** 2)
        self.inner.observe(o)


class Knn(Model):
    """Mean log ratio of the k most recent finished tasks of the same course and kind (then kind, then all)."""

    name = "knn"

    def __init__(self, k: int = 4, sigma_min: float = 0.2):
        self.k, self.sigma_min = k, sigma_min
        self.obs: list[Obs] = []

    def observe(self, o: Obs) -> None:
        self.obs.append(o)

    def predict(self, course, kind, est, week):
        for pick in (lambda o: o.course == course and o.kind == kind, lambda o: o.kind == kind, lambda o: True):
            pool = [o for o in self.obs if pick(o) and (o.est if est else True)][-self.k:]
            if len(pool) >= 2:
                break
        else:
            return AsGiven().predict(course, kind, est, week)
        if est:
            r = np.array([math.log(o.actual / o.est) for o in pool])
            return math.log(est) + float(r.mean()), max(self.sigma_min, float(r.std(ddof=1)) * math.sqrt(1 + 1 / len(r)))
        y = np.array([math.log(o.actual) for o in pool])
        return float(y.mean()), max(self.sigma_min, float(y.std(ddof=1)) * math.sqrt(1 + 1 / len(y)))


# ---------------------------------------------------------------- quantiles


def quantile(m: float, s: float, p: float) -> float:
    return math.exp(m + s * norm.ppf(p))


def remaining(m: float, s: float, p: float, worked: float) -> float:
    """The p-quantile of what is left, given `worked` minutes and not finished: D | D > worked."""
    if worked <= 0:
        return quantile(m, s, p)
    f = norm.cdf((math.log(worked) - m) / s)
    u = min(1 - 1e-9, f + p * (1 - f))
    return max(0.0, math.exp(m + s * norm.ppf(u)) - worked)


def make(name: str, kinds, courses) -> Model:
    """The model zoo E020 compares."""
    if name == "as_given":
        return AsGiven()
    if name == "oracle":
        return Oracle()
    if name == "global_bias":
        return Hier(kinds, courses, levels=(), name=name)
    if name == "kind_bias":
        return Hier(kinds, courses, levels=("kind",), name=name)
    if name == "hier":
        return Hier(kinds, courses, name=name)
    if name == "hier_fused":
        return Hier(kinds, courses, fuse=True, name=name)
    if name == "hier_drift":
        return Hier(kinds, courses, half_life=4.0, name=name)
    if name == "hier_fused_drift":
        return Hier(kinds, courses, fuse=True, half_life=4.0, name=name)
    if name == "knn":
        return Knn()
    if name == "hier_fused_trend":
        return Hier(kinds, courses, fuse=True, trend=True, name=name)
    if name == "hier_fused_drift_trend":
        return Hier(kinds, courses, fuse=True, half_life=4.0, trend=True, name=name)
    if name.endswith("_recal"):
        return Recalibrated(make(name[: -len("_recal")], kinds, courses), name=name)
    m = re.fullmatch(r"(.+)_fa(\d+)", name)
    if m:  # fuse only after n recorded lengths
        inner = make(m.group(1), kinds, courses)
        inner.fuse_after, inner.name = int(m.group(2)), name
        return inner
    raise KeyError(name)
