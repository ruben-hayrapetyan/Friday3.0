## 3. Baseline results (v2: staged CP-SAT on the slot grid)

The baseline is a faithful minimal build of reference section 6A: x / start / cum / any variables, constraints C1-C8, the three
stages each frozen at the evaluator's exact value before the next, a locks-only hint, and the reference's repair of
contradictory locks extended to an unsat-core relaxation (locks can contradict dependencies and chunk limits, which the
reference did not cover). It passes reference scenarios 1-9 and 11-24 and matches brute force on 20 tiny instances.

**E001 (idle laptop, 8 workers, 30 s per solve, reference benchmark n = 20/40/60, seeds 0-9, cold and warm):**

| target (reference 12.4) | required | measured |
| --- | --- | --- |
| cold solve p90 | <= 10 s | 20.5 / 30.2 / 30.7 s (at the cap) |
| warm replan p90 | <= 3 s | 17.7 / 24.7 / 26.2 s |
| deadlines stage | <= 3 s | 4.1 / 7.8 / 10.2 s median |
| executor at 100 items | <= 50 ms | 0.1 ms |
| allocator | <= 1 s | 0.13 s |

The preferences stage was never proven optimal (bound gap 63-94% at its time limit); wellbeing was optimal on 100% / 30% /
10% of runs; repeated solves of one instance with 8 workers differed by up to 2x in the preferences value, so the reference's
"same input, same plan" holds only with one worker; one n=40 run froze a stage-1 plan with 606 hours of lateness.

![Baseline time](report/figures/baseline_time.png)

**E002: tuning it at 10 s.** Six fair variants (fewer fine days, a shorter horizon, one worker, a zero-late constructive plan
as the hint, different stage shares): every variant either timed out (the stage limits double once, so "10 s" took 20-25 s) or
returned hundreds of late hours. Even with a zero-late hint, 7/10 runs timed out: the hint is feasible (fixing variables to it
solves in 0.12 s and the model's stage values equal the evaluator's), but the preferences stage cannot finish presolve inside
its 3 s share. **So the fair baseline is v2 at its own 30 s budget; at equal time (10 s) it is not competitive.**

**Under load.** From session 2 the laptop was shared with a live service. CP-SAT with 8 workers suffered most: "30 s" solves
took 61 s median and were deadline-safe on only 30% of 40 instances (E004), against 70-100% zero-late on the idle laptop (cold: 90% / 70% / 100% at n = 20 / 40 / 60)
(E001). A design that needs eight idle cores for half a minute is fragile on a user's laptop; the sampler uses one core per
chain and scales down gracefully.
