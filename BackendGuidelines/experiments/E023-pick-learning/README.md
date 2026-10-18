# E023 — Learning from the pick (RQ15)

**Question.** When the user picks one of three schedules, how should Friday learn from it so the recommended option
becomes the one they would pick? Compare learning from picks (multinomial logit over the three plans, or "rank
breaking": the pick beats each of the other two as Bradley-Terry pairs) with and without the existing feedback (pairs
and drags, E011b), against no learning and against the existing feedback alone (picks ignored).

**Set-up.** `src/fr/sim/picks.py` with the generator chosen in E022. Simulated users (easy, noisy, moody, missing rule,
adversarial), 3 per type on tuning seeds, 12 weeks, a fresh Cornell-style instance each week. Robustness: users who lean
toward the recommended option (pick it outright 30% of the time, a status-quo bias) — does learning stall?

**Metrics.** Share of weeks the user picks the recommended option (overall and in weeks 8-11), regret of the
recommended plan, weight cosine with the truth, and how far one week's evidence moves the weights (1 - cos between
consecutive weeks; a single odd pick should not flip the recommendation).

**Expectation.** Picks alone learn slower than pairs + drags (one bit-ish per week vs six pairs and a drag), but add to
them; MNL and rank breaking are close; a status-quo lean slows learning but does not bias it.

**Generator** (set after E022 round 2, before running): `thompson+post`: Thompson alternatives, the three ranked so that
option 0 has the highest posterior-mean pick probability.
