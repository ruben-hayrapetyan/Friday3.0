## 12. Recommended v3 engine specification

Everything below is implemented in `src/fr/` and was measured in the experiments cited; numbers are defaults to start from.

### 12.1 Problem and state

- **Problem**: unchanged from `ENGINE_REFERENCE.md` (items, facets, fixed occurrences, nights, grid of 15/30-minute slots,
  the 18 reference soft rules plus user rules, dials). The grid, builder, pruning and lock repair are reused as they are.
- **State**: one owner per slot, `owner[s] in {-1} ∪ items` (int16). This is the Potts / slot-assignment representation;
  "one thing per slot" holds by construction. Chunks are maximal runs of one item's slots.
- **Compiled model** (`engines/compile.py`): the problem flattened into arrays: per-stage price tables `price[stage, item, slot]`
  and overflow costs; every measure (hinge rule) as a sparse linear expression over x(item, slot) x units, chunk starts,
  overflow and any(group) indicators, each with its convex hinge curve (integer coefficients exactly as the reference
  rounds them); per-rule price tables for explanations; the hard-rule data (allowed slots, locks, windows, chunk limits,
  one-sitting flags, dependency lag tables, daily caps).

### 12.2 Energy

E(x) = sum over stages k of w_k x V_k(x), where V_k is the exact integer stage value of the shared evaluator (prices of occupied
slots + overflow costs + hinge costs of measures). Maintained **incrementally**: a slot changing owner updates the prices,
the measures it appears in (with hinge cost deltas), chunk-start indicators of the two neighboring slots, any-group counts and
overflow. Exactness is a tested invariant: after any sequence of moves the kernel's stage values equal `evaluate()` and its
hard-violation counts equal `check()` (`tests/test_kernel.py`). Per-rule totals can be recomputed from scratch in ~50 µs
(`rule_totals`) for explanations and learning features.

### 12.3 Walls (hard rules)

A move is rejected if it would produce any hard violation the checker knows: slot outside the item's allowed set, a lock
touched, amount above its cap, chunk shorter than the minimum or longer than the maximum, a second chunk of a one-sitting item
or a partial one, a dependency read before its source reached the required amount (lag-aware), a day above the hard cap.
Only the items a move touches (and their dependents) are re-checked (`item_viol`, ~0.6 µs per item). **Deadline wall**: an item
that is complete and on time in the start plan is *protected*: it may only use slots ending by its due time and may never lose
units. Items late at the start are not protected; their lateness is the deadline stage of the energy, weighted 10^6 times the
other stages, so moves can only shorten it.

### 12.4 Start plan, repair and overload

