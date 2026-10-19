# E011b notes — learning, round 2 (Bradley-Terry likelihood)

Run: the E011 protocol and user seeds, learners none / rank_qp / combined / bt / bt_cd, 2 shards, 2026-10-17 14:33-14:43.
Because the users' random streams are consumed per learner, a different learner set gives the users different weeks: the
rows for none / rank_qp / combined are an **independent replicate** of E011 for the same users, not a copy.

## Held-out accuracy, last 4 weeks (mean)

| user type | none | rank_qp | combined | bt | bt_cd |
| --- | --- | --- | --- | --- | --- |
| easy | 0.748 | 0.844 | 0.875 | 0.896 | **0.949** |
| moody | 0.848 | 0.899 | 0.913 | **0.916** | 0.890 |
| noisy | 0.830 | 0.828 | **0.862** | 0.777 | 0.729 |
| missing feature | 0.763 | 0.860 | 0.860 | 0.873 | **0.879** |
| adversarial | 0.747 | 0.723 | 0.662 | **0.805** | 0.692 |
| mean over types | 0.787 | 0.831 | 0.834 | **0.853** | 0.828 |

E011 (first replicate) means: none 0.772, rank_qp 0.793, combined 0.827.

## Findings

1. **Replicates disagree on the QP more than on anything else.** The ranking QP's easy-user accuracy was 0.92 in E011 and 0.84
   here; noisy 0.75 vs 0.83. With 3 users and 12 weeks per type, single-type differences under ~0.05 are not established.
2. **Bradley-Terry is the best on average (0.853) and the most robust to deliberate inconsistency** (adversarial 0.805 vs 0.66-0.75
   for the others; per user 0.76/0.85/0.80, best or equal for all three). It is not robust to plain noise: on noisy users it
   is below no learning (0.777 vs 0.830), because its temperature (SCALE 0.05) is fixed and assumes answers are almost
   deterministic. "combined" is the best on noisy users in both replicates (0.85, 0.86).
3. **Adding CD to BT (bt_cd) helps easy users (0.949, best) and hurts noisy and adversarial users**: the lived-week term pulls
   towards wherever the user drifted, which for a noisy user is mostly noise.
4. Regret medians are within each other's confidence intervals for most cells (single-plan regret is noisy); accuracy and
   cosine are the reliable learning metrics here.

## Recommendation (P5 exit)

Bradley-Terry likelihood over rankings and drags (drags x3), prior at the hand-set weights, as the default; the next
improvement, left open, is to fit the answer temperature per user (the noise level), which E011/E011b point to as the one
thing separating noisy from consistent users and which also sets how many questions are worth asking (E016). Likelihood
from lived weeks only as a small regulariser for users whose rankings are consistent.
