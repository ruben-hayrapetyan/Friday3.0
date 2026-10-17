# E012 — An RBM trained on lived schedules, with no hand-written rules (section 8)

**Question.** Can a restricted Boltzmann machine trained only on the weeks a user actually lived learn a scheduler, or at
least a usable preference energy, without the rule library?

**Setup.** Three easy simulated users. For each, 60 lived weeks (fresh Cornell-style instance per week; Friday plans with the
reference weights; the user drifts from it under their true energy). A week is encoded as 336 binary visible units: for each
day (7) and hour (24), "deep work happens" and "other work happens". RBM: 32 hidden units, CD-1, 300 epochs, learning rate 0.05,
weight decay 1e-4, trained on 50 weeks, 10 held out. Free energy F(v) is the learned energy (lower = more like the user).

Tests: (1) held-out log-likelihood proxy: mean free energy of held-out lived weeks vs Friday's own plans for the same weeks
(does it tell the user's week from Friday's?); (2) pairwise ranking accuracy on 200 held-out pairs of plans (the E011 protocol),
F_RBM vs the reference rules (theta = 1) vs the true energy; (3) re-ranking regret: from 16 diverse T > 0 samples of Friday's plan
for a held-out week, pick the lowest F_RBM; true-energy regret against picking by true energy; (4) can its samples be
schedules? Gibbs samples of v, checked for whether they contain the week's required work hours and respect sleep.

**Hypotheses.** (1) Yes, it separates lived weeks from Friday's plans (it learns "when this user works"). (2) Ranking accuracy
is above chance but below the rule-based energy, because a 336-bit occupancy picture cannot see items, deadlines, chunking or
amounts. (3) Re-ranking helps a little over theta = 1 for easy users. (4) Its samples are not schedules: they ignore amounts,
deadlines and fixed events, so an RBM can at most be one feature inside the rule energy (an "occupancy prior"), never the scheduler.
