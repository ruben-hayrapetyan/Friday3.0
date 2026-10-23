"""A simulated student (DESIGN §24.4): how they live Friday's plan.

They have hidden per-area duration multipliers, start late by a few minutes, sometimes skip a block, sometimes take
a safe swap, and answer the review a little noisily. (M9 adds hidden weights, moods and comparisons.)
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SimUser:
    rng: np.random.Generator
    area_mult: dict[str, float] = field(default_factory=dict)  # true time ÷ planned time, by area
    start_delay_min: float = 10  # mean minutes late to start a block
    skip_p: float = 0.08  # chance of skipping a block outright
    swap_p: float = 0.1  # chance of doing a safe swap instead
    review_slip_p: float = 0.1  # chance a review answer is a step off the truth

    @staticmethod
    def make(seed: int, areas: list[str]) -> "SimUser":
        rng = np.random.default_rng(seed)
        mult = {a: float(np.exp(rng.normal(0.1, 0.25))) for a in areas}
        return SimUser(rng, mult)

    def delay(self) -> int:
        """Minutes late to start, in whole quarter hours."""
        return int(round(self.rng.exponential(self.start_delay_min) / 15) * 15)

    def skips(self) -> bool:
        return bool(self.rng.random() < self.skip_p)

    def swaps(self) -> bool:
        return bool(self.rng.random() < self.swap_p)

    def work_minutes(self, planned: int, area: str | None) -> int:
        """How long a planned stretch really takes, with day-to-day noise, in whole quarter hours."""
        true = planned * self.area_mult.get(area or "", 1.0) * float(np.exp(self.rng.normal(0, 0.15)))
        return max(15, int(round(true / 15) * 15))

    def answer(self, status: str) -> str:
        """The review answer for what really happened, a step off now and then."""
        if self.rng.random() >= self.review_slip_p:
            return status
        return {"done": "partial", "partial": "done", "not_done": "partial"}[status]


FAMILIES = ("consistent", "noisy", "moody", "missing", "adversarial")
MISSING = "fri_sat:late:any"  # the preference no reference rule expresses: no work on Friday and Saturday evenings
MOOD_EFFECT = {
    "normal": {},
    "tired": {"late_night": 3.0, "deep_run": 2.5, "daily_load": 2.5, "weekday_evenings": 2.0, "weekends": 2.0,
              "unscheduled": 0.4, "target_shortfall": 0.4, "open_value": 0.3},
    "motivated": {"daily_load": 0.4, "deep_run": 0.5, "weekday_evenings": 0.5, "unscheduled": 2.0,
                  "target_shortfall": 2.0, "open_value": 2.5},
}  # fmt: skip


@dataclass
class Taste:
    """A simulated user's hidden preferences (DESIGN §24.4, ported from the research's `sim/user.py`): true
    multipliers (log-normal, σ 0.6), a family that sets how they answer, and, for some, moods or a missing rule."""

    rng: np.random.Generator
    family: str
    theta: dict[str, float]
    mood: str = "normal"

    @staticmethod
    def make(seed: int, family: str, rules: tuple[str, ...]) -> "Taste":
        rng = np.random.default_rng(seed)
        return Taste(rng, family, {r: float(np.exp(rng.normal(0, 0.6))) for r in rules})

    def true_theta(self) -> dict[str, float]:
        if self.family != "moody":
            return self.theta
        effect = MOOD_EFFECT[self.mood]
        return {r: t * effect.get(r, 1.0) for r, t in self.theta.items()}

    def energy(self, features: dict) -> float:
        theta = self.true_theta()
        missing = 3.0 * features.get("templates", {}).get(MISSING, 0.0) if self.family == "missing" else 0.0
        return sum(theta.get(r, 1.0) * v for r, v in features["rules"].items()) + missing

    def prefers_a(self, a: dict, b: dict) -> bool:
        """Bradley–Terry on true energy, on the model's own scale; noisy users answer hotter, adversarial ones flip
        30% on purpose."""
        size = sum(abs(a["rules"].get(r, 0) - b["rules"].get(r, 0)) for r in a["rules"]) or 1.0
        tau = 0.05 * (6.0 if self.family == "noisy" else 1.0)
        gap = (self.energy(a) - self.energy(b)) / size / tau
        answer = bool(self.rng.random() < 1 / (1 + np.exp(np.clip(gap, -50, 50))))
        if self.family == "adversarial" and self.rng.random() < 0.3:
            answer = not answer
        return answer

    def step_mood(self) -> None:
        if self.family == "moody":
            self.mood = str(self.rng.choice(("normal", "tired", "motivated"), p=(0.6, 0.2, 0.2)))
