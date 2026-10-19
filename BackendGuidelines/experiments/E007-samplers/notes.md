# E007 notes — samplers and speed

Run: reference n=40, n=60 and Cornell, tuning seeds 0-9 (30 instances) x 10 samplers x 2 budgets (2 s, 8 s), 2026-10-17
14:34-15:16, load 11-35. Tiered stages for every method (E006 later showed tiered is the weaker stage scheme; the comparison
between samplers is unaffected). Kernel speed: 548k proposals per second median (single thread, M3 Max, under load).
Cold numba compile (empty cache, fresh process): **66 s**; with the on-disk cache, about 1 s. `results/runs.csv`,
`figures/sampler_ranks.png`.

| sampler | mean lexicographic rank, 2 s (of 10) | 8 s | instances better / worse than geometric SA, 8 s |
| --- | --- | --- | --- |
| multi-start, 8 chains on 8 threads | **2.3** | 2.8 | 26 / 4 |
| parallel tempering, 8 replicas, 8 threads | 2.9 | **2.7** | 26 / 4 |
| population annealing, 32 members, 8 threads | 3.5 | 2.8 | 25 / 5 |
| SA (80%) then tabu (20%), 1 thread | 6.8 | **5.1** (best single-thread) | 17 / 13 |
| geometric SA, Metropolis, 1 thread | 6.1 | 6.1 | - |
| linear schedule | 6.1 | 6.4 | |
| heat-bath acceptance | 6.7 | 6.8 | 13 / 17 |
| zero-temperature descent | 5.0 | 6.5 | 12 / 18 |
| fixed moderate temperature, no annealing | 5.8 | 7.0 | 14 / 16 |
| parallel tempering on 1 thread | 10.0 | 8.7 | 5 / 25 |

At 8 s the 8-thread methods reach the best known wellbeing on 77-90% of instances (single thread 40-63%).
Every run was valid. Lateness: on 4 instances whose constructed start was late (unprotected items), the fixed-temperature
chain left 125-45k points of lateness that other samplers removed; the production pipeline repairs the start first (E005).

## Against the hypotheses

1. **Only partly.** Geometric SA beats a fixed temperature at 8 s (16 vs 14 instances, mean rank 6.1 vs 7.0) but not at 2 s, and
   zero-temperature descent is competitive at 2 s (rank 5.0): from a good constructed start the landscape is mostly "walk
   downhill". Annealing pays off with time.
2. **Confirmed.** Heat-bath and Metropolis are within noise (13/17).
3. **Confirmed.** PT on 8 threads is among the best; PT on one thread is the worst method (8 replicas share one core, each gets
   1/8 of the steps).
4. **Confirmed.** Independent multi-start on 8 threads is as good as PT-8 (ranks 2.3-2.8 vs 2.7-2.9): replica exchange adds
   little over restarts at these budgets.
5. **Refuted mildly.** Tabu as a finisher helps at 8 s (best single-thread method, 17/13) but not at 2 s.
6. Against CP-SAT: see E004 (every sampler here at 2 s already matches or beats CP-SAT-30 s on comparable stages).

## Recommendation (P4 exit, with E006b's stage scheme)

Geometric SA chains from the repaired start; on a laptop use as many independent chains as idle performance cores (multi-start
is simpler than PT and equally good; keep PT as the T > 0 sampler when samples, not just the best plan, are wanted: E010); finish
with a short tabu phase when the budget allows more than ~5 s. Fixed step budgets per instance size for determinism (E009).
