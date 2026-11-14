## 8. The supervisor: routing feedback, missing features, softening walls, active queries (RQ8)

**Routing (built in `fr/system.py`, `fr/supervisor/`).**

| feedback | goes to | how |
| --- | --- | --- |
| a plan that breaks a hard rule; a new hard rule from the user | a wall | added to the problem as a forbid/lock; the kernel's moves can never produce it again |
| a ranking "A better than B"; a manual drag (the user's version beats Friday's) | the ranking model | Bradley-Terry likelihood over all rankings, drags x3, prior at the hand-set weights (a likelihood, not hard constraints: E011) |
| rankings that contradict each other over time | hidden units | only if the per-user predictive test says "state" (E013); otherwise they are noise and stay in the likelihood |
| lived weeks | the likelihood term (CD) | a small step that moves the prior's center; never on its own (E011) |
| skipped blocks, "not done", check-ins | state evidence | the skip link and the check-in likelihood of the hidden units |
| rankings no weights explain | rule proposal | cross-validated gain of each template rule (E014) |
| work logged inside a "never" window | wall review | one question (E015) |

**Missing features (E014).** A grammar of 132 `time_preference` templates (11 day sets x 6 windows x scope any/deep). For each,
the 5-fold cross-validated gain in ranking log-likelihood when its feature is added; a threshold of 0.114 nats per ranking
was tuned on 6+6 tuning users. On 6+6 fresh users: the right rule ("no work Friday/Saturday evenings") was proposed for 6/6
missing-feature users by week 4 (40 rankings) and was the top candidate at every checkpoint after; users without a missing
feature got false proposals in 33% of week-4 checks, 17% at weeks 6-8 and none from week 10. Auto-adding vs flagging could
not be separated on regret (single-plan regret noise of about +-0.15 exceeds the effect of a preference that rarely binds in
two-week instances). Policy: propose (do not auto-add) from week 6, in plain words, and add the rule on a yes; a refused
proposal is removed from the candidate list. In the end-to-end system (E017) proposals are confirmed by the simulated user.

**Softening "never" walls (E015).** Keeping a stale wall and dropping a real one cost about the same (28 vs 30 points per
two-week plan, ~3% of a plan's energy). Over 12 weeks: ask once at the first contradicting event, regret 15 (0.67 questions per
user); soften after 3 events in 3 distinct weeks within 6, regret 50 and no questions; soften after 1 event, regret 94 (every
one-off user loses their wall); never soften, regret 114. A wall never softens silently.

![Active queries](report/figures/active_queries.png)

**Active queries (E016).** For consistent users, query-by-committee (6 bootstrap fits) or uncertainty sampling reach 90%
held-out ranking accuracy in 10-12 questions vs 25 for random pairs. For noisy users every strategy first *loses* accuracy
against the hand-set prior (0.82 -> 0.74-0.80 over 20-60 answers); QBC loses least and recovers to the prior by 60. Policy:
QBC, at most ~10 questions in the first weeks, stop when the committee's disagreement on its own top pair drops below 20% or
when the user's answers contradict each other (estimated answer noise high).
