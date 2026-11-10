"""Annealing (DESIGN §11.8–11.9): the schedule, the stage policies, chains as threads, the tabu finish.

Budgets are proposals per chain, never seconds. Chain c uses seed `seed + c`, and the best chain wins by
(deadlines, wellbeing, preferences) — deadlines within LATE_TOLERANCE of the least late counting as equal — then by
index, so the plan never depends on how many threads ran the chains.
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from friday.engine.chain import run_chain, sample_deltas, tabu
from friday.engine.compile import Compiled
from friday.engine.kernel import N_MOVES, init_state, move_cumulative, new_state, protected_items

DEADLINE_WEIGHT = 1e6
# How much later, as a share of what is already late, polishing may make the plan. With work late, the deadlines
# stage's integer rounding (a minute's lateness) outranked everything, and late work went in alternating half-hour
# slivers of three assignments (M15). Nothing late stays nothing late: 0 × anything is 0.
LATE_TOLERANCE = 0.001
CALIBRATION_MOVES = 1500
TABU_SHARE, TABU_CANDIDATES, TABU_TENURE = 0.2, 25, 8
STRICT_WELLBEING_SHARE = 0.35  # the research's split for strictly tiered annealing
LEXPOLISH_SEARCH_SHARE = 0.6


@dataclass(frozen=True)
class SamplerConfig:
    policy: str = "lexpolish"
    weighted_ratio: float = 1000.0
    seed: int = 0
    chains: int = 1
    threads: int = 1
    t0: float = 0.1
    t1: float = 0.003
    tabu_after_steps: int = 2_500_000
    move_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class Phase:
    weights: np.ndarray
    share: float  # of the chain's steps
    caps_wellbeing: bool = False  # cap wellbeing at the value the previous phase reached
    caps_deadlines: bool = False  # cap deadlines there too, within LATE_TOLERANCE, instead of weighing them


@dataclass
class ChainOutcome:
    index: int
    owner: np.ndarray
    stage_values: tuple[int, int, int]
    stats: np.ndarray
    steps: int
    after_each_phase: list[tuple[int, int, int]] = field(default_factory=list)


def performance_cores() -> int:
    """Performance cores on this machine (all cores where the platform doesn't tell them apart)."""
    try:
        out = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True, timeout=2)
        if out.returncode == 0 and out.stdout.strip().isdigit():
            return int(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return os.cpu_count() or 1


def default_chains() -> int:
    """Performance cores − 1, so a plan depends on the Mac (C90: GitHub's 2-CPU machines ran 1 chain and planned
    worse than any Mac would). FRIDAY_CHAINS fixes the number: the tests set 3, the fewest an Apple-silicon Mac gets."""
    if fixed := os.environ.get("FRIDAY_CHAINS", "").strip():
        return max(1, int(fixed))
    return max(1, performance_cores() - 1)


def policy_phases(config: SamplerConfig) -> list[Phase]:
    if config.policy == "lexpolish":
        # Search one weighted energy, then polish preferences without letting wellbeing rise (research E006b).
        return [
            Phase(np.array([DEADLINE_WEIGHT, 1000.0, 1.0]), LEXPOLISH_SEARCH_SHARE),
            Phase(np.array([0.0, 0.0, 1.0]), 1 - LEXPOLISH_SEARCH_SHARE, caps_wellbeing=True, caps_deadlines=True),
        ]
    if config.policy == "weighted":
        return [Phase(np.array([DEADLINE_WEIGHT, config.weighted_ratio, 1.0]), 1.0)]
    if config.policy == "strict":
        return [
            Phase(np.array([DEADLINE_WEIGHT, 1.0, 0.0]), STRICT_WELLBEING_SHARE),
            Phase(np.array([DEADLINE_WEIGHT, 0.0, 1.0]), 1 - STRICT_WELLBEING_SHARE, caps_wellbeing=True),
        ]
    raise ValueError(f"engine.stage_policy: unknown policy {config.policy!r}")


def median_delta(
    c: Compiled, owner: np.ndarray, protected: np.ndarray, weights: np.ndarray, cumulative: np.ndarray, seed: int
) -> float:
    """The median |Δ| of random valid moves that leave the deadlines stage alone (its deltas would set T near 10⁹)."""
    st = new_state(c.m)
    init_state(c.m, st, owner)
    out = np.zeros((CALIBRATION_MOVES, 3), dtype=np.int64)
    work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
    n = sample_deltas(c.m, st, protected, weights, cumulative, *work, CALIBRATION_MOVES, seed, out)
    moves = out[:n]
    if weights[0] >= 1e5:
        moves = moves[moves[:, 0] == 0]
    deltas = np.abs(moves[:, 1:] @ weights[1:])
    deltas = deltas[deltas > 0]
    return float(np.median(deltas)) if len(deltas) else 1.0


def run_one_chain(
    c: Compiled,
    start: np.ndarray,
    protected: np.ndarray,
    config: SamplerConfig,
    steps: int,
    t0: float,
    index: int,
    cancel: np.ndarray,
) -> ChainOutcome:
    seed = config.seed + index
    cumulative = move_cumulative(config.move_weights)
    phases = policy_phases(config)
    owner = start.copy()
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    st = new_state(c.m)
    wellbeing_cap = deadline_cap = -1
    after_each_phase = []
    for n, phase in enumerate(phases):
        phase_steps = max(1000, int(steps * phase.share))
        tabu_steps = int(phase_steps * TABU_SHARE) if steps > config.tabu_after_steps and n == len(phases) - 1 else 0
        caps = (deadline_cap if phase.caps_deadlines else -1, wellbeing_cap if phase.caps_wellbeing else -1, -1)
        cap = np.array(caps, dtype=np.int64)
        median = median_delta(c, owner, protected, phase.weights, cumulative, seed * 7919 + n)
        init_state(c.m, st, owner)
        best = owner.copy()
        best_info = np.full(3, np.inf)
        work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
        run_chain(
            c.m,
            st,
            protected,
            phase.weights,
            cap,
            cumulative,
            *work,
            phase_steps - tabu_steps,
            t0 * median,
            config.t1 * median,
            1,
            0.0,
            seed * 1000 + n,
            best,
            stats,
            best_info,
            cancel,
        )
        if tabu_steps and not cancel[0]:
            tabu(
                c.m,
                st,
                protected,
                phase.weights,
                cap,
                cumulative,
                *work,
                max(1, tabu_steps // TABU_CANDIDATES),
                TABU_CANDIDATES,
                TABU_TENURE,
                seed * 1000 + n + 500,
                best,
                best_info,
                np.zeros(c.m.I, dtype=np.int64),
                np.zeros(TABU_CANDIDATES, dtype=np.int64),
                np.zeros(TABU_CANDIDATES, dtype=np.int64),
            )
        owner = best
        init_state(c.m, st, owner)
        wellbeing_cap, deadline_cap = int(st.stage_value[1]), tolerated(int(st.stage_value[0]))
        after_each_phase.append((int(st.stage_value[0]), int(st.stage_value[1]), int(st.stage_value[2])))
    init_state(c.m, st, owner)
    values = (int(st.stage_value[0]), int(st.stage_value[1]), int(st.stage_value[2]))
    return ChainOutcome(index, owner, values, stats, steps, after_each_phase)


def anneal(
    c: Compiled,
    start: np.ndarray,
    protected: np.ndarray,
    config: SamplerConfig,
    steps: int,
    warm: bool,
    warm_t0: float,
    cancel: np.ndarray | None = None,
) -> list[ChainOutcome]:
    """Run every chain from the same start; returns them best first."""
    cancel = np.zeros(1, dtype=np.int64) if cancel is None else cancel
    if c.m.I == 0:  # nothing to move, and every move proposal picks an item
        st = new_state(c.m)
        init_state(c.m, st, start)
        values = (int(st.stage_value[0]), int(st.stage_value[1]), int(st.stage_value[2]))
        return [ChainOutcome(0, start.copy(), values, np.zeros((N_MOVES, 3), dtype=np.int64), 0)]
    t0 = warm_t0 if warm else config.t0
    run = lambda index: run_one_chain(c, start, protected, config, steps, t0, index, cancel)  # noqa: E731
    if config.threads > 1 and config.chains > 1:
        with ThreadPoolExecutor(min(config.threads, config.chains)) as pool:
            outcomes = list(pool.map(run, range(config.chains)))
    else:
        outcomes = [run(index) for index in range(config.chains)]
    least_late = tolerated(min(o.stage_values[0] for o in outcomes))
    return sorted(outcomes, key=lambda o: (o.stage_values[0] > least_late, o.stage_values[1:], o.stage_values, o.index))


def tolerated(deadlines: int) -> int:
    return deadlines + int(deadlines * LATE_TOLERANCE)


# Sampling weighs wellbeing and preferences alike, as the research's pool did; deadlines stay a wall in effect.
SAMPLE_WEIGHTS = np.array([1e6, 1.0, 1.0])


def sample(
    c: Compiled, start: np.ndarray, temperature: float, steps: int, seed: int, move_weights: dict[str, float]
) -> np.ndarray:
    """A plan drawn near `start` at a fixed temperature (DESIGN §11.13): `temperature` times the median |Δ| of a
    random valid move. It keeps the chain's last state, not its best, so samples are genuinely different plans."""
    if c.m.I == 0:  # nothing to move, and every move proposal picks an item
        return start.copy()
    protected = protected_items(c.m, start)
    cumulative = move_cumulative(move_weights)
    t = temperature * median_delta(c, start, protected, SAMPLE_WEIGHTS, cumulative, seed)
    st = new_state(c.m)
    init_state(c.m, st, start)
    work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
    best, stats, info = start.copy(), np.zeros((N_MOVES, 3), dtype=np.int64), np.full(3, np.inf)
    cap, cancel = np.full(3, -1, dtype=np.int64), np.zeros(1, dtype=np.int64)
    run_chain(
        c.m, st, protected, SAMPLE_WEIGHTS, cap, cumulative, *work, steps, t, t, 1, 0.0, seed, best, stats, info, cancel
    )
    return st.owner.copy()
