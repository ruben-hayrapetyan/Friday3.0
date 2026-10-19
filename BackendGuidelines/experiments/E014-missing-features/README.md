# E014 — Missing-feature detection and automatic rule proposal (RQ8)

**Question.** When a user's true preferences include something the rule library cannot express, can the supervisor notice
and propose the right new rule from a grammar of templates? How often does it propose rules that are not there (false rules)?
Is auto-adding better than only flagging the gap?

**Setup.** Users with a missing preference (no work on Friday/Saturday evenings, weight 3) and users without one (easy type).
12 weeks each on fresh Cornell-style instances; Friday plans with the ranking QP's weights; the user ranks 10 pairs per week
(plus drags). From week 4, every 2 weeks, the supervisor fits a Bradley-Terry model to all rankings and computes, for each of
132 candidate rules (11 day sets x 6 windows x 2 scopes of `time_preference`), the 5-fold cross-validated gain in log-likelihood
per ranking when that rule's feature is added. Threshold tuning: users 0-5 of each type (tuning users) give the max-gain
distributions; the threshold is the smallest one with no more than 1 of 6 easy users ever flagged. Evaluation: users 6-11 of each
type with that threshold. A proposal is correct if it is fri_sat x (evening | late | night) with scope any.

Policies at week 12: auto-add (plan with the library weights refitted and the new rule with its fitted weight) vs flag only (no
new rule) vs oracle (the true rule and weight); regret as in E011.

**Hypotheses.** (1) Most missing-feature users get a correct proposal by week 12, half by week 8. (2) The false-rule rate on
evaluation users stays near the tuned level (about 1 in 6). (3) Auto-adding cuts regret for missing-feature users and costs
little for the others because a false rule gets a small fitted weight.
