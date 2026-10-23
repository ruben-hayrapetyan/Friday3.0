"""Length estimates and how your own estimates run (DESIGN §6.6).

The estimate comes from similar past items, else the group median, else nobody knows and the preset default
stands. The bias check compares your typed estimates with actual times, per area.
"""

import math
import sqlite3
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from friday.core.bias import bias_ratio  # noqa: F401  (estimates and the planner's cushion share it)
from friday.core.db import rows
from friday.core.settings import EstimateSettings
from friday.core.textnorm import TextRules, norm, similarity, type_text
from friday.core.time import UNIT_MIN, format_utc

LEARNED_SOURCES = ("timer", "review", "retro")


@dataclass
class Estimate:
    units: int
    method: str  # similar | group
    detail: dict[str, Any] = field(default_factory=dict)


def history(
    conn: sqlite3.Connection, area: str | None, preset: str | None, now_utc: int, window_days: int, user_id: int = 1
) -> list[dict[str, Any]]:
    since = format_utc(now_utc - window_days * 1440)
    column, value = ("area", area) if area is not None else ("preset", preset)
    return rows(
        conn,
        f"SELECT * FROM completions WHERE user_id = ? AND {column} IS ? AND completed_utc >= ? "
        f"AND actual_source IN ({', '.join('?' * len(LEARNED_SOURCES))}) ORDER BY completed_utc DESC",
        [user_id, value, since, *LEARNED_SOURCES],
    )


def estimate_length(
    title: str, area: str | None, past: list[dict[str, Any]], settings: EstimateSettings, text: TextRules
) -> Estimate | None:
    words = type_text(norm(title, text, area))
    scored = []
    for row in past:
        score = similarity(words, type_text(row["norm_title"].split()))
        if area is not None and row["area"] == area:
            score += settings.area_bonus
        if score >= settings.min_similarity:
            scored.append((score, row))
    # Sorting is stable and `past` is newest first, so equal scores keep the most recent.
    best = sorted(scored, key=lambda pair: -pair[0])[: settings.k]
    if len(best) >= settings.min_samples:
        minutes = [row["actual_minutes"] for _, row in best]
        used = [{"title": row["norm_title"], "minutes": row["actual_minutes"], "score": round(s, 2)} for s, row in best]
        return Estimate(units_of(median(minutes)), "similar", detail(minutes, used))
    if len(past) >= settings.min_samples:
        minutes = [row["actual_minutes"] for row in past]
        return Estimate(units_of(median(minutes)), "group", detail(minutes, []))
    return None


def units_of(minutes: float) -> int:
    return max(1, math.ceil(minutes / UNIT_MIN))


def detail(minutes: list[int], used: list[dict[str, Any]]) -> dict[str, Any]:
    return {"median_min": median(minutes), "range_min": [min(minutes), max(minutes)], "used": used}
