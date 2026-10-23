"""State: the dials as hidden units (DESIGN §21.3; off by default), ported from the research's `learn/hidden.py`
in its "dial" mode and the gate from `system.py`.

Four units h (capacity, rest, spread, growth) act multiplicatively on the learned multipliers: θ_eff = θ·exp(U h),
with U seeded from what each dial means. A week's h is inferred from its comparisons, skipped blocks and check-ins;
θ and the skip link are fitted jointly over all weeks. The units are used only after they have predicted the
following weeks' comparisons `gate` nats better, cumulatively, than taste alone at its best answer temperature.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

DIALS = ("capacity", "rest", "spread", "growth")
DIAL_RULES = {
    "capacity": {"daily_load": -1.0, "deep_run": -1.0},
    "rest": {"late_night": 1.0, "weekday_evenings": 1.0, "weekends": 1.0},
    "spread": {"even_load": 1.0},
    "growth": {"open_value": 1.0, "target_shortfall": 1.0, "unscheduled": 1.0},
}
MOODS = ("normal", "tired", "motivated")
# Check-in logits of (normal, tired, motivated) given the four units; a check-in is right about 70% of the time.
CHECKIN = np.array([[0.0, 0.0, 0.0, 0.0], [-1.5, 1.5, 0.0, -1.0], [1.5, -1.0, 0.0, 1.5]])
PACE_H = {
    "normal": np.zeros(4),
    "tired": np.array([-1.0, 1.0, 0.0, -1.0]),
    "motivated": np.array([1.0, -1.0, 0.0, 1.0]),
}
TASTE_SCALES = (0.02, 0.05, 0.1, 0.2, 0.5)


def loadings(rules: Sequence[str]) -> np.ndarray:
    """U [4, D]: which rule weights each dial moves."""
    u = np.zeros((4, len(rules)))
    for j, dial in enumerate(DIALS):
        for rule, v in DIAL_RULES[dial].items():
            if rule in rules:
                u[j, list(rules).index(rule)] = v
    return u


@dataclass
class Week:
    diffs: np.ndarray  # [n, D] normalized winner − loser
    weights: np.ndarray  # per comparison (drags count more)
    skips: int
    blocks: int
    checkin: str | None
    pace: str | None  # a picked pace clamps the units: it is that week's known state


@dataclass
class StateModel:
    rules: tuple[str, ...]
    scale: float = 0.05
    theta: np.ndarray = field(default=None)  # type: ignore[assignment]
    weeks: list[Week] = field(default_factory=list)
    h: list[np.ndarray] = field(default_factory=list)
    skip_link: np.ndarray = field(default_factory=lambda: np.array([-2.5, -0.8, 1.0, 0.0, -0.4]))
    ll_units: float = 0.0
    ll_taste: dict[float, float] = field(default_factory=lambda: dict.fromkeys(TASTE_SCALES, 0.0))

    def __post_init__(self) -> None:
        self.u = loadings(self.rules)
        if self.theta is None:
            self.theta = np.ones(len(self.rules))

    @property
    def gain(self) -> float:
        return self.ll_units - max(self.ll_taste.values())

    def units_on(self, gate: float) -> bool:
        return self.gain > gate

    def theta_eff(self, h: np.ndarray, theta: np.ndarray | None = None) -> np.ndarray:
        return (self.theta if theta is None else theta) * np.exp(np.clip(h @ self.u, -5, 5))

    def checkin_ll(self, h: np.ndarray, checkin: str | None) -> float:
        if checkin is None:
            return 0.0
        z = CHECKIN @ h
        z = z - z.max()
        return 0.7 * float(z[MOODS.index(checkin)] - np.log(np.exp(z).sum()))

    def predict_h(self, checkin: str | None, pace: str | None) -> np.ndarray:
        """The units to plan with at a week's start, before its comparisons exist."""
        if pace is not None:
            return PACE_H[pace].copy()
        h = 0.5 * self.h[-1] if self.h else np.zeros(4)  # states persist a little
        if checkin is not None:
            h = minimize(lambda x: 0.5 * np.sum((x - h) ** 2) - self.checkin_ll(x, checkin), h, method="L-BFGS-B").x
        return h

    def week_ll(self, theta: np.ndarray, h: np.ndarray, week: Week) -> float:
        ll = 0.0
        if len(week.diffs):
            z = -(week.diffs @ self.theta_eff(h, theta)) / self.scale
            ll -= float((week.weights * np.logaddexp(0, -z)).sum())
        if week.blocks:
            p = float(np.clip(1 / (1 + np.exp(-(self.skip_link[0] + self.skip_link[1:] @ h))), 1e-6, 1 - 1e-6))
            ll += week.skips * np.log(p) + (week.blocks - week.skips) * np.log(1 - p)
        return ll + self.checkin_ll(h, week.checkin)

    def score(self, week: Week, h: np.ndarray, taste: np.ndarray) -> None:
        """The gate's running tally, before learning from the week: units against taste at its best temperature."""
        if not len(week.diffs):
            return
        self.ll_units += self.week_ll(self.theta, h, Week(week.diffs, week.weights, 0, 0, None, None))
        for s in self.ll_taste:
            self.ll_taste[s] -= float(np.logaddexp(0, (week.diffs @ taste) / s).sum())

    def add(self, week: Week, iters: int = 200) -> None:
        self.weeks.append(week)
        self.h.append(np.zeros(4))
        self.fit(iters)

    def fit(self, iters: int = 200) -> None:
        """Joint MAP of θ, every week's units and the skip link."""
        n_weeks, d = len(self.weeks), len(self.rules)

        def objective(x: np.ndarray) -> float:
            theta, hs, link = x[:d], x[d : d + 4 * n_weeks].reshape(n_weeks, 4), x[d + 4 * n_weeks :]
            self.skip_link = link
            nll = 0.5 * float(np.sum((theta - 1.0) ** 2))
            for w, week in enumerate(self.weeks):
                h = PACE_H[week.pace] if week.pace is not None else hs[w]
                nll += 0.5 * float(np.sum(h**2)) - self.week_ll(theta, h, week)
            return nll

        start = np.concatenate([self.theta, np.array(self.h).ravel(), self.skip_link])
        bounds = [(0.02, 20.0)] * d + [(-3.0, 3.0)] * (4 * n_weeks) + [(-6.0, 6.0)] * 5
        found = minimize(objective, start, method="L-BFGS-B", bounds=bounds, options={"maxiter": iters}).x
        self.theta = found[:d]
        self.h = list(found[d : d + 4 * n_weeks].reshape(n_weeks, 4))
        self.skip_link = found[d + 4 * n_weeks :]

    def mood(self, h: np.ndarray) -> str:
        """A week's units read as a mood."""
        z = CHECKIN @ h
        return MOODS[int(np.argmax(z))] if z.max() - z[0] > 0.5 else "normal"
