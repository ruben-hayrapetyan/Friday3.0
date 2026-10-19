# E014 notes — missing-feature detection and rule proposal

Run: 12 missing-feature users + 12 users without one (easy), 12 weeks, 10 ranked pairs a week (+ drags), 132 candidate rules,
2 shards, 2026-10-17 14:13-14:20. Users 0-5 of each type tuned the threshold; users 6-11 are the evaluation.
`results/checkpoints_*.csv`, `results/regret_*.csv`, `results/threshold.txt`, `analysis.txt`.

## Threshold (tuning users)

Max cross-validated gain per ranking over all checkpoints, easy tuning users: 0.032, 0.038, 0.048, 0.092, 0.114, 0.273.
Threshold = the second largest, 0.114 (at most 1 of 6 tuning users ever flagged). Missing-feature users' true rule gains
0.13-0.59 per ranking, but early on (week 4) some are as low as 0.05.

## Evaluation users (6 + 6)

| week | missing-feature users: a rule proposed / the right one | users without one: a rule proposed (all false) |
| --- | --- | --- |
| 4 | 100% / 100% | 33% |
| 6 | 83% / 83% | 17% |
| 8 | 100% / 100% | 17% |
| 10 | 83% / 83% | 0% |
| 12 | 100% / 100% | 0% |

Whenever a proposal is made for a missing-feature user it is the right rule (fri/sat x evening/late): the true rule ranks
first among 132 candidates in the median at every checkpoint. For users without a missing feature, the best candidate's
gain shrinks with data (median rank of the "true" rule drops to 5-8 because nothing is there), and false proposals vanish by
week 10. Across all 12 users of each type (tuning included) the correct rule is the top candidate for 12/12 missing-feature
users by week 12 (11/12 at week 10).

## Regret (week 12, one plan per policy; relative)

| | auto-add | flag only | true rule with true weight |
| --- | --- | --- | --- |
| missing-feature users, median | 0.122 | 0.029 | 0.046 |
| users without one, median | 0.027 | 0.063 | 0.063 |

**Inconclusive.** Even planning with the true rule and true weight does not beat flagging-only on this metric: the missing
preference (no work on Friday/Saturday evenings) rarely binds in these two-week instances, and single-plan regret has a
spread of about +-0.15 between policies on the same user (sampler noise). The value of a found rule must therefore be judged
by ranking accuracy and by asking the user, not by regret on 12 users.

## Against the hypotheses

1. **Confirmed, faster than expected**: right rule for 100% of evaluation users by week 4 (40 rankings), never a wrong rule
   for them.
2. **Partly**: false proposals on evaluation users run 33% at week 4, then fall to 0% by week 10. Early checkpoints need a
   stricter threshold or must stay in "suggest" mode (ask the user before adding).
3. **Not supported by this data** (see regret).

**Policy recommended**: propose (never auto-add) from the ranking log, at a threshold tuned for <= 1/6 false flags, only from
week 6 on (60 rankings) or when the same candidate wins two checkpoints in a row; show the user the rule in plain words
("Avoid work on Friday and Saturday evenings?") and add it only on a yes. That keeps the discovery rate of auto-add without
its early false rules, and the learned layer stays editable.
