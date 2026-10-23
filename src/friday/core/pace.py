"""Dials, paces and pace periods (DESIGN §17.6). The only place dials turn into per-day factors."""

from dataclasses import dataclass, replace
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field


class Dials(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capacity: float = Field(1.0, ge=0.3, le=1.5)
    rest: float = Field(1.0, ge=0.5, le=3.0)
    spread: float = Field(1.0, ge=0.0, le=5.0)
    growth: float = Field(1.0, ge=0.0, le=3.0)


@dataclass(frozen=True)
class DayScales:
    """Factors one day's dials apply to rules and the allocator. Floors and caps are applied by the users."""

    daily_load_threshold: float = 1.0
    deep_run_threshold: float = 1.0
    utilization: float = 1.0
    reserve_free: float = 1.0
    late_night_weight: float = 1.0
    debt_factor: float = 1.0
    even_load_weight: float = 1.0
    open_value_slopes: float = 1.0
    target_weight: float = 1.0
    target_amount: float = 1.0


def scales(dials: Dials) -> DayScales:
    return DayScales(
        daily_load_threshold=dials.capacity,
        deep_run_threshold=dials.capacity,
        utilization=dials.capacity,
        reserve_free=dials.rest,
        late_night_weight=dials.rest,
        debt_factor=dials.rest,
        even_load_weight=dials.spread,
        open_value_slopes=dials.growth,
        target_weight=dials.growth,
        target_amount=dials.growth,
    )


DEFAULT_PACES = {
    "Normal": Dials(),
    "Easy": Dials(capacity=0.6, rest=2.0, spread=3.0, growth=0.0),
    "Push": Dials(capacity=1.2, rest=0.5, spread=1.0, growth=2.0),
}


@dataclass(frozen=True)
class PacePeriod:
    pace_name: str | None  # None means custom dials
    dials: Dials
    start_date: date
    end_date: date | None  # inclusive; None lasts until changed


def period_on(day: date, periods: list[PacePeriod]) -> PacePeriod | None:
    for period in periods:
        if period.start_date <= day and (period.end_date is None or day <= period.end_date):
            return period
    return None


def dials_on(day: date, periods: list[PacePeriod], paces: dict[str, Dials], default_pace: str) -> Dials:
    period = period_on(day, periods)
    return period.dials if period else paces[default_pace]


def switch_pace(
    periods: list[PacePeriod],
    today: date,
    dials: Dials,
    pace_name: str | None,
    end_date: date | None,
    default_pace: str,
) -> list[PacePeriod]:
    """The periods after switching from today on. Switching to the default pace just ends the current one."""
    yesterday = today - timedelta(days=1)
    kept = []
    for period in periods:
        if period.end_date is not None and period.end_date < today:
            kept.append(period)
        elif period.start_date < today:
            kept.append(replace(period, end_date=yesterday))
    if pace_name == default_pace:
        return kept
    return kept + [PacePeriod(pace_name, dials, today, end_date)]


def pace_label(dials: Dials, paces: dict[str, Dials]) -> str:
    return next((name for name, saved in paces.items() if saved == dials), "Custom")


def adjust_dials(current: Dials, **changes: float | None) -> Dials:
    """The dials in effect with only the given ones changed (`pace --capacity 0.7`)."""
    return Dials.model_validate(current.model_dump() | {k: v for k, v in changes.items() if v is not None})
