# E011c notes — learning, round 3: fitted answer temperature

Run: E011 protocol, learners none / combined / bt / bt_auto, 2 shards, 2026-10-17 14:44-14:52. A third replicate for
none, combined and bt (different week streams again, same users).

| user type | none | combined | bt (fixed temperature) | bt_auto (fitted temperature) | fitted temperature, mean (range) |
| --- | --- | --- | --- | --- | --- |
| easy | 0.748 | 0.911 | **0.919** | 0.903 | 0.08 (0.05-0.2) |
| moody | 0.848 | 0.872 | **0.929** | 0.819 | 0.19 (0.02-0.5) |
| noisy | 0.830 | 0.870 | **0.885** | 0.850 | 0.18 (0.1-0.5) |
| missing feature | 0.763 | 0.860 | 0.834 | **0.868** | 0.35 (0.05-0.5) |
| adversarial | 0.747 | 0.706 | 0.800 | **0.852** | 0.50 (always the top of the grid) |
| mean | 0.787 | 0.844 | **0.873** | 0.858 | |

## Findings

1. **Hypothesis partly confirmed.** The fitted temperature is an excellent *noise detector*: it sits at 0.05-0.08 for easy users
   and at 0.18-0.50 for noisy, moody, missing-feature and adversarial users (it saturates at the top of the grid for every
   adversarial user). It makes BT robust to deliberate inconsistency (adversarial 0.852, best of all learners in all three
   replicates' terms) but costs accuracy on moody users (0.819: mood flips look like noise and get discounted).
2. **Replicate variance is the main caveat of P5.** bt's noisy-user accuracy was 0.777 in E011b and 0.885 here, with the same
   users. Over the two replicates bt averages 0.863 across types, combined 0.839, the QP 0.81 (three replicates: 0.79/0.83),
   none 0.78. Differences of a few points between the top learners are not established with 3 users per type.
3. **Decision.** Bradley-Terry likelihood (drags x3, prior at the hand-set weights) is the weight learner. The fitted
   temperature is used as the user's noise estimate, which drives two policies: the query budget (stop asking when it is high:
   E016) and the per-user state test (high noise without predictive gain = noise, not mood: E013). It is not used to rescale
   the weight fit itself, since that hurt moody users.
