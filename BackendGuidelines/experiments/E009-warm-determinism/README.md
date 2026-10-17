# E009 — Warm replans, churn, determinism, explanations (RQ9, RQ4 warm starts)

**Question.** The reference's hardest target is the warm replan (p90 <= 3 s; v2 took 18-26 s, E001). When two items are added
and one removed, how fast does the wall sampler, warm-started at a low temperature from the previous plan, reach a good
plan, and how much does it move (churn) compared with a cold sampler and with CP-SAT warm (hint = previous plan)? Are
the plans deterministic (same input, seed and profile give the same plan)?

**Setup.** Reference n=40, n=60, Cornell; tuning seeds 0-9. Previous plan = the sampler's own 5 s cold plan. Warm snapshot =
the reference warm variant (+2 items, -1 item), with `current` = previous plan so `minimize_changes` is active, exactly as
in v2. Warm start = previous plan kept where still allowed, new items added by construction. Methods: sampler warm (T0 at
0.01 x median |delta|), sampler cold (from construction), both at 0.5 / 1 / 3 s; CP-SAT warm at 10 s and 30 s (8 workers).
Determinism: every sampler run is repeated with the same seed and a fixed step count; CP-SAT-10 s is repeated once.

**Metrics.** lexicographic value vs best known, churn (hours of surviving items' work that moved), time, identical rerun.

**Hypotheses.** (1) Sampler warm at 1 s matches sampler cold at 3 s and beats CP-SAT warm at 30 s on lexicographic value.
(2) Warm churn is far below cold churn, and below CP-SAT's. (3) Sampler reruns are bit-identical; CP-SAT with 8 workers is not.
