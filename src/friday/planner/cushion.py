"""The learned cushion (COMBINED.md 41): your length is planned exactly, until the work you've timed of the same tag
(or kind, without one) shows you consistently run over. Then the plan reserves that much more for your estimate, up
to `estimate.cushion_cap` times it. Running under never shortens it. Settings → Advanced switches it off.

A kind you finish faster is shortened only on your yes (2 Nov): Friday asks once work it planned late keeps getting
done on time in less time (learn/beat_plan.py), and the share you accept is kept in kv `length_shares`."""

import math
import sqlite3
from dataclasses import replace
from typing import Any

from friday.core.bias import bias_ratio
from friday.core.db import rows
from friday.core.items import Item
from friday.core.time import format_utc

LEARNED_SOURCES = ("timer", "review", "retro")
SHARES = "length_shares"  # kv: kind → the share of its length it's planned at


def cushion(conn: sqlite3.Connection, area: str | None, preset: str | None, now_utc: int, settings: dict[str, Any],
            user_id: int, memo: dict[tuple[str | None, str | None], float]) -> float:  # fmt: skip
    """The factor your estimates for this tag or kind are planned at: 1, or how far over you consistently run."""
    key = (area, preset)
    if key not in memo:
        estimate = settings["estimate"]
        ratio = None
        if estimate.cushion:
            since = format_utc(now_utc - estimate.window_days * 1440)
            column, value = ("area", area) if area is not None else ("preset", preset)
            past = rows(
                conn,
                f"SELECT * FROM completions WHERE user_id = ? AND {column} IS ? AND completed_utc >= ? "
                f"AND actual_source IN ({', '.join('?' * len(LEARNED_SOURCES))}) ORDER BY completed_utc DESC",
                [user_id, value, since, *LEARNED_SOURCES],
            )
            ratio = bias_ratio(past, estimate)
        memo[key] = min(ratio, estimate.cushion_cap) if ratio is not None and ratio > 1 else 1.0
    return memo[key]


def cushioned(item: Item, factor: float) -> Item:
    """The item as planned: your estimate times the cushion, when you gave one and it runs over."""
    if factor <= 1 or item.amount != "fixed" or item.duration_source != "you" or not item.your_estimate_units:
        return item
    return replace(item, duration_units=max(item.duration_units or 0, math.ceil(item.your_estimate_units * factor)))


def shortened(item: Item, share: float | None) -> Item:
    """The item as planned at `share` of its length, when the length is yours or the kind's (Friday's own estimates
    learn from your times already) and nothing says you run over."""
    if not share or share >= 1 or item.amount != "fixed" or item.duration_source not in ("you", "preset"):
        return item
    if not item.duration_units or item.when == "fixed":
        return item
    units = max(1, math.ceil(item.duration_units * share))
    return replace(
        item, duration_units=units, min_chunk_units=min(item.min_chunk_units, units), full_units=item.duration_units
    )


def past_shortened(item: Item, done_units: int) -> Item:
    """The item at its full length again once the work done on it reaches its shortened length and it's still open:
    the share was a guess, and this one is taking longer (8 Nov: an assignment planned at 75% of its 7 hours, with
    5½ hours done, had nothing planned for its last 1½ hours, due that afternoon)."""
    if not item.full_units or not item.duration_units or done_units < item.duration_units:
        return item
    return replace(item, duration_units=item.full_units, full_units=None)
