# E013b notes — gating hidden units per user (round 2)

Run: E013 protocol with the multiplicative link and drags x3, modes none / dial (always on) / gated (dial units only after a
cumulative predictive gain > 2 nats over taste-only, or in pace weeks), 2 shards, 2026-10-17 14:52-15:01.

| regret, median (mean) | none | dial | gated |
| --- | --- | --- | --- |
| moody users | 0.106 (0.141) | **0.065** (0.079) | 0.086 (0.117) |
| easy users | **0.050** (0.061) | 0.095 (0.097) | 0.084 (0.094) |
| noisy users | 0.118 (0.165) | 0.098 (0.169) | 0.160 (0.176) |

Per-user "state or noise" over all 16 weeks: easy 2/3 noise, moody 2/3 state, noisy 1/3 noise: **5/9 right** (E013: 8/9).

## Findings

1. Always-on dial units again help moody users (0.106 -> 0.065, replicating E013's 0.078 -> 0.051) and again cost easy users
   (0.050 -> 0.095).
2. **The gate failed.** It opened for one easy user and two noisy users. Cause, on inspection of the test: the units can win the
   predictive comparison without any state, by shrinking the effective weights and so *softening* predictions, which fits a
   noisy user's answers better. The test compares "units" with "taste at a fixed answer temperature", so it partly measures
   temperature, not state. E013's 8/9 was with the additive link, where this shrinkage was weaker.
3. Round 3 (E013c): compare the units against taste-only at its best-fitting answer temperature (E011c's noise estimate), so
   that softening alone cannot open the gate.
