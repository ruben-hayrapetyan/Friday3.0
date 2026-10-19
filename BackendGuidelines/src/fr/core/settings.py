"""Engine settings. Starting values from ENGINE_REFERENCE.md, not facts."""
from __future__ import annotations

from dataclasses import dataclass, field

UNIT_MIN = 15
MINUTES_PER_DAY = 1440
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Hourly energy prices (points/hour) charged to deep work; index = local hour of slot start.
# Starting values to tune: cheap mid-morning, a post-lunch dip, dearer late and very early.
_DEEP = [3, 3, 3, 3, 3, 3, 3, 2, 1, 0.5, 0, 0, 0.5, 1, 0.5, 0.5, 0.5, 1, 1, 1.5, 2, 2, 2.5, 3]


def default_energy_map() -> dict[int, list[float]]:
    return {wd: list(_DEEP) for wd in range(7)}


@dataclass
class Sleep:
    """Per-weekday bedtime / wake in minutes of the calendar day (bedtime may exceed 1440)."""

    bedtime: tuple[int, ...] = (23 * 60 + 30,) * 5 + (24 * 60 + 30,) * 2
    wake: tuple[int, ...] = (7 * 60 + 30,) * 5 + (9 * 60,) * 2
    margin: int = 60


@dataclass
class Settings:
    day_start: int = 4 * 60
    week_start: int = 0
    horizon_days: int = 14
    fine_days: int = 7
    allocator_weeks: int = 12
    scale: int = 100
    utilization: float = 0.8
    day_cap_units: int = 48  # hard daily cap, 12 h
    sleep: Sleep = field(default_factory=Sleep)
    buffers: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {"class": (10, 0), "meeting": (5, 5), "shove": (0, 0), "other": (5, 5)}
    )
    energy_map: dict[int, list[float]] = field(default_factory=default_energy_map)
    stages: tuple[str, ...] = ("deadlines", "wellbeing", "preferences")
    # per-stage deterministic-time limit and wall-clock share (6A.6)
    det_time: tuple[float, float, float] = (20.0, 20.0, 20.0)
    time_limit_s: float = 30.0
    time_share: tuple[float, float, float] = (0.4, 0.3, 0.3)
    stage_slack: tuple[float, float, float] = (0.0, 0.0, 0.0)
    workers: int = 8
    minimize_changes_scale: float = 1.0


STAGES = ("deadlines", "wellbeing", "preferences")
