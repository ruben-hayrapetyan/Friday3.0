# E010 — Diversity and calibration of T > 0 samples (RQ10)

**Questions.** (A) Does the chain sample the Boltzmann distribution over valid plans correctly (is the move set ergodic under
walls, and do marginals converge)? (B) Are T > 0 samples meaningfully different plans, or tiny variations of one plan? (C) Are
statements like "item X lands on Tuesday with 70%" calibrated against what a (simulated) user actually does?

**Setup.**
- A: tiny instances (8 slots, 3 items, tuning seeds 0-9), every valid plan enumerated, exact p(x) ~ exp(-E(x)/T) for
  E = 1e6 x deadlines + wellbeing + preferences (no deadline protection, walls on). 16 chains x 20k steps at T, samples
  every 50 steps after 2k burn-in. Metric: total-variation distance to the exact distribution, and the share of valid plans the
  chains ever visit. Temperatures: T = 1, 3, 10 x the median |delta| of the instance.
- B: reference n=40 seeds 0-4. From the tiered 8 s plan, 16 chains x 200k steps at T in {0.003, 0.01, 0.03, 0.1} x median |delta|
  (the single-tier energy wellbeing + preferences, deadlines walled). Metrics: mean pairwise share of work slots that differ,
  number of distinct day patterns per item, mean energy excess over the start (points).
- C: simulated users (easy and noisy types, 3 users each, 6 weeks each on Cornell instances). Friday knows the true weights;
  it predicts p(item has work on day d in the lived week) from 16 samples at T_f in {0.3, 1, 3} x the user's choice
  temperature. Reliability (binned predicted vs observed) and Brier score against the user's lived week.

**Hypotheses.** (A) TV distance falls with more samples and is small at T >= 3 x median; some valid plans are unreachable at
low T in the time given (walls make the space fragmented). (B) Below T = 0.01 x median the samples are near copies; at
0.03-0.1 they differ in 10-30% of slots at an energy cost of a few percent. (C) Predictions are calibrated only when T_f
matches the user's own noise; too cold is over-confident.
