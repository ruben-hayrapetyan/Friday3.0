"""How your own estimates run (DESIGN §6.6's bias check): the median of actual ÷ estimate, when it is consistently
off. Shared by the estimate's warning and the planner's learned cushion (COMBINED.md 41). Pure."""

from statistics import median
from typing import Any

from friday.core.settings import EstimateSettings
from friday.core.time import UNIT_MIN


def bias_ratio(past: list[dict[str, Any]], settings: EstimateSettings) -> float | None:
    """The median of actual ÷ your estimate when it is consistently off by more than the threshold."""
    typed = [r for r in past if r["your_estimate_units"]][: settings.bias_window]
    ratios = [r["actual_minutes"] / (r["your_estimate_units"] * UNIT_MIN) for r in typed]
    if len(ratios) < settings.bias_min_samples:
        return None
    m = median(ratios)
    if 1 / settings.bias_threshold <= m <= settings.bias_threshold:
        return None
    same_side = sum(1 for r in ratios if (r > 1) == (m > 1)) / len(ratios)
    return m if same_side >= settings.bias_consistency else None
