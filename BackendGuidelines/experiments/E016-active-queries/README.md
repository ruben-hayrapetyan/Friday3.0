# E016 — Active querying: which comparisons to show (RQ8)

**Question.** If Friday may ask the user to compare two plans now and then, which pairs should it ask about? Random pairs
from its sample pool, uncertainty sampling (the pair whose predicted preference is closest to 50/50), or query-by-committee
(the pair a bootstrap ensemble disagrees on most)? Measured as queries needed to reach a held-out ranking accuracy.

**Setup.** 8 easy and 8 noisy users. Candidate pool per user: 3 Cornell-style instances x 30 plans (samples at T > 0 from plans
optimised for random weight vectors), all within-instance pairs (1305). Held-out: 200 noise-free pairs on a fourth instance.
Learner: Bradley-Terry MAP over the library features (prior at the hand-set weights). Up to 60 queries, refit after each;
5 repetitions per user and strategy (different random streams for the user's noise and for random selection).

**Metrics.** held-out accuracy after k queries; queries to reach 85% and 90% (censored at 60).

**Hypotheses.** Uncertainty sampling reaches 85% with about half the queries random needs for easy users; with noisy users its
advantage shrinks (it keeps asking near-ties, where answers are coin flips), and QBC is more robust there.
