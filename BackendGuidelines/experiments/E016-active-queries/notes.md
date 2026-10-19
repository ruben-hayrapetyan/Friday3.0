# E016 notes — active querying

Run: 8 easy + 8 noisy users, pools of 3 instances x 30 plans (1305 candidate pairs), 200 held-out noise-free pairs on a fourth
instance, Bradley-Terry MAP refit after each query, 60 queries, 5 repetitions per user and strategy, 2026-10-17 14:20-14:29.
`results/curves.csv`, `figures/active_queries.png`.

## Held-out accuracy (mean over users and repetitions)

| queries | 0 | 5 | 10 | 20 | 40 | 60 |
| --- | --- | --- | --- | --- | --- | --- |
| easy, random | 0.798 | 0.835 | 0.846 | 0.872 | 0.888 | 0.904 |
| easy, uncertainty | 0.798 | 0.841 | 0.861 | 0.897 | **0.924** | 0.931 |
| easy, query-by-committee | 0.798 | **0.862** | **0.865** | **0.901** | 0.921 | **0.935** |
| noisy, random | **0.821** | 0.763 | 0.757 | 0.743 | 0.742 | 0.762 |
| noisy, uncertainty | 0.821 | 0.771 | 0.778 | 0.791 | 0.808 | 0.818 |
| noisy, query-by-committee | 0.821 | 0.797 | 0.793 | 0.797 | 0.813 | 0.825 |

Queries to reach 90% held-out accuracy (median; share of user-repetitions that reach it within 60): easy users: QBC 10
(95%), uncertainty 11.5 (97.5%), random 25 (80%). Noisy users: no strategy reaches 90% in the median (QBC 45%, uncertainty 33%,
random 38% of runs ever do).

## Against the hypothesis

- **Confirmed for easy users**: active selection halves the questions needed (10-12 vs 25 for 90%), and QBC and
  uncertainty sampling are within noise of each other.
- **Stronger than expected for noisy users**: every strategy *loses* accuracy against the hand-set prior for the first 20-60
  answers (0.821 -> 0.74-0.80): answers from a noisy user (Bradley-Terry temperature 2x the typical energy gap) move the
  weights more than they inform them. QBC degrades least and recovers to the prior by 60 queries; random never does.
- So "ask" has a cost model: with an easy user, 10 good questions buy +10 points of accuracy; with a noisy one they buy
  nothing for a long time. The supervisor should estimate the user's answer noise (from consistency across repeated or
  near-duplicate pairs) and stop asking, or ask only near-tie pairs that QBC flags, when the noise is high.

**Recommended**: query-by-committee (6 bootstrap fits) to choose pairs; at most ~10 questions per user in the first weeks;
stop when the committee's disagreement on its own top pair falls below 20%, or when answers are inconsistent with themselves.
