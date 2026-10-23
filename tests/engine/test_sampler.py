"""Sampler guarantees: valid plans, walls that hold, determinism across thread counts, cancellation."""

import threading
import time

import numpy as np
import pytest

from friday.engine.checker import check
from friday.engine.construct import prepare_start
from friday.engine.evaluate import evaluate
from friday.engine.kernel import protected_items
from friday.engine.sampler import anneal
from friday.engine.scheduler import schedule
from tests.bench.generator import ADVERSARIAL, reference_instance
from tests.engine.configs import fast

FAMILIES = {"ref20": lambda s: reference_instance(20, s), **ADVERSARIAL}


def started(sc):  # noqa: ANN001, ANN201
    p = sc.build()
    start = prepare_start(p)
    return p, start.c, start.owner, protected_items(start.c.m, start.owner)


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("policy", ["lexpolish", "weighted", "strict"])
def test_every_policy_keeps_every_wall_and_every_protected_item(family: str, policy: str) -> None:
    p, c, owner, protected = started(FAMILIES[family](2))
    best = anneal(c, owner, protected, fast(policy=policy).sampler, 20_000, False, 0.01)[0]
    plan = c.plan_from_owner(best.owner)
    keys = [c.keys[i] for i in np.flatnonzero(protected)]
    assert check(p, plan, keys) == []
    assert list(best.stage_values) == [
        evaluate(p, plan).stage_values[s] for s in ("deadlines", "wellbeing", "preferences")
    ]


@pytest.mark.parametrize("seed", range(4))
def test_the_lexpolish_polish_never_raises_wellbeing(seed: int) -> None:
    p, c, owner, protected = started(reference_instance(30, seed))
    best = anneal(c, owner, protected, fast().sampler, 30_000, False, 0.01)[0]
    search, polish = best.after_each_phase
    assert polish[1] <= search[1]
    assert polish[2] <= search[2] or polish[1] < search[1]


def test_the_same_seed_and_budget_give_the_same_plan_on_1_2_and_8_threads() -> None:
    p = reference_instance(40, 4).build()
    plans = [schedule(p, fast(steps=20_000, chains=8, threads=t)).plan for t in (1, 2, 8)]
    assert plans[0] == plans[1] == plans[2]


def test_another_seed_gives_another_plan() -> None:
    p = reference_instance(20, 4).build()
    assert schedule(p, fast(seed=1)).plan != schedule(p, fast(seed=2)).plan


def test_the_tabu_finish_runs_on_large_budgets_and_keeps_the_walls() -> None:
    p, c, owner, protected = started(reference_instance(20, 5))
    config = fast(tabu_after_steps=10_000).sampler
    best = anneal(c, owner, protected, config, 20_000, False, 0.01)[0]
    assert check(p, c.plan_from_owner(best.owner), [c.keys[i] for i in np.flatnonzero(protected)]) == []


def test_a_cancel_flag_stops_the_chains_well_inside_their_budget() -> None:
    p, c, owner, protected = started(reference_instance(60, 1))
    cancel = np.zeros(1, dtype=np.int64)
    done: list[float] = []

    def run() -> None:
        anneal(c, owner, protected, fast().sampler, 50_000_000, False, 0.01, cancel)
        done.append(time.perf_counter())

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.5)
    cancel[0] = 1
    stopped = time.perf_counter()
    worker.join(timeout=30)
    assert done and done[0] - stopped < 2.0  # 50M steps would take about a minute


def test_a_cancel_flag_stops_a_running_deadline_fallback() -> None:
    from friday.engine.scheduler import schedule
    from tests.bench.generator import overload

    p = overload(0).build()
    cancel = np.zeros(1, dtype=np.int64)
    timer = threading.Timer(1.0, lambda: cancel.__setitem__(0, 1))
    timer.start()
    began = time.perf_counter()
    result = schedule(p, fast(steps=10_000, fallback_s=30.0), cancel=cancel)
    assert time.perf_counter() - began < 10  # the fallback alone was given 30 s
    assert result.cancelled and check(p, result.plan, result.protected) == []
