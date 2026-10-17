# Friday v3 engine research — log

Memory across sessions. Keep it short: status, decisions, numbers, next steps. Details live in `experiments/E###-*/notes.md`.

## Goal (my reading)

Find out whether Friday's scheduling engine should be rebuilt as an energy-based / Boltzmann-machine sampler with a
logical supervisor, instead of v2's staged CP-SAT. Test it against a faithful v2 baseline on one shared evaluator.
Deadlines, one-thing-per-slot, locks and the sleep core must stay *guarantees* (walls), not penalties.
Also test: Boltzmann/ranking learning of rule weights, hidden units (dials) for mood, a supervisor that sorts
feedback into walls / rankings / state / likelihood, and what happens when a rule is missing.
Output: one `REPORT.md` with an engine spec precise enough to write a v3 design from. No app, UI, DB or server.

## Status

- **Session 1** (2026-10-17): P0 done, P1 done, P2 done (baseline built, scenario tests pass, E001 run). 138 tests pass.
  Baseline misses its own speed targets (see E001). Next: E002 baseline tuning, then P3.
- **Session 2** (2026-10-17): P3-P7 built. Compiled energy kernel (numba) exact against the evaluator/checker; wall sampler;
  QUBO, LNS, PT, population annealing, tabu; simulated users; learners; hidden units; supervisor (discovery, softening,
  active queries). E002-E003 done; E004-E016 queued (`experiments/queue_*.sh`, progress in `queue_*.txt`).
- Branch: `rhayrapetyan/backend` (off `main`). Project root: `BackendGuidelines/`.
- **Machine is shared** from session 2: a trading bot runs on it (load average 30-45 on 16 cores). All jobs run at
  `nice -n 19` (asked by that session). Timing numbers from E004 on carry this load; each queue logs the load at start.

## Hardware (P0)

Apple M3 Max, 16 cores (12 performance + 4 efficiency), 64 GB RAM, integrated GPU (40 cores, unused).
Python 3.12.13 via uv 0.13.1 (Homebrew). numba 0.68, OR-Tools 9.15, scipy 1.18, cvxpy 1.9, numpy 2.5.
Laptop timings vary with power and thermals: repeat 3x, report variance (RESEARCH_PROMPT section 7).

## Phase plan and rough budgets

| Phase | Budget | State |
| --- | --- | --- |
| P0 Setup | 0.1 session | done |
| P1 Problem core | 1 session | done (see below) |
| P2 Baseline (v2 CP-SAT grid, staged) + quality-vs-time curves | 1-2 sessions | done (E001); E002 tunes it for fairness |
| P3 Representations + hard constraints (RQ1-3) | 3 sessions | |
| P4 Samplers + speed (RQ4, RQ9, RQ10) | 3 sessions | |
| P5 Simulated users + learning (RQ5) | 2 sessions | |
| P6 Hidden units (RQ6, RQ7) | 2 sessions | |
| P7 Supervisor (RQ8) | 2 sessions | |
| P8 Integration + weakness hunt | 2 sessions | |
| P9 Report | 1 session | |

## What exists (P1)

`src/fr/core/`: `settings` (reference defaults) · `grid` (15/30-min slots, planning days/weeks) · `pwl` (`Lin`, convex
hinges, integer coefficients) · `problem` (items, fixed occurrences, nights, dial scales) · `rules` (all 20 reference
rule types: price / forbids / measures) · `context` (BuildContext) · `evaluate` (shared evaluator + hard-rule checker) ·
`direct` (a second evaluator from slot arrays, no `Lin`) · `builder` (facet specs, presets, pins, lock repair, pruning) ·
`edf` (executor: exact feasibility, latest starts) · `brute` (exhaustive solver for tiny instances) · `generate`
(reference benchmark, Cornell semester, stress to 150 items, 6 adversarial families, tiny) · `plans` (random plans).
`src/fr/baseline/`: `cpsat` (staged GridModel, lock-core repair), `allocator`, `whatif`.
`tests/`: 138 tests, ~4 min (CP-SAT scenario and fuzz tests dominate). Run: `cd BackendGuidelines && uv run pytest`.

