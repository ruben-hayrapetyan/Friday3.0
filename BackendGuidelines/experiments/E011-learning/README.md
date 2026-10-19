# E011 — Learning rule weights from simulated users (RQ5)

**Question.** Which way of learning the weights works best from what Friday can observe: likelihood learning from lived weeks
(contrastive divergence, CD-k, or persistent CD), the supervisor's ranking QP (every ranking and drag kept, slack, prior, step
cap), both combined, v2's outline (max-margin from manual moves only), or nothing? Measured on sample efficiency, robustness to
noise and inconsistency, and stability. Also tests "likelihood alone, without the supervisor" (section 8).

**Setup.** Five user types (easy, noisy, moody, missing-feature, adversarial; `fr/sim/user.py`), 5 users each (true weight
multipliers log-normal, sigma 0.6), 12 weeks each, a fresh Cornell-style two-week instance per week (tuning seeds). Every
learner has its own trajectory: Friday plans with the learner's weights (single weighted energy, deadlines walled, 300k
steps), the user lives that plan (a short chain under their true energy from Friday's plan), may drag (50%/week), answers 6
ranking pairs drawn from Friday's own T > 0 samples, and the learner updates. Missing-feature users have a true preference
no rule expresses; no learner here can add rules (that is E015/P7).

**Metrics.** regret = E_true(Friday's plan) - E_true(plan optimised for the true weights, this week's mood), in points and
relative; held-out ranking accuracy on 200 fixed pairs (normal mood, no noise); weight recovery (cosine, relative error of
normalised vectors); stability (mean |change| per week in the last 4 weeks); weeks until held-out accuracy stays within 2
points of its final value.

**Hypotheses.** (1) Ranking QP learns fastest on easy users (each pair is a direct constraint) and is robust to noise thanks
to slack. (2) CD from lived weeks alone is slow and noisy (one lived week is one sample; departures are local), and the scale
of theta is not identifiable from likelihood (handled by fixing the norm). (3) v2's moves-only learner learns little (one drag
per two weeks). (4) Combined is at least as good as the QP. (5) Adversarial users stall every method; the QP stays closest to
the prior thanks to its slack and step cap. (6) Missing-feature users plateau below the others.
