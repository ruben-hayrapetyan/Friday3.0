## 5. Samplers and speed (RQ4, RQ9, RQ10)

**The kernel.** A numba energy kernel with incremental deltas runs ~550k move proposals per second on one core (M3 Max,
under load), with every hard rule checked per touched item in ~0.6 µs. Two implementation facts mattered more than any
algorithm: numba helper calls with a 50-array model tuple cost ~100 ns each in reference counting until compiled without the
runtime (`_nrt=False`; 10-15x faster moves), and moves must keep *units*, not slot counts, across the 15/30-minute boundary
(the first version silently trapped all work in week one). Cold JIT compilation is 66 s; the on-disk cache brings it to ~1 s.

**Samplers (E007, 30 instances, 2 s and 8 s, mean lexicographic rank among 10, lower is better):**

| sampler | 2 s | 8 s |
| --- | --- | --- |
| 8 independent chains on 8 cores (multi-start) | **2.3** | 2.8 |
| parallel tempering, 8 replicas on 8 cores | 2.9 | **2.7** |
| population annealing, 32 members on 8 cores | 3.5 | 2.8 |
| geometric SA + tabu finish, 1 core | 6.8 | 5.1 |
| geometric SA, 1 core | 6.1 | 6.1 |
| zero-temperature descent | 5.0 | 6.5 |
| fixed moderate temperature, no annealing | 5.8 | 7.0 |
| heat-bath acceptance | 6.7 | 6.8 |
| parallel tempering on 1 core | 10.0 | 8.7 |

Multi-core methods beat a single chain on 25-29 of 30 instances; replica exchange adds nothing over independent restarts
at these budgets; parallel tempering on one core is the worst (its replicas share the core). Heat-bath and Metropolis are
equivalent. A fixed temperature is no better than descent and worse than annealing given time (prompt section 8).

**Moves (E008).** Split (cut a legal-size piece and move it) is essential: without it wellbeing is 3x worse on every instance,
because walls forbid breaking long runs one slot at a time. Insert, drop and shrink are essential for elastic, target and open
items (they start empty). Far shift and swap matter; transfer, merge, ejection, grow and small shifts are near neutral.

**Stage handling (E006, E006b).** One weighted energy with a 1000:1 ratio between stages matched strictly tiered annealing on
wellbeing for 80% of instances and gave 3x better preferences; lower ratios trade wellbeing away (ratio 1: 4x worse
wellbeing). The recommended scheme searches the 1000:1 energy and then polishes preferences with wellbeing capped (E006b).

**Against CP-SAT on equal time.** At 2 s every sampler above already matches or beats the staged CP-SAT given 30 s on every
comparable stage (E004), and is valid and deadline-safe on every instance where CP-SAT often is not.

**Warm replans (E009).** From the previous plan at a low start temperature: 0.38 s median (p90 0.43 s) for a usable replan, 2.3 s
for one that ties CP-SAT-30 s on wellbeing; CP-SAT warm needs 24 s (and at a 10 s budget reaches zero late on only 33%). CP-SAT
at 30 s does produce better preferences and less churn (37.6 vs 44 h of work moved, median); with the tiered stage scheme the
sampler's first phase ignores `minimize_changes`. E009b re-measures churn with the weighted-then-polish scheme.

**Determinism (RQ9).** With a fixed step budget reruns produce the identical plan (all 90 warm reruns, 89 of 90 cold ones), independent of
thread count (each chain seeds its own generator); the one cold rerun that differed had its step count sized from the
clock. CP-SAT with 8 workers gave the same plan on 53% of reruns. **Exact explanations**: per-rule energies equal the
evaluator's to the integer, and "why not elsewhere" equals the evaluator's difference on every tested move (`tests/`).

**Diversity and calibration (RQ10, E010).** T > 0 samples are different plans (66-71% of work slots differ between samples;
~5 day patterns per item in 16 samples). Item-on-day probabilities from 16 samples were calibrated against simulated users'
lived weeks (ECE 0.003 for consistent users, 0.009 for noisy ones) when the temperature matched the user's own noise, and
over-confident when colder. But under walls the chain does not sample the Boltzmann distribution over *all* valid plans: on
tiny instances where every valid plan was enumerated, it reached only ~20% of them, and longer walks reach no more (the
missing plans need coordinated changes to several items in a full grid). Probabilities are therefore over plans reachable
from the current plan, which is what a user deciding "where will PS5 go" needs, but not a full posterior.
