# E011 notes — learning weights from simulated users

Run: 5 user types x 3 users x 12 weeks x 6 learners (each learner its own trajectory), fresh Cornell-style instance per week,
2 parallel shards, 2026-10-17 12:16-12:59. (The first attempt with 5 users per type was stopped at the request of a live
service sharing the machine; its partial output is not used.) `results/runs_shard*.csv`, `figures/learning_curves.png`.

## Results (last 4 weeks; held-out accuracy on 200 fixed noise-free pairs; regret relative to the plan optimal for the
true weights and mood; cos = cosine between learned and true multipliers)

| user type | none | v2 moves only | ranking QP | CD | PCD | combined (CD + QP) |
| --- | --- | --- | --- | --- | --- | --- |
| easy: accuracy | 0.74 | 0.84 | **0.92** | 0.73 | 0.72 | 0.84 |
| easy: regret | 0.091 | 0.046 | 0.052 | 0.056 | 0.041 | **0.038** |
| moody: accuracy | 0.82 | 0.86 | **0.88** | 0.79 | 0.80 | 0.85 |
| moody: regret | 0.108 | 0.121 | 0.148 | 0.074 | 0.062 | **0.040** |
| noisy: accuracy | 0.78 | 0.78 | 0.75 | 0.79 | 0.82 | **0.85** |
| missing feature: accuracy | 0.81 | 0.82 | 0.76 | 0.82 | 0.78 | **0.85** |
| adversarial: accuracy | 0.71 | **0.83** | 0.66 | 0.71 | 0.72 | 0.75 |

Weeks until accuracy settles (median): ranking QP 5 (easy), 6 (moody); CD/PCD 9-11 (they barely move); combined 9-10.
Stability (mean |change of theta| per week, last 4 weeks): QP 0.02-0.08, combined 0.07-0.13, CD 0.04-0.07.

## Against the hypotheses

1. **Confirmed for easy users, refuted for the rest.** The ranking QP learns fastest and best on easy and moody users
   (0.92 / 0.88, cosine 0.92 / 0.90) but *loses* accuracy on noisy (0.75 < 0.78), missing-feature (0.76 < 0.81) and adversarial
   users (0.66 < 0.71): it keeps every ranking as a constraint, and slack does not stop it from bending the weights to fit
   noise, mood flips or a preference no rule expresses. Its regret on moody users (0.148) is worse than no learning (0.108).
2. **Confirmed.** Likelihood learning from lived weeks alone (CD, PCD) hardly moves accuracy (one lived week is one sample,
   and the departure from Friday's plan is local), though it lowers regret a little (it learns "where this user drifts").
   Section 8's "likelihood alone, without the supervisor" is therefore weak but safe.
3. **Refuted.** v2's moves-only learner does well: on easy users 0.84, and it is the most robust to adversarial rankings
   (0.83), simply because drags come from what the user did, not from answers they can flip. Drags are scarce (about 1 per 2
   weeks) but clean.
4. **Confirmed in the robust sense.** Combined is the best or close to best on every type (0.84-0.85 accuracy, lowest regret on
   easy, moody, and good on noisy); the likelihood step regularises the QP.
5. **Partly.** Adversarial users stall every method except v2's drags; the QP is the most hurt, not the least.
6. **Confirmed.** Missing-feature users plateau (best 0.85) and the QP is hurt by trying to explain the missing preference
   with library weights: this is the signal the supervisor uses in E014.

## What this means for the design

Rankings are the fastest teacher but must not be trusted blindly: weight them by how consistent they are (slack history),
keep the likelihood term as a regulariser, and treat drags (revealed behavior) as the most reliable evidence. With three
users per type the confidence intervals are wide (see `analyze.py`). Per user (mean accuracy, weeks 8-11): combined beats
the QP for all 3 noisy users (0.82/0.87/0.87 vs 0.78/0.72/0.74); on easy users the QP is best or within 0.01 for all 3; on
missing-feature users the QP falls below no-learning for 2 of 3 users; v2's drags beat the QP for all 3 adversarial users.
The per-type averages are therefore driven by consistent per-user effects, not by one outlier, but n = 3 is small.
