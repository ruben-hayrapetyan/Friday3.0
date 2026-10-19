# E013c notes — a gate that temperature alone cannot open (round 3)

Run: E013 protocol, modes none / dial / gated2, 2 shards, 2026-10-17 15:01-15:10. gated2 uses the dial units only when their
cumulative predictive log-likelihood beats taste-only at its best answer temperature (grid 0.02-0.5) by 2 nats, or in a week
the user picked a pace. (The taste-only model had already learned from the week when the gate scored it, which biases the
gate towards staying closed.)

| regret, mean | none | dial (always on) | gated2 |
| --- | --- | --- | --- |
| moody, weeks without a pace | 0.133 | **0.079** | 0.119 |
| moody, pace weeks | 0.183 | **0.080** | 0.097 |
| easy, weeks without a pace | **0.066** | 0.099 | 0.069 |
| noisy, weeks without a pace | 0.167 | 0.164 | 0.167 |

(Easy and noisy users also "pick a pace" in 6% of weeks, matching a mood that changes nothing for them; those weeks penalise
any mode that trusts a pace, an artefact of the simulation.)

## Findings

1. **The cost is gone.** Outside pace weeks gated2 matches no-units for easy (0.069 vs 0.066) and noisy users (0.167 vs 0.167):
   comparing against a temperature-calibrated baseline stops the units from opening the gate by softening predictions.
2. **So is most of the gain.** For moody users gated2 (0.119) recovers only a quarter of always-on units' gain (0.079 vs
   none 0.133): with 6 ranked pairs a week the units need many weeks to prove themselves against a calibrated baseline.
3. Three rounds give a clear trade-off rather than a free win: always-on units help moody users by 30-40% and cost the rest
   30-60%; a calibrated gate is safe but slow. Explicit signals (a picked pace, a check-in) are where the units are worth using
   without proof; automatic state inference should stay behind the calibrated gate and become faster only with more data per
   week (more rankings, or skips and reviews with learned links).
