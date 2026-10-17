# E004b — Penalties on the full model: how large must they be, and what do they cost? (RQ2, second round of P3)

**Question.** E004's penalty variant used huge penalties (1e6 per violation) and a deadline-feasible start, so it behaved like
a wall. Here the penalty design is tested honestly: (A) penalty per hard violation lambda in {0.1, 1, 10, 100} x the median
|move delta|, deadlines still lexicographic; (B) deadlines as an ordinary weighted term, w_D in {1, 10, 100} x the wellbeing
weight, hard rules at 1e6. Both from the constructed start and from an empty plan (locks only), to see whether penalties can
*find* feasibility, not just keep it.

**Setup.** Reference n=40 and Cornell, tuning seeds 0-9; 5 s tiered single-thread SA; the wall sampler as reference.
Only violation-free states can be returned (the chain's best feasible state); a run that never sees one returns its start.

**Hypotheses.** (A) With small lambda, chains spend their time in infeasible states and return worse plans; from an empty start
they often never return anything better than empty. (B) Deadlines as weights miss avoidable deadlines whenever w_D is not huge,
which is the QUBO finding again on the full model.