1. **Construct** (`engines/construct.py`, < 32 ms at 150 items): items in earliest-effective-deadline order (a source inherits the
   earliest deadline of its dependents; dependencies are placed first), each into the earliest free slots that honor windows,
   the daily cap, chunk minimums and maximums (keeping legal remainders), one-sitting runs and dependency readiness; hard items
   use on-time slots first. Elastic, target and open items start empty. With a previous plan (warm start) everything still
   allowed is kept and only missing amounts are placed. If construction leaves violations caused by locks, those locks are
   demoted to preferred pins (as v2's repair) and construction reruns.
2. **Repair** (`engines/repair.py`) if the start is late: the sampler on the deadline stage alone, hard rules as penalties
   (lambda 10^9), 400k proposals, best violation-free state.
3. **Exact fallback**, only while lateness remains, ordered by size (`engines/api.run_v3`, E018-E018d): up to 60 flexible items,
   CP-SAT's deadline stage first (hinted with the repaired plan, 5 s for the stage, longer in an overload week), then the wall
   sampler; above 60 items, the wall sampler first for the budget, then CP-SAT hinted with its plan. Every step keeps the less
   late plan.
Measured: zero late on 72/72 instances where it is possible (construction alone 69/72); on proven overload the fallback reached
the optimum on 5/5; on unproven overload the sampler path beat CP-SAT-15 s on 20/23 (E005); deadline-safe on 36/36 adversarial
instances (E018). Remaining lateness is reported per item.

### 12.5 Move set (11 moves, `engines/kernel.py`)

All moves keep units exact across the 15/30-minute boundary. Probabilities (relative): shift 1-4 slots 3 (reduce to ~1, E008),
swap two equal-unit chunks of different items 1, grow 1, shrink 0.5, transfer k units between chunks of an item 1, **split** a
legal-size piece off a chunk and move it 1 (essential), merge next to a sibling chunk 1, **far shift** anywhere in the window 1.5,
**insert** a new chunk (min-chunk units, or the whole amount for one-sitting items) 1, **drop** a chunk 0.3, **eject** (move a chunk
onto another item's chunk and re-place that one) 0.5. Removing split makes wellbeing 3x worse; removing insert/drop/shrink
breaks elastic, target and open items (E008).

### 12.6 Sampler

- **Metropolis, geometric schedule** T0 = 0.1 x median |delta|, T1 = 0.003 x median |delta|, where the median is taken over 1,500
  random valid moves from the start that leave the walled stage unchanged (E-calibration finding: including deadline-stage
  deltas sets T ~ 10^9).
- **Stage handling ("lexpolish", E006)**: 60% of the steps on E = 10^6 D + 1000 W + P, then 40% on 10^6 D + P with W capped at the
  value reached (moves raising wellbeing are rejected). This is lexicographic for wellbeing at the end and searches like a
  weighted sum; strictly tiered annealing left preferences 3x worse (E006). E006b: same median wellbeing as tiered, preferences
  2.3x better, better than tiered and than the pure weighted search on 95% of instances; wellbeing a few percent worse on 20%.
- **Parallelism**: independent chains from the same start on all idle performance cores, best result wins (multi-start was as
  good as parallel tempering in E007); a short tabu finish (20% of steps, 25 candidates, tenure 8) when the budget exceeds ~5 s.
- **Budgets and determinism**: a *step* budget per instance size, not a time budget (E009): ~0.5-1 M proposals per chain for a
  cold plan of 40-60 items (~1-2 s at 550k/s), 0.3 M for a warm replan at T0 = 0.01 x median. Same input, seed, profile and step
  budget give the identical plan, on any thread count (each chain seeds its own generator).
- JIT: ship the numba cache; cold compile is ~66 s (E007).

### 12.7 Warm replans

Start from the previous plan (construct with `base`), repair if late, protect what is on time, anneal with lexpolish from a
low temperature (T0 = 0.01 x median |delta|) with the reference's `minimize_changes` rule active. E009/E009b: 0.9 s (p90 0.94 s)
for a 1 s replan, 2.7 s for a 3 s one, against 24 s for CP-SAT warm; churn 38.6 h median at 3 s (CP-SAT-30: 37.6 h); zero late
on every instance where any engine reaches zero.

### 12.8 Explanations

Per-rule energy = `rule_totals` (exact, equals the evaluator). "Why not elsewhere": relocate the chunk to the asked slot in a
scratch state; if the move breaks a hard rule the answer is that rule (a wall); otherwise the per-rule energy difference, top
three rules first (`engines/explain.py`, tested to equal the evaluator difference).

### 12.9 T > 0 samples and probabilities

Samples come from chains at a fixed temperature from the plan (E010). See section 5 for diversity and calibration; only quote
probabilities when the temperature is matched to the user's estimated noise.

### 12.10 Learning (sections 6-8)

- **Weights**: theta = multipliers on the hand-set rule weights; features phi_r = rule r's cost at its reference weight.
  Bradley-Terry likelihood over every ranking and drag (drags x3), P(A beats B) = sigmoid(-theta·(phi_A - phi_B)/(|.|_1 s)),
  s = 0.05, Gaussian prior N(1, 1) per weight, theta >= 0.02, refit after each week; optional small CD step from lived weeks
  for users with low answer noise.
- **Answer noise**: fitted per user (temperature grid 0.02-0.5, cross-validated); used for the query budget and the state test.
- **Hidden units**: theta_eff = theta x exp(U h), U = the four dials' rule loadings; a picked pace clamps h; automatic inference
  of h from rankings, skips and check-ins only after the units beat taste-only-at-its-best-temperature by 2 nats of predictive
  log-likelihood (E013c).

### 12.11 Supervisor policies (section 8)

Hard-rule feedback -> walls. Rankings and drags -> the likelihood. Contradictions -> the state test (units on only if it passes).
Lived weeks -> small CD regulariser. Skips, check-ins -> state evidence. Missing features: every 2 weeks from week 6, the
cross-validated gain of each of 132 `time_preference` templates; propose the best above 0.114 nats per ranking in plain words;
add it only on the user's yes. Walls never soften silently: one question at the first contradicting event (or, with questions
off, propose softening as a price after 3 events in 3 distinct weeks within 6). Active queries: query-by-committee (6 bootstrap
fits), at most ~10 questions in the first weeks, stop when committee disagreement < 20% or the answer noise is high.

### 12.12 Expected performance (laptop, single core per chain; measured under load, so conservative)

| quantity | measured | reference target |
| --- | --- | --- |
| hard-rule violations | 0 in every v3 plan of every experiment (thousands of plans) | 0 |
| avoidable lateness | 0 on 72/72 (E005), 36/36 adversarial (E018), 288/288 semester plans (E017) | 0 |
| cold plan, 40-60 items | 1.3 s median, 2.9 s p90 (E017, 2 s step budget) | p90 <= 10 s |
| warm replan | 0.9 s median / 0.94 s p90 at a 1 s budget; 2.7 s at 3 s (E009b) | p90 <= 3 s |
| construction (the deadline-feasible start) | 0.7 ms median, 32 ms max at 150 items (E005) | (deadline stage <= 3 s) |
| move proposals | ~550k per second per core (E007) | - |
| quality vs v2 at 30 s | ties or beats on every comparable stage at 2-10 s (E004, E007); behind on tight 2 h-chunk overload packing (E018d) | - |
| determinism | identical plan for the same input, seed, profile and step budget, any thread count | same input -> same plan |
| JIT | ~66 s cold, ~1 s from the shipped cache | - |
