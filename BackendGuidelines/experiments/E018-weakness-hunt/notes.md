# E018 notes — weakness hunt

Run: 6 adversarial families x 6 seeds (tuning range) x 3 engines, 10 s for v3 variants, 30 s for CP-SAT (8 workers),
2026-10-17 17:35-18:20. From 17:41 the process ran at background QoS (efficiency cores) at a co-tenant's request, so times are
slow for every engine after that. `results/runs.csv`. Engines: `v3` (construction -> sampler repair -> CP-SAT deadline fallback
5 s -> wall sampler with lexpolish for what is left of 10 s), `v3_nocp` (no CP-SAT), `cpsat30` (staged v2).

| family | what it attacks | deadline-safe: v3 / v3_nocp / CP-SAT | at the best known lateness: v3 / v3_nocp / CP-SAT | median late (points): v3 / v3_nocp / CP-SAT |
| --- | --- | --- | --- | --- |
| tight one-sitting | greedy packing of one-sitting items | 100% / **50%** / 100% | 100% / 0% / 100% | 168k / 966k / 168k |
| tight + 2 h min chunks | fragmentation | 100% / 100% / 100% | 83% / 0% / 100% | 105k / 186k / 105k |
| 30-item dependency chain | dependency readiness | 100% / 100% / **0%** | 100% / 100% / 0% | 0 / 0 / 42.6M |
| 40 pins | locks everywhere | 100% / 100% / **0%** | 100% / 100% / 0% | 0 / 0 / 36.7M |
| 2.2x overload | unavoidable lateness | 100% / 100% / 100% | 67% / 100% / 0% | 92.6M / 92.4M / 210.9M |
| 150 items | size | 100% / 100% / 83% | **33%** / 100% / 0% | 259k / 177k / 54.4M |

All plans valid for every engine. "Deadline-safe" = zero late wherever zero is known possible; lateness is unavoidable in the
tight, overload and stress families, so the "at the best known lateness" column is the stricter test there.

## Failure catalogue

1. **Greedy packing (one-sitting, big chunks).** Without CP-SAT the sampler stays 2-6x later than the optimum on tight one-sitting
   packing: moving a whole one-sitting item into a gap other items occupy needs coordinated moves the sampler rarely accepts
   under walls. CP-SAT's deadline stage solves these small instances exactly in ~7 s. -> **keep the CP-SAT fallback.**
2. **The fallback eating the budget (v3 as built for E018).** On 150 items and 2.2x overload, CP-SAT's 5 s deadline solve (plus
   model build, ~25 s in total on efficiency cores) improved nothing and left no time for annealing, which on its own (v3_nocp)
   reduced lateness further (stress150: 177k vs 259k median; 3/6 instances worse). -> **run annealing first, CP-SAT only if
   lateness remains** (fixed in `engines/api.run_v3`, re-run in E018b).
3. **v2 under adversarial structure.** CP-SAT-30 found no deadline-feasible plan for any long dependency chain or many-pins
   instance (it times out and returns lateness of 37-43M points), and on 150 items it misses 67 hard items on median. These are
   the families where construction (which honors dependencies and locks by design) is strongest.

No family broke validity or made v3 late where v3_nocp was not, except through the budget issue in (2).
