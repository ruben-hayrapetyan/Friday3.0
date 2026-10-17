# E005 — Deadline guarantee: walls vs penalties vs repair (RQ2)

**Question.** (1) On every instance where the CP-SAT baseline proves that zero late work is possible, does a wall design
(EDF-style construction, then moves that never leave the feasible set) deliver zero late work? (2) Where construction alone
fails (min chunks, one-sitting items, dependencies, daily caps: the gap EDF leaves), how often does a sampler repair or CP-SAT
close it? (3) When some lateness is unavoidable (overload), how close to the proven optimum are the heuristic and the CP-SAT
fallback, and how fast?

**Ground truth.** CP-SAT with the deadline stage alone (8 workers, 15 s): OPTIMAL value 0 = a zero-late plan exists; OPTIMAL > 0 =
overload; FEASIBLE/other = unknown (reported separately, never counted for or against a design).

**Methods.**
- `edf`: the reference executor's exact-in-one-direction test (feasible/infeasible), no plan.
- `construct`: earliest-deadline-order placement honouring locks, windows, cap, chunks, one-sitting, dependencies.
- `repair`: construct, then the sampler on the deadline stage with hard rules as penalties (400k steps), best violation-free state.
- `repair+cpsat`: as above, then CP-SAT stage 1 (5 s) if lateness remains.
- `walls`: the full wall sampler (tiered, 3 s) from the repaired start: lateness must not rise above the start.
- `penalty`: the same sampler with penalties and no protection, from the same start: lateness may rise.

**Instances.** Tuning seeds 0-11 of tight_deadlines, overload, fragmented, many_deps, many_one_sitting, many_pins; reference
n=20/40/60 and Cornell, seeds 0-5; stress 100 and 150 items, seeds 0-1.

**Hypotheses.** (1) construct reaches zero late on >= 95% of the instances with proven zero; the remainder are closed by repair.
(2) EDF says "feasible" on some instances that CP-SAT shows are infeasible (cap/chunk/dependencies) and on a few where construct
also fails. (3) Walls keep lateness at or below the start on 100% of instances; penalties let it rise on some. (4) On overload the
sampler repair is within ~10% of the CP-SAT optimum in under a second, and CP-SAT is better only on the hardest instances.
