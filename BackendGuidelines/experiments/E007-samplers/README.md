# E007 — Samplers and speed (RQ4, plus "fixed temperature" from section 8)

**Question.** With the representation fixed (slot model + chunk moves + walls, E004), which sampler finds the best plans
in a given wall-clock time: simulated annealing (geometric or linear schedule, Metropolis or heat-bath acceptance), a fixed
moderate temperature with no annealing, zero-temperature descent, parallel tempering (one thread or eight), population
annealing, multi-start, or annealing finished by tabu search? How does each compare with CP-SAT at equal time?

**Setup.** Reference n=40, n=60 and Cornell, tuning seeds 0-9 (30 instances). Budgets 2 s and 8 s of wall clock per plan,
tiered stages (35% wellbeing, 65% preferences). Single-thread methods get `rate x budget` steps; 8-thread methods get 8x the
steps in the same wall clock (they use 8 cores: a latency comparison, and the CPU cost is stated). Same moves, same
calibration (T0 = 0.1, T1 = 0.003 x median |delta| per tier). JIT: cold-cache numba compile time measured once in a
fresh process.

**Hypotheses.** (1) Geometric SA beats a fixed temperature and zero-temperature descent (glassy landscape: descent sticks).
(2) Heat-bath and Metropolis are within noise. (3) PT-8 threads beats single-chain SA at equal wall clock, but PT-1 thread does
not (the replicas share one core). (4) Multi-start-8 is nearly as good as PT-8 (independent restarts already help a lot).
(5) Tabu adds little over SA. (6) At 2 s every sampler beats CP-SAT-10 s on the lexicographic value.

**Metrics.** lexicographic value and per-stage gap to the best known; success = valid and zero late; time; JIT time.
