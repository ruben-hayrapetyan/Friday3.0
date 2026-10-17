## 10. Dead ends (what failed and why)

| tried | result | why it fails | evidence |
| --- | --- | --- | --- |
| Strict QUBO / Boltzmann machine with penalty weights for every hard rule | Never meets hard deadlines (0-5%) at any penalty scale; 25-200x the optimum | Small penalties are cheated (over-placing); large ones freeze the search: slack bits absorb unplaced work and leaving needs two coordinated flips across a barrier of about the penalty. Most rules cannot even be written pairwise | E003 |
| Hopfield-style network (greedy single-flip descent) on the same energy | No better than annealing at T = 0: 0% feasible at alpha 1, misses 4 hard items at alpha 10 | Spurious attractors of the penalty landscape | E003 |
| Huge penalty weights on the full model (Potts state, chunk moves) | 95% deadline-safe instead of 100% | From a late start the chain explores infeasible states and its best feasible state stays late | E004, E004b |
| Pure weighted stages, ratio 1-10 | Wellbeing worse on 85-100% of instances (4x at ratio 1) | The ratio decides the trade; a small one is not "wellbeing first" | E006 |
| Strictly tiered annealing (wellbeing with preferences switched off, then preferences under a cap) | Preferences 3x worse than a weighted search at ratio 1000, wellbeing no better on 80% | Optimising one stage alone leaves the next in a state the cap forbids repairing | E006 |
| A fixed moderate temperature with no annealing | see E007 | | E007 |
| CP-SAT deadline skeleton for every instance | Hurt quality and missed deadlines twice | A 3 s CP-SAT stage-1 solution is often later than the 1 ms construction | E004 |
| CP-SAT large-neighbourhood polish at a 10 s budget | Worse wellbeing than pure annealing | Each neighbourhood solve pays model build + presolve (1-2 s): too few exact moves per second | E004 |
| An RBM trained on lived weeks, no rules | Ranks plans at 0.62-0.64 vs 0.80-0.87 for the rules; samples are not schedules | An occupancy picture cannot see items, amounts or deadlines; lived weeks are Friday's plan plus a small drift | E012 |
| Learning weights from likelihood alone (CD, PCD) | Barely moves held-out accuracy in 12 weeks | One lived week is one sample, and the departure from the plan is local; the scale of the weights is not identifiable | E011 |
| Ranking QP with hard constraints for every ranking | Best on consistent users, worse than no learning on noisy, missing-feature and adversarial users | Slack does not stop it bending the weights to fit noise, moods and preferences no rule expresses | E011 |
| Hidden units learned without dial seeding | No nameable state, smaller regret gain than seeded units | Nothing anchors the units; free loadings fit noise | E013 |
| Hidden units always on | Regret up from 0.049 to 0.085 for users with no moods | Units chase misleading check-ins (false attribution 23-42% of weeks) | E013 |
| Asking random comparisons of noisy users | Accuracy falls below the hand-set prior and stays there for 60 answers | Noisy answers move the weights more than they inform them | E016 |
| Softening a "never" wall after one contradicting event | Every one-off user loses their wall | One event cannot tell a change of mind from an exception | E015 |
| A time budget (steps sized from measured speed) as the production limit | Plans depend on machine load, breaking determinism | Determinism needs a step budget per instance size | E009 |
