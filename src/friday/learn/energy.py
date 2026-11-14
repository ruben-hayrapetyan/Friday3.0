"""The learned energy map (DESIGN §21.7): per half-hour of the week, whether planned work there happens and how
fast it goes, turned into a price for deep work that is added to your own map. Pure: numpy only.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

CELLS = 48
MIN_SEEN = 4  # a cell with fewer observations gets no learned price, so early misses don't brand it
PRIOR = 4.0  # how many blocks your overall rate counts as, in each cell


@dataclass(frozen=True)
class Seen:
    weekday: int  # Monday = 0
    cell: int  # half hour of the day, 0–47
    happened: bool
    speed: float | None  # actual ÷ planned when timed


def prices(seen: Sequence[Seen]) -> list[list[float]]:
    """7 × 48 learned prices in points an hour: 4 × (your overall rate − the cell's P(happened)) + 2 × how much
    slower than your usual speed the cell runs (shrunk log ratio), in [0, 6]."""
    s, n = np.zeros((7, CELLS)), np.zeros((7, CELLS))
    log_speed, timed = np.zeros((7, CELLS)), np.zeros((7, CELLS))
    for x in seen:
        n[x.weekday, x.cell] += 1
        s[x.weekday, x.cell] += x.happened
        if x.speed:
            log_speed[x.weekday, x.cell] += np.log(x.speed)
            timed[x.weekday, x.cell] += 1
    overall = s.sum() / max(n.sum(), 1)
    s_smooth, n_smooth = smooth(s), smooth(n)
    # Shrunk toward your own overall rate (a Beta prior worth PRIOR blocks), and priced against it: work that slips
    # everywhere alike makes no hour look worse than another.
    happened = (s_smooth + PRIOR * overall) / (n_smooth + PRIOR)
    mean_log = np.divide(log_speed, timed, out=np.zeros_like(log_speed), where=timed > 0)
    usual = log_speed.sum() / max(timed.sum(), 1)  # slower everywhere alike makes no hour worse either
    shrunk = np.where(timed > 0, mean_log - usual, 0.0) * timed / (timed + 5)
    # Only a shortfall beyond chance counts: 1.5 standard errors of the cell's rate are forgiven.
    noise = 1.5 * np.sqrt(overall * (1 - overall) / (n_smooth + PRIOR))
    price = np.clip(4 * np.maximum(0.0, overall - happened - noise) + 2 * shrunk, 0.0, 6.0)
    price[n < MIN_SEEN] = 0.0
    return [[round(float(v), 2) for v in row] for row in price]


def smooth(grid: np.ndarray) -> np.ndarray:
    """Neighboring half hours of the same day count half; the same half hour on neighboring days a quarter."""
    out = grid.copy()
    out[:, 1:] += 0.5 * grid[:, :-1]
    out[:, :-1] += 0.5 * grid[:, 1:]
    out += 0.25 * (np.roll(grid, 1, axis=0) + np.roll(grid, -1, axis=0))
    return out
