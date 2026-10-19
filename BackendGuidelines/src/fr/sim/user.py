"""Simulated users (RESEARCH_PROMPT section 5).

A user has a hidden truth: weight multipliers over the rule library (relative to the hand-set reference weights), a
mood Markov chain whose states shift those weights through U*, per-area duration multipliers, and optionally a true
preference the rule library does not contain (a "missing feature", written as an extra rule only the user has).

Energies are in points. A plan's feature vector phi has one entry per rule (its cost at the reference weight, in points),
so E_theta(x) = theta . phi(x) with theta = 1 meaning "the reference weights".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# rules whose weights are learned; the deadline stage (late_work, quota) is a guarantee, not a taste
LEARNABLE = ("late_night", "deep_run", "weekday_evenings", "weekends", "daily_load", "even_load", "energy", "soft_late",
             "unscheduled", "chunk_cost", "spread", "cluster", "target_shortfall", "elastic_shortfall", "open_value")
MOODS = ("normal", "tired", "motivated")

# how a mood multiplies the true weights (U* in multiplicative form)
MOOD_EFFECT = {
    "normal": {},
    "tired": {"late_night": 3.0, "deep_run": 2.5, "daily_load": 2.5, "weekday_evenings": 2.0, "weekends": 2.0,
              "unscheduled": 0.4, "target_shortfall": 0.4, "open_value": 0.3},
    "motivated": {"daily_load": 0.4, "deep_run": 0.5, "weekday_evenings": 0.5, "unscheduled": 2.0,
                  "target_shortfall": 2.0, "open_value": 2.5},
}
SKIP_BY_MOOD = {"normal": 0.05, "tired": 0.25, "motivated": 0.02}

# a preference no reference rule expresses: no work on Friday and Saturday evenings
MISSING_RULE = dict(type="time_preference", name="missing:fri_sat_evening", weight=1.0,
                    params=dict(days=["fri", "sat"], start="19:00", end="23:59", price=4.0))


@dataclass
class UserType:
    name: str
    theta_sigma: float = 0.6  # spread of log true multipliers around 1
    choice_tau: float = 1.0  # temperature of day-to-day choices, as a multiple of the typical energy gap
    rank_tau: float = 1.0  # Bradley-Terry temperature of rankings, same units
    flip: float = 0.0  # probability of answering a ranking the wrong way on purpose (adversarial)
    mood_P: np.ndarray = field(default_factory=lambda: np.array([[0.9, 0.05, 0.05], [0.3, 0.7, 0.0], [0.3, 0.0, 0.7]]))
    mood_strength: float = 1.0  # 0 = moods do nothing
    missing_weight: float = 0.0  # weight of MISSING_RULE in the true energy
    drag_p: float = 0.5  # chance per week that the user drags something
    skip_scale: float = 1.0


USER_TYPES = {
    "easy": UserType("easy", choice_tau=0.3, rank_tau=0.3, mood_strength=0.0),
    "noisy": UserType("noisy", choice_tau=2.0, rank_tau=2.0, mood_strength=0.0),
    "moody": UserType("moody", choice_tau=0.3, rank_tau=0.3, mood_strength=1.0,
                      mood_P=np.array([[0.6, 0.2, 0.2], [0.4, 0.6, 0.0], [0.4, 0.0, 0.6]])),
    "missing": UserType("missing", choice_tau=0.3, rank_tau=0.3, mood_strength=0.0, missing_weight=3.0),
    "adversarial": UserType("adversarial", choice_tau=0.3, rank_tau=0.3, mood_strength=0.0, flip=0.3),
}


@dataclass
class SimUser:
    kind: UserType
    seed: int
    theta: np.ndarray  # true multipliers over LEARNABLE (normal mood)
    mood: str = "normal"
    rng: np.random.Generator = None  # type: ignore[assignment]
    area_mult: dict = field(default_factory=dict)

    @staticmethod
    def make(kind: str | UserType, seed: int) -> "SimUser":
        k = USER_TYPES[kind] if isinstance(kind, str) else kind
        rng = np.random.default_rng(seed)
        theta = np.exp(rng.normal(0.0, k.theta_sigma, size=len(LEARNABLE)))
        areas = {f"CS{c}": float(np.exp(rng.normal(0.1, 0.25))) for c in range(4)}
        return SimUser(k, seed, theta, "normal", rng, areas)

    def theta_now(self, mood: str | None = None) -> np.ndarray:
        """True multipliers in a mood (default: the current one)."""
        m = self.mood if mood is None else mood
        out = self.theta.copy()
        for r, f in MOOD_EFFECT[m].items():
            out[LEARNABLE.index(r)] *= f ** self.kind.mood_strength
        return out

    def step_mood(self) -> str:
        i = MOODS.index(self.mood)
        self.mood = MOODS[int(self.rng.choice(3, p=self.kind.mood_P[i]))]
        return self.mood

    def energy(self, phi: np.ndarray, phi_missing: float = 0.0, mood: str | None = None) -> float:
        return float(self.theta_now(mood) @ phi + self.kind.missing_weight * phi_missing)

    def choose(self, energies: np.ndarray, scale: float) -> int:
        """Pick one of several alternatives with probability proportional to exp(-E / (tau * scale))."""
        t = max(1e-9, self.kind.choice_tau * scale)
        z = -(energies - energies.min()) / t
        p = np.exp(z)
        p /= p.sum()
        return int(self.rng.choice(len(energies), p=p))

    def rank(self, e_a: float, e_b: float, scale: float) -> bool:
        """True if the user says A is better than B (Bradley-Terry on true energies, plus deliberate flips)."""
        t = max(1e-9, self.kind.rank_tau * scale)
        p_a = 1.0 / (1.0 + np.exp(np.clip((e_a - e_b) / t, -50, 50)))
        ans = bool(self.rng.random() < p_a)
        if self.kind.flip and self.rng.random() < self.kind.flip:
            ans = not ans
        return ans

    def skip_p(self) -> float:
        return SKIP_BY_MOOD[self.mood] * self.kind.skip_scale

    def review(self, e_lived: float, scale: float) -> float:
        """A 1-5 rating of the week: worse energy and a tired mood both pull it down; noisy."""
        base = 4.0 - 1.0 * np.tanh(e_lived / max(scale * 20, 1e-9)) - (0.8 if self.mood == "tired" else 0.0) \
            + (0.4 if self.mood == "motivated" else 0.0)
        return float(np.clip(base + self.rng.normal(0, 0.5), 1, 5))

    def checkin(self) -> str:
        """A one-tap mood check-in: right 70% of the time."""
        if self.rng.random() < 0.7:
            return self.mood
        return MOODS[int(self.rng.integers(0, 3))]