## Decisions and assumptions

1. **DST simplified away** (allowed by the prompt): wall-clock minutes, a planning day is always 24 h. The reference's
   DST scenario (#10) is therefore not tested; zone-boundary crossing is.
2. **Cost scale.** All costs are integer scaled points (100 = 1 point). Price rows are `round(w x dial x price x hours x 100)`;
   hinge coefficients are `round(w x mult x slope x 0.25 x 100)` per unit (per count: no 0.25), never rounding a positive value to 0.
3. **Evaluator independence.** `evaluate.py` (Lin; same structure CP-SAT builds from) is cross-checked against `direct.py`
   (slot arrays) on 24 generated cases + dials + extra rules: agree to the integer. The checker is cross-checked against an
   independent re-derivation of the hard rules over *every* assignment of 12 tiny instances.
4. **Open items:** `daily_ceiling` is the full per-day ceiling; today's progress is `progress_today` (the reference's wording
   was ambiguous). Day-0 cap = ceiling - progress_today; the open_value curve uses the full ceiling.
5. **Night.** Stores `debt_hours`, not the multiplier, so the rest dial can scale `debt_factor` as section 10 requires.
6. **Dependency lag** is in minutes; `cum` is read at the slot containing `start(s) - lag` (conservative on coarse slots).
7. **Energy map** (the reference gives none): deep-work price by local hour, 0 at 10-12, 3 at night. Starting value.
8. **target_shortfall** under dials: weight and target amount use the mean growth over the window's days with allowed slots.
9. **Tie-breaking.** Rules never read a clock or RNG; brute-force ties are returned as a list.
11. **C2 tightened:** `need + 1` units only when a coarse slot is used (reference allows it always; that made replans churn at equal cost). Checker matches.
12. **Lock repair generalised:** a lock overrides dependency ordering; if locks still contradict the hard rules, `solve` takes the CP-SAT unsat core over per-item lock literals and demotes those items' locks to preferred pins (reported in `SolveResult.demoted_locks`). Also demotes locked runs that break chunk limits and cannot grow.
13. **Allocator tie-break:** default `pace` (as late as pacing allows) instead of the reference's epsilon-earlier, which front-loads (scenario 19 expects a linear share).
14. **Default hint** = locks-only plan. Pins in generators are placed inside the item's window.
10. Commits go on branch `rhayrapetyan/backend` in the outer Friday repo (the research prompt asks for commits after every step).

15. **Energy kernel.** Numba functions with `_nrt=False`: passing the 50-array model tuple to helpers cost ~100 ns per call in
    reference counting otherwise (measured), 10-15x slower moves. Never allocate inside the kernel; work arrays are passed in.
16. **Moves are unit-aware.** A chunk moved between the 15-min and 30-min zones keeps its units, not its slot count (the first
    version kept slot counts and silently trapped all work in the first week).
17. **Temperature calibration** uses the median |delta| of random valid moves that leave the walled stage unchanged (a first
    version let deadline-weighted deltas set T ~ 1e9: a random walk). Defaults: T0 = 0.1, T1 = 0.003 x median, geometric.
18. **Deadline wall** = a hard item that is complete and on time in the start plan ("protected") may only use on-time slots and
    may never lose units. Items late at the start are not protected; their lateness is just the heaviest energy term.
19. **Learning features** phi_r = rule r's cost at its reference weight, in points; theta = multipliers (1 = hand-set).
    Likelihood learning cannot fix theta's scale (it is the temperature), so CD keeps sum(theta) fixed.
20. **Determinism needs a step budget, not a time budget.** Sizing steps from measured speed makes runs depend on load; the
    production profile must fix step counts per instance size (E009 measures both).

21. **Hidden units act multiplicatively**: theta_eff = theta * exp(U h). The additive form E = sum (w + U h) phi lets theta's
    scale and the state trade off (found by a planted-state unit test); multiplicative keeps "state = relative change".
22. **Ejection move** (11th move, round 2 of P4): move a chunk onto one other item's chunk and re-place that chunk.
    Added before E007; E004-E006 ran with the first 10 moves.
