"""Scheduler configurations for tests: the defaults with small budgets, so tests run in seconds."""

from dataclasses import replace

from friday.core.settings import DEFAULTS
from friday.engine.scheduler import SchedulerConfig, StepBudget
from friday.planner.build import scheduler_config


def fast(steps: int = 30_000, chains: int = 1, threads: int = 1, policy: str | None = None, seed: int = 0,
         fallback: bool = True, fallback_s: float = 2.0, **sampler: object) -> SchedulerConfig:  # fmt: skip
    base = scheduler_config(DEFAULTS, threads=threads)
    sampler_config = replace(base.sampler, chains=chains, threads=threads, seed=seed,
                             policy=policy or base.sampler.policy, **sampler)  # fmt: skip
    return replace(base, sampler=sampler_config, step_budgets=(StepBudget(10**6, steps, steps // 2),),
                   repair_steps=50_000, use_fallback=fallback, fallback_s=fallback_s, fallback_overload_s=fallback_s,
                   fallback_overload_warm_s=fallback_s, fallback_workers=4)  # fmt: skip
