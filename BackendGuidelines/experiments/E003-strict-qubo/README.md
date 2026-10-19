# E003 — Strict QUBO / Boltzmann machine, and a Hopfield descent: expected to struggle

**Question (RQ1, RESEARCH_PROMPT section 8).** If the scheduling problem is written as a pure pairwise energy over binary units
x[item, slot] with every hard rule a penalty (one thing per slot: weight A; amount: weight B with slack bits; deadlines through
the overflow price), how well does single-flip annealing do, how does feasibility depend on the penalty scale, and where does
the landscape freeze? What cannot be written at all?

**Setup.** Price-only slice (`price_only` generator): 6-10 fixed-amount items, 2 days (~110 allowed slots per item), rules
`late_work late_night energy soft_late unscheduled`. These are the rules a pairwise energy can express exactly; hinge measures
(daily load, reserves, deep runs), chunk rules, one-sitting, dependencies and chunk starts need helper bits or higher-order terms
and are left out on purpose. The exact optimum comes from the staged CP-SAT baseline on the same problem.

Penalty scale alpha: A = alpha x P0 and B = alpha x P0 / 2 where P0 is the largest single-unit price in the instance (the
overflow price of the most important hard item), i.e. alpha = 1 is the textbook minimum that makes violations unprofitable.
alpha in {0.1, 0.3, 1, 3, 10, 100, 1000}. For every alpha, the temperature range is tuned over T0/P0 in {0.01, 0.05, 0.2, 1}
(best of the grid per instance: an oracle-tuned QUBO, the fairest case for it), 3 million flips, 10 seeds, 2 sizes.
Also a greedy single-flip descent (a Hopfield-style network at T=0) from empty and random starts.

**Hypotheses.**
1. Feasible (no hard violation, no hard deadline missed) low-energy states appear only for alpha >= ~1; below it the optimiser
   cheats on the penalties.
2. Large alpha (>= 100) freezes the search: the barrier A between feasible states is far above the price differences the
   objective cares about, so the objective quality (gap to optimum) gets worse as alpha grows although feasibility is perfect.
   There is no alpha that gives both a guaranteed deadline and good preferences.
3. The Hopfield descent ends in infeasible or poor states (spurious attractors).
4. Coefficient dynamic range (largest / smallest nonzero |coefficient|) exceeds what hardware annealers represent (~10-100x),
   so the formulation cannot run on annealing hardware as is.

**Budget.** About 8 minutes of CPU.
