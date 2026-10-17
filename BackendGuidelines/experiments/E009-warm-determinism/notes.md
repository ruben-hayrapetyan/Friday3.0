# E009 notes — warm replans, churn, determinism

Run: reference n=40, n=60 and Cornell, tuning seeds 0-9 (30 warm instances: +2 items, -1 item, `current` = the sampler's own
5 s cold plan so `minimize_changes` is active), 2026-10-17 15:30-16:13, load ~12. Sampler runs repeated with the same seed.
`results/runs.csv`, `analyze.py`.

| method | zero late | mean lexicographic rank (of 8) | wellbeing gap | preferences gap | churn h, median (p90) | seconds, median (p90) | identical rerun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CP-SAT warm, 30 s | **93%** | **1.4** | 0.000 | 0.000 | **37.6** (62.2) | 23.7 (27.2) | - |
| sampler warm, 3 s | 90% | 2.2 | 0.000 | 0.69 | 46.4 (58.3) | 2.3 (2.6) | 100% |
| sampler cold, 3 s | 87% | 3.5 | 0.031 | 0.57 | 51.9 (71.6) | 2.3 (2.6) | 97% |
| sampler warm, 1 s | 90% | 3.7 | 0.030 | 1.78 | 44.1 (59.3) | 0.75 (0.86) | 100% |
| sampler warm, 0.5 s | 90% | 4.8 | 0.050 | 2.16 | 44.3 (63.1) | 0.38 (0.43) | 100% |
| sampler cold, 1 s | 80% | 5.8 | 0.093 | 2.55 | 55.5 (76.5) | 0.78 (0.87) | 100% |
| sampler cold, 0.5 s | 80% | 6.9 | 0.450 | 2.49 | 62.6 (79.1) | 0.41 (0.45) | 100% |
| CP-SAT warm, "10 s" | 33% | 7.7 | 0.038 | 15.0 | 100.9 (110.8) | 22.5 (30.1) | 53% |

## Against the hypotheses

1. **Partly.** Warm at 1 s beats cold at 1 s and nearly matches cold at 3 s; warm at 0.4-0.8 s meets the reference's warm target
   (p90 <= 3 s) by a wide margin while CP-SAT warm takes 24 s (and is useless at a 10 s budget: 33% zero late). But **CP-SAT
   at 30 s wins on quality** (rank 1.4 vs 2.2 for warm 3 s; its preferences are ~0.7 better relative): with a good hint (the
   previous plan) and 10x the time, CP-SAT is strong. Under the lexicographic order the sampler's warm 3 s plans tie
   CP-SAT-30 on wellbeing (median gap 0).
2. **Refuted.** Warm churn is lower than cold (44 vs 52-63 h) but **higher than CP-SAT's** (37.6 h). Cause: the tiered stage
   scheme anneals wellbeing first with preferences (where `minimize_changes` lives) switched off, so the first phase moves
   work freely. E009b re-tests churn with the weighted-then-polish scheme (E006), where `minimize_changes` counts throughout.
3. **Confirmed with one exception that proves decision 20.** Every warm rerun was bit-identical; one cold 3 s rerun differed.
   Cause: `solve_sampler` subtracts the measured calibration time from the budget before sizing the step count, so the step
   count depends on the clock. With a fixed step budget the plans are identical; CP-SAT with 8 workers gave the same plan on only
   53% of reruns.

**Lateness.** The sampler left lateness on 3 warm instances: two (ref-n40-s7, -s8) where CP-SAT-30 has the same lateness and
CP-SAT's deadline stage (5 s) cannot remove it either (locks/pins), and one (ref-n60-s7, 125 points) that the production
pipeline's sampler repair removes in 0.6 s (re-run separately). This experiment started the sampler straight from construction,
without the repair step; the recommended pipeline always repairs first.
