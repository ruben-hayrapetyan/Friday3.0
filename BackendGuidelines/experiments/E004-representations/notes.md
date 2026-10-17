# E004 notes — representations on equal budgets

Run: 40 instances (reference n=20/40/60, Cornell; tuning seeds 0-9) x 6 engine settings, 2026-10-17 11:50-13:06, on a
shared, heavily loaded laptop (load average 30-190 on 16 cores; jobs at nice 19). `results/runs.csv`, `runs_scored.csv`,
`figures/engines.png`, `analyze.py`. Best known = best valid value any engine produced (E004, E006-E009, E018).

## Results (all 40 instances)

| engine | valid | deadline-safe | wellbeing gap, median | preferences gap, median (comparable runs) | median s |
| --- | --- | --- | --- | --- | --- |
| wall sampler, 10 s | 100% | **100%** | 0.000 | 0.000 (27/40) | 7.4 |
| Potts + penalties (lambda 1e6), 10 s | 100% | 95% | 0.000 | 0.000 (22/40) | 8.7 |
| skeleton hybrid (CP-SAT stage 1 + walls), 10 s | 100% | 95% | 0.075 | 0.080 (14/40) | 9.8 |
| walls + CP-SAT LNS polish, 10 s | 100% | **100%** | 0.050 | 0.044 (17/40) | 10.7 |
| CP-SAT staged, "30 s" | 97% | 30% | 0.000 (8 comparable) | 0.42 (6) | 61 |
| CP-SAT staged, "10 s" | 97% | 12% | 3.1 (1) | - | 16 |

Deadline-safe = valid and zero late work whenever zero late is known possible. A stage gap is only computed when the
earlier stages tie the best known value; "comparable" counts those runs.

## Against the hypotheses

1. **Walls beat penalties on the guarantee, narrowly on quality.** Penalties at 1e6 per violation behave almost like walls
   when the start is feasible, but on 2/40 instances (ref-n40-s6, ref-n60-s5) the penalty chain ended late (one hard item)
   where walls reached zero. Cause, reproduced: on ref-n40-s6 the constructed start is itself late (1.71M); under walls the
   unprotected late item can only move to cheaper places, and the wall chain reached 0; the penalty chain spends its time in
   infeasible states (a violation costs 1e6, lateness of a unit costs ~1e8) and its best feasible state stayed late (1.55M).
   E004b sweeps penalty scales properly.
2. **Partly wrong:** construction is not always zero-late when zero is possible (ref-n40-s6). Walls + annealing fixed it here;
   E005 measures how often construction alone fails.
3. **Wrong:** the CP-SAT skeleton hurt. A 3 s stage-1 solve is often *later* than construction (ref-n40-s7: 45k late), and the
   hybrid used it blindly; on 2 instances it ended late. Fixed after this run (keep the better start, decision 23).
4. **Confirmed and stronger than expected.** At 10 s the wall sampler ties or beats CP-SAT-30 s on every comparable stage, and
   CP-SAT is deadline-safe on only 30% at "30 s" under this load (E001, idle: 70-100% zero late). CP-SAT also overran its budget
   (median 61 s for "30 s": the stage limits double when a stage finds nothing).
5. **Wrong:** LNS polish did not help at 10 s; each neighbourhood solve pays CP-SAT model build and presolve (~1-2 s), so it
   replaces ~40% of annealing with a handful of exact moves. Wellbeing gap 0.05 vs 0.

## Shortlist for P4

1. **Slot-assignment state + chunk moves + walls** (the wall sampler), with construction and repair as the start.
2. **The same with a CP-SAT deadline fallback** used only when construction + repair leave lateness (not as a skeleton
   for every instance). E005 and E018 decide whether it is needed.
Dropped: strict QUBO (E003), penalty-only Potts (no guarantee), LNS (too slow per neighbourhood), the always-on skeleton.

## Surprises

- CP-SAT under load is far worse than on an idle laptop; its 8 workers compete with everything else, while the sampler
  uses one core. A design that needs 8 idle cores for 30 s is fragile on a user's laptop.
- cornell-s7: CP-SAT returned no plan at all (time-out) in both budgets; the locks-only fallback plan breaks a hard rule (a
  partially placed one-sitting lock).