23. **Skeleton hybrid keeps the better start** (construct vs time-limited CP-SAT stage 1): E004 showed the 3 s skeleton can be
    later than construction. Applies to runs after E004.

## Findings so far

- **EDF exactness is about feasibility.** When jobs cannot all finish, `L_max` depends on a convention for unfinished jobs, so only
  its sign (`<= 0` iff feasible) is exact; it equals the exhaustive optimum whenever it is feasible. 300-example property tests
  against an exhaustive DP agree. Slack >= 0 iff feasible also holds. (reference 9.2 says "exact"; true for the feasibility test.)
- Two of my own hand-written test expectations were wrong (not the code): the differential evaluator caught no code bugs on
  first run, which is why `tests/test_differential.py` asserts that each rule actually fires, so agreement is not vacuous.
- `quota` can't fire without the allocator (not built yet); it is covered with hand-made quotas.

## Experiments

| ID | Question | Finding |
| --- | --- | --- |
| E001-v2-baseline | How fast / good is faithful v2 on the reference benchmark? | Misses every speed target: cold p90 20-31 s (target 10), warm p90 18-26 s (target 3). Preferences stage never proven optimal (gap 63-94% at 9 s). Not deterministic with 8 workers (up to 2x spread). EDF optimistic in 6/69 runs. Executor 0.1 ms, allocator 0.13 s are fine. |
| E002-baseline-tuning | Can v2 work at a 10 s budget with fair tuning? | No: every variant times out (stage limits double) or returns hundreds of late hours; even a zero-late hint fails 7/10 (presolve > stage share). Fair baseline = v2 at 30 s. |
| E004-representations | Which representation, on equal budgets? | Wall sampler: 100% valid and deadline-safe, best W/P at 7 s; penalties 95% safe; skeleton hybrid hurt (bad 3 s skeletons); LNS too slow per neighbourhood; CP-SAT-30 s only 30% deadline-safe under load. Shortlist: walls (+ CP-SAT fallback). |
| E005-deadline-guarantee | Do walls deliver zero late whenever possible? | Construction 95.8%, + sampler repair 100% (72/72), CP-SAT alone 51%. Overload: CP-SAT hinted with the repaired plan is exact on 5/5 proven cases; on unproven overload the sampler beats CP-SAT-15 s on 20/23. EDF optimistic on 5/5 overloads. |
| E011-learning | Which learner? | Ranking QP best on easy users (0.92 acc) but bends to noise/mood/missing/adversarial; drags most reliable; CD alone weak; combined robust. Round 2: Bradley-Terry likelihood (E011b). |
| E011b-learning-round2 | Bradley-Terry likelihood vs QP vs combined | BT best on average (0.853 vs 0.83) and on adversarial users; below no-learning on noisy users (fixed temperature). QP results vary a lot between replicates. Default: BT + drags x3; open: per-user answer temperature. |
| E011c-learning-round3 | Fit the answer temperature? | It detects noise well (0.08 easy vs 0.18-0.5 others; saturates for adversarial) and makes BT the best on adversarial users, but hurts moody users. Replicate variance large (bt noisy 0.78 vs 0.89). Decision: BT for weights, fitted temperature as the noise estimate for query budget and state test. |
| E013b/E013c | Gate the units per user? | Round 2's gate opened for mood-free users (units win by softening predictions). Round 3 compares with a temperature-calibrated baseline: cost gone for mood-free users, but only ~1/4 of the gain for moody users. Units: explicit signals (pace) yes; automatic inference behind the calibrated gate. |
| E007-samplers | Which sampler on equal wall clock? | 8-thread multi-start ~ PT ~ population annealing (rank 2.3-3.5), beating single-chain SA on 25-29/30; PT on 1 thread worst; heat-bath = Metropolis; tabu finisher helps at 8 s; descent competitive at 2 s. 548k proposals/s; cold JIT 66 s. |
| E008-move-ablation | Which moves matter? | split essential (3x worse W without), insert/drop/shrink essential for preferences (elastic/target/open items start empty); far + swap matter; transfer/merge/eject/grow/shift near neutral; minimal set 9x worse W. Walls held in every variant. |
| E009-warm-determinism | Warm replans, churn, determinism | Warm sampler 0.4-2.3 s vs CP-SAT warm 24 s; CP-SAT-30 wins on quality (rank 1.4 vs 2.2) and churn (38 vs 44 h); CP-SAT-10 useless (33% zero late). Sampler reruns identical when the step count is fixed (one time-sized run differed); CP-SAT-8 workers identical 53%. Round 2: E009b (lexpolish keeps minimize_changes on). |
| E010-diversity-calibration | Are T>0 samples Boltzmann, diverse, calibrated? | Not Boltzmann over all valid plans: under walls chains reach only ~20% of tiny instances' valid plans (reachability, not mixing). Samples are diverse (66-71% of work slots differ). Item-day probabilities calibrated (ECE 0.003-0.009) when T matches the user's noise. |
| E004b-penalty-scale | Penalties on the full model | Walls 100% deadline-safe from construction (85% from empty); penalties <=1x median cheat (2-7x worse wellbeing), >=10x act like walls but 15-30% worse preferences; deadlines as a weight (1x) leave avoidable lateness on 25%; from empty, penalties miss 4.5-7 hard items. |
| E006-stages | Lexicographic vs weighted vs tiered? | Weighted r<=10 sacrifices wellbeing; r=1000 matches tiered wellbeing on 80% and has 3x better preferences: plain tiered search is the weak one. Round 2 (E006b): weighted-1000 search + capped preference polish. |
| E012-rbm-from-data | RBM from lived weeks only | Dead end as a scheduler: cannot tell lived weeks from Friday's (lower F for Friday's 60-80%), ranking acc 0.62-0.64 vs rules 0.80-0.87, samples ignore amounts. |
| E013-hidden-units | Hidden units for mood? | Dial-seeded units cut moody users' regret by a third but cost easy users (false attribution 23-42% of weeks); a per-user predictive test separates state from noise for 8/9 users -> gate the units. Pace clamping helps most. |
| E014-missing-features | Can the supervisor find a missing rule? | Right rule for 6/6 evaluation users by week 4, never a wrong rule for them; false proposals on users without one 33% at week 4 -> 0% by week 10. Regret effect inconclusive (noise). Policy: propose from week 6, add on the user's yes. |
| E015-soften-walls | Should walls soften? | Ask once at the first contradicting event: regret 15 vs 50 (3 events) vs 94 (auto) vs 114 (never). Never soften silently. |
| E016-active-queries | Which comparisons to ask? | Easy users: QBC/uncertainty reach 90% in 10-12 questions vs 25 random. Noisy users: every strategy loses accuracy vs the prior for 20-60 answers; QBC degrades least. |
| E003-strict-qubo | Pairwise QUBO with penalties, price-only slice | Dead end: never meets hard deadlines (0-5%) at any penalty scale; alpha < 3 cheats, alpha >= 3 freezes (slack bits absorb unplaced work); 25-200x worse than optimum. Hopfield descent same. |

- **E001 findings in one line each:** time-limited quality is the baseline at n>=40; v2 determinism needs 1 worker; stage-1 can
  freeze a bad plan (n=40 seed 1: 606 h late, FEASIBLE only); EDF is a one-directional certificate; overflow is large at 45% load.

## Next steps

1. E002: tune the baseline fairly (horizon/fine days, slot length, stage budgets, 1 vs 8 workers, hints) so v3 is not beaten
   against a straw man; fix the baseline's "best known" reference values per instance for gap metrics (long runs, 10 min).
2. P3: representations. Start with strict QUBO / Hopfield (deliberate failure: penalty scale vs feasibility), then Potts slot
   model, chunk-level with walls, and the CP-SAT/EDF-skeleton + sampler hybrid. Walls first: move sets that never leave the feasible set.
3. Open from P1/P2: reference scenario #10 (DST) untested; safe swaps (9.4) not built; allocator day-level dependencies lightly tested.
4. Investigate the zero_late < 1 instances at n=40 (dependency/cap chains?) to separate real overload from model artefacts.
