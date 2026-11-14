## 6. Learning (RQ5)

**Setup (E011, E011b, E011c).** Simulated users (section 5 of the prompt; `fr/sim/user.py`) have true weight multipliers
(log-normal, sigma 0.6, around the hand-set weights), a mood chain that rescales some weights, per-area duration multipliers,
skips, noisy reviews and check-ins; five types: easy (consistent), noisy (Bradley-Terry temperature 2x the typical energy
gap), moody, missing-feature (a true preference no rule expresses) and adversarial (30% of rankings flipped on purpose). Each
week is a fresh two-week Cornell-style instance; Friday plans with its current weights; the user lives the plan (a short
Metropolis chain under their true energy, started at Friday's plan), may drag (half the weeks), and ranks 6 pairs drawn from
Friday's own T > 0 samples. Features are each rule's cost at its reference weight, so theta = 1 means "the hand-set weights".
Each learner has its own trajectory; 3 users per type, 12 weeks; three replicates (independent for every learner except
"none", whose week stream is the same in replicates 2 and 3).

**Held-out ranking accuracy (200 fixed noise-free pairs on an unseen instance), last 4 weeks, mean over types:**

| learner | replicate 1 (E011) | replicate 2 (E011b) | replicate 3 (E011c) |
| --- | --- | --- | --- |
| none (hand-set weights) | 0.772 | 0.787 | 0.787 |
| v2: max-margin from drags only | 0.823 | - | - |
| ranking QP (every ranking a constraint, slack, prior, step cap) | 0.793 | 0.831 | - |
| contrastive divergence (lived weeks only) | 0.767 | - | - |
| persistent CD | 0.765 | - | - |
| combined (CD step + QP) | 0.827 | 0.834 | 0.844 |
| Bradley-Terry likelihood (drags x3, prior) | - | **0.853** | **0.873** |
| BT + CD | - | 0.828 | - |
| BT with fitted answer temperature | - | - | 0.858 |

![Learning curves](report/figures/learning_curves_E011b.png)

**Findings.**
- **Rankings teach fastest; how they are used decides robustness.** The QP (constraints with slack) learned fastest on easy
  users (0.92 in replicate 1, settled in 5 weeks) but fell *below* no learning on noisy, missing-feature and adversarial users in
  replicate 1, and its numbers moved by up to 0.08 between replicates. A likelihood over the same rankings (Bradley-Terry)
  is the best on average in both replicates where it ran and the most robust to deliberate inconsistency.
- **Lived weeks alone teach little** (CD, PCD ~ no learning on accuracy). One lived week is one sample, the user's departure
  from the plan is local, and the scale of the weights is not identifiable from a likelihood (it is the temperature), so CD
  keeps sum(theta) fixed. "Learning from likelihood alone, without the supervisor" is safe but slow.
- **Drags are the cleanest evidence.** v2's moves-only learner was the most robust to adversarial users (0.83) because drags
  come from behavior, not from answers that can be flipped; weighting drags 3x inside the likelihood keeps that benefit.
- **The answer temperature is the noise detector** (E011c): fitted per user, it sits at 0.05-0.08 for consistent users and at
  0.18-0.5 for noisy, moody, missing-feature and adversarial users. Using it to rescale the fit helped adversarial users and
  hurt moody ones, so it is used to set policies (how many questions to ask, whether contradictions are noise), not the fit.
- **Weight recovery** (cosine with the true multipliers) reaches 0.92-0.95 for easy and moody users and 0.58-0.90 for the rest;
  stability (mean |change| per week in the last 4 weeks) 0.06-0.2 for BT, 0.01-0.08 for the QP (it moves less, and
  learns less when it should not move).
- Regret differences between learners are mostly inside their confidence intervals: one plan per week per learner makes
  regret a noisy metric; accuracy and cosine carry the conclusions.

**Recommendation.** Bradley-Terry likelihood over all rankings and drags (drags x3), Gaussian prior at the hand-set weights,
refitted after each week; lived weeks only as a small CD regulariser for users whose fitted answer temperature is low.
Learning RBMs from lived weeks without rules is a dead end (E012, section 10).
