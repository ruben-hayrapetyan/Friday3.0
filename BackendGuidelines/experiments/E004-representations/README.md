# E004 — Representations on equal budgets (RQ1, RQ2, RQ3)

**Question.** Which way of holding the plan and the hard rules works best: (a) the staged CP-SAT grid model (baseline),
(b) the slot-assignment (Potts) model with chunk moves where hard rules are **penalties**, (c) the same model and moves with hard
rules as **walls** (infeasible moves rejected, deadline-protected items never get late), (d) walls + a CP-SAT deadline skeleton as
the start plan, (e) walls + CP-SAT large-neighbourhood polish. The strict QUBO (E003) is not run here because it cannot hold the
full rule set.

**Setup.** Tuning seeds 0-9 on reference n=20/40/60 and the Cornell semester (40 instances). All problems are `prepare`d once, so
every engine sees the same locks. Budgets: sampler engines 10 s of wall clock (numba JIT excluded, reported separately),
single thread; baseline CP-SAT 30 s with 8 workers (its own design budget) and 10 s with 8 workers. Every plan is scored by the
shared evaluator and checker; invalid plans count as failures regardless of energy. Tiered annealing for stages (E005 studies
the alternatives).

**Hypotheses.**
1. Walls beat penalties on feasibility (100% valid and 100% deadline-safe vs less) and on quality at equal time.
2. Walls + EDF-style construction reach zero late work on every instance where CP-SAT proves zero, in milliseconds.
3. The CP-SAT skeleton adds little over `construct` (the construction already gives zero late work), so the pure wall sampler
   and the skeleton hybrid are within noise.
4. At 10 s the wall sampler is within a few percent of CP-SAT-30 s on wellbeing, and ahead on preferences at n >= 40.
5. LNS polish helps modestly at n=60 where annealing is time-limited.

**Metrics.** valid rate, deadline-safe rate (valid and zero late whenever the best known has zero late), lexicographic value,
gap to the best known per stage, time. Best known is the best value any engine has produced on that instance in any experiment
(`experiments/refs/best_known.json`).
