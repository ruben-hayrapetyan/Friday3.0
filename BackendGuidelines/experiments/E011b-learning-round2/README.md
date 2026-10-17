# E011b — Learning, improvement round 2 (RQ5)

**Why.** E011: the ranking QP learns fastest on easy users but bends to noise, mood flips, missing features and deliberate
inconsistency (it keeps every ranking as a hard constraint with slack); drags were the most reliable evidence; CD alone
hardly moves. Round 2 replaces constraints by a likelihood: `bt` = Bradley-Terry MAP over all rankings (each a noisy vote,
drags counted 3x, Gaussian prior at the hand-set weights, direction-only); `bt_cd` = the same with the CD step from lived
weeks moving the prior's centre.

**Setup.** Identical to E011 (same user seeds, instances, protocol), learners none / rank_qp / combined / bt / bt_cd, so
none, rank_qp and combined reproduce E011 and check its stability.

**Hypotheses.** bt matches the QP on easy users and beats it on noisy, missing and adversarial users; bt_cd adds a little
on moody users.
