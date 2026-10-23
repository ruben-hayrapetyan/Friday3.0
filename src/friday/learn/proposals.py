"""Missing rules (DESIGN §21.5), ported from the research supervisor (`supervisor/grammar.py`, `discover.py`).

A grammar of `time_preference` templates (day sets × time windows × any or deep work). For each, the feature on a
plan is its hours of matching work, priced 1 an hour. A template is proposed when adding its feature raises the
5-fold cross-validated likelihood of the comparisons by more than a threshold. Nothing is added without a yes.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from friday.learn.preferences import Comparison, bt_fit, design, loglik

DAY_SETS: dict[str, tuple[str, ...] | None] = {
    "weekdays": ("mon", "tue", "wed", "thu", "fri"),
    "weekend": ("sat", "sun"),
    "fri_sat": ("fri", "sat"),
    **{d: (d,) for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
    "all": None,
}
WINDOWS = {
    "early": ("06:00", "09:00"),
    "morning": ("09:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "21:00"),
    "late": ("19:00", "23:59"),
    "night": ("21:00", "23:59"),
}
SCOPES = ("any", "deep")
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_WORDS = {"weekdays": "weekdays", "weekend": "weekends", "fri_sat": "Friday and Saturday", "all": "any day"}
WINDOW_WORDS = {"early": "early mornings", "morning": "mornings", "afternoon": "afternoons", "evening": "evenings",
                "late": "late evenings", "night": "nights"}  # fmt: skip


@dataclass(frozen=True)
class Template:
    name: str  # "fri_sat:late:any"
    days: tuple[str, ...] | None
    start: str
    end: str
    deep_only: bool

    def rule(self) -> dict:
        """The rule a yes adds: a gentle time preference whose weight is then learned."""
        params: dict = {"start": self.start, "end": self.end, "price": 1.0}
        if self.days is not None:
            params["days"] = list(self.days)
        rule = {"type": "time_preference", "name": f"learned:{self.name}", "weight": 1.0, "params": params}
        if self.deep_only:
            rule["scope"] = {"energy": "deep"}
        return rule

    def sentence(self) -> str:
        days, window, scope = self.name.split(":")
        what = "deep work" if scope == "deep" else "work"
        return f"You seem to prefer no {what} on {DAY_WORDS.get(days, days.capitalize())} {WINDOW_WORDS[window]}."


TEMPLATES = [
    Template(f"{d}:{w}:{s}", days, start, end, s == "deep")
    for d, days in DAY_SETS.items()
    for w, (start, end) in WINDOWS.items()
    for s in SCOPES
]


def hours_in(template: Template, blocks: Sequence[tuple[datetime, datetime, str | None]]) -> float:
    """Hours of work (local start, end, energy) inside the template's window on its days."""
    total = 0.0
    for start, end, energy in blocks:
        if template.deep_only and energy != "deep":
            continue
        if template.days is not None and DAY_NAMES[start.weekday()] not in template.days:
            continue
        lo = start.replace(hour=int(template.start[:2]), minute=int(template.start[3:]))
        hi = start.replace(hour=int(template.end[:2]), minute=int(template.end[3:]))
        total += max(0.0, (min(end, hi) - max(start, lo)).total_seconds() / 3600)
    return total


def template_features(blocks: Sequence[tuple[datetime, datetime, str | None]]) -> dict[str, float]:
    return {t.name: hours_in(t, blocks) for t in TEMPLATES}


def cv_gain(lib: np.ndarray, extra: np.ndarray, folds: int = 5, seed: int = 0) -> np.ndarray:
    """Per template: held-out log-likelihood per comparison with its feature, minus without."""
    n, d = lib.shape
    order = np.random.default_rng(seed).permutation(n)
    base, with_it = np.zeros(n), np.zeros((extra.shape[1], n))
    for test in np.array_split(order, min(folds, n)):
        train = np.setdiff1d(order, test)
        theta = bt_fit(lib[train], np.ones(d), np.ones(d), np.full(d, 0.02))
        base[test] = loglik(lib[test], theta)
        for c in range(extra.shape[1]):
            x = np.hstack([lib, extra[:, c : c + 1]])
            prior, sd = np.append(np.ones(d), 0.0), np.append(np.ones(d), 2.0)
            theta2 = bt_fit(x[train], prior, sd, np.append(np.full(d, 0.02), 0.0))
            with_it[c, test] = loglik(x[test], theta2)
    return (with_it - base).mean(axis=1)


def propose(
    comparisons: Sequence[Comparison],
    extras: Sequence[tuple[dict[str, float], dict[str, float]]],  # per comparison: (winner, loser) template hours
    rules: Sequence[str],
    refused: set[str],
    min_gain: float,
    seed: int = 0,
) -> tuple[Template | None, float]:
    """The best template not refused before, if its gain clears `min_gain` (at least 10 comparisons)."""
    candidates = [t for t in TEMPLATES if t.name not in refused]
    if len(comparisons) < 10 or not candidates:
        return None, 0.0
    lib, _ = design(comparisons, rules)
    size = np.array([sum(abs(c.winner.get(r, 0) - c.loser.get(r, 0)) for r in rules) for c in comparisons])
    size[size < 1e-12] = 1.0
    extra = (
        np.array([[w.get(t.name, 0.0) - lo.get(t.name, 0.0) for t in candidates] for w, lo in extras]) / size[:, None]
    )
    gains = cv_gain(lib, extra, seed=seed)
    best = int(np.argmax(gains))
    return (candidates[best] if gains[best] > min_gain else None), float(gains[best])
