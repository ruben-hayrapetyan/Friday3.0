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
- **Session 2, end**: all phases done (P0-P9); `REPORT.md` complete (assembled from `report/sections/` by
  `report/assemble.py`; figures by `report/make_figures.py`). 25 experiment folders (E001-E018d). Recommendation: slot-state
  energy sampler with walls + construction/repair/CP-SAT fallback; BT ranking learning; gated dial units; supervisor policies.
- **Session 3** (2026-10-17): program 2 started (`RESEARCH_PROMPT_2.md`, phases Q0-Q7, RQ11-RQ17): duration
  prediction from estimates + recorded actuals, three schedules to pick from, learning from picks, constraints parsed from
  text by Sonnet 5.5 via the `claude` CLI. Consumer: the Friday app (`../UI`).
- **Session 3, later** (2026-10-18): on the user's request the engine is wired into the Friday app as a Planner page
  (app branch `rhayrapetyan/planner-tab`, merged into `personal` and installed; not pushed). E021 rounds 1-2, E022
  round 1, E024 round 1 done; E022 round 2 (ranking the three) and E024 round 2 (p95) queued (`queue_p2b.sh`).
- **Session 3, end** (2026-10-18): program 2 complete. E019-E025 done (E021, E022, E024, E025 in two rounds); report
  sections 14-15 written, `REPORT.md` reassembled; 195 tests pass. Engine defaults set from the experiments (decisions
  31-35); the installed app picks them up when it next starts the engine.
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
| P3 Representations + hard constraints (RQ1-3) | 3 sessions | done: E003-E006b; shortlist = walls (+ CP-SAT fallback) |
| P4 Samplers + speed (RQ4, RQ9, RQ10) | 3 sessions | done: E007-E010, E009b |
| P5 Simulated users + learning (RQ5) | 2 sessions | done: E011-E012, E011b, E011c (3 rounds) |
| P6 Hidden units (RQ6, RQ7) | 2 sessions | done: E013, E013b, E013c (3 rounds) |
| P7 Supervisor (RQ8) | 2 sessions | done: E014-E016 (+ policies wired into fr/system.py) |
| P8 Integration + weakness hunt | 2 sessions | done: E017, E018-E018d |
| P9 Report | 1 session | done: REPORT.md (report/sections + report/figures) |

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

24. **(Program 2) LLM = Sonnet 5.5 through the `claude` CLI** in print mode with no tools, as the Friday app already runs
    it (`UI/Sources/Calendar/ClaudePanel.swift`): no API key, the user's own sign-in. Only for text -> typed constraints,
    confirmed by the user and stored; never on the planning path.
25. **(Program 2) Sidecar store, not `todos.json`.** Todo List drops unknown keys, so estimates, actuals, picks, constraints
    and the learned profile live in Friday's own files (`~/Library/Application Support/Friday/engine/`), keyed by task UUID.
26. **(Program 2) Bridge = `fr serve`**, JSON lines over stdio, launched by the app the way it launches the `claude` CLI
    (no port, no HTTP stack; one long-lived process keeps numba's compiled code warm). Swift changes are out of scope.

27. **(Program 2) Constraint prompt = guide2** (E019): role + translation guide (hard/soft wording, night windows end in the
    morning, sleep nights named by the evening, ask instead of guessing, report the inexpressible) with the CLI's
    structured output; no few-shot examples (they added nothing). 99.0% of held-out cases fully right over 3 runs.
28. **(Program 2) Duration model = hier_fused_drift_fa3_recal** (E020, 3 rounds): ratio actual/estimate and length, each a
    Bayesian ridge over (all, kind, course, course x kind), fused once 3 lengths are recorded (before that the user's
    estimate is the prediction, as the user asked), 4-week half-life, online recalibration. CRPS 0.187 vs 0.290 for
    estimates as given; p80 covers 80%.
29. **(Program 2) Fixed-step planner for the product** (`fr.product.planner`, `Engine`): construction -> repair -> (CP-SAT
    deadline fallback <= 60 items) -> lexpolish with step counts, so the app's plans are deterministic.
30. **(Program 2) The three options all start from the repaired zero-late plan** and share its deadline walls, so no option
    is later on a hard deadline than the recommended one (tested per method).
31. **(Program 2) Hard deadlines are planned at p95** (E021 round 2; was p80): along the padding frontier the shipped
    duration model beats the alternatives at every point, and p80 -> p95 cuts hard-deadline misses 15.1% -> 4.3% for
    ~23 min a day of reserved time left unused. Flexible tasks stay at the median.
32. **(Program 2) "Recommended picked" is not a metric on its own** (E022 round 1): generators whose alternatives are worse
    plans score highest on it. The product goal is: the user gets a good plan (pick regret), Friday learns (cosine), and
    the recommended label predicts the pick. The label was below chance because alternatives get more annealing than
    the recommended plan; round 2 ranks the three after making them.
33. **(Program 2) Options = thompson+post** (E022 round 2): Thompson alternatives, then the three ranked by posterior-mean
    pick probability. Recommended picked 27% -> 63%, its regret 0.135 -> 0.100, lived regret unchanged.
34. **(Program 2) Learn from picks alone (MNL)** (E023): -25% regret vs no learning; pairs and drags add nothing on average
    and hurt missing-rule / adversarial users. Matches what the app collects.
35. **(Program 2) Questions** (E024 round 2): at most two "how long did it take?" a week (misses 2.9% -> 0.2% at p95);
    estimates only when one saves >= 60 min of p95 padding (neutral on misses, frees ~20 min/day).
36. **(After program 2, from use, 2026-10-18) Schema: task types, exclusions, soft one sitting.** The user's "I like to
    do things in one go, but split problem sets rather than other assignments" came back unsupported: one_sitting was
    hard only, and a target could neither name problem sets (kind "assignment" covers them) nor leave tasks out. Added
    `Target.types` (from the title: `adapter.type_of`; a task in Assignments must say "problem set", "HW", ... to be
    one), `exclude_types`, `exclude_titles` (compiled by tagging matched items, since rule scopes have no negation), and
    `OneSitting.strength` (soft = chunk_cost 0.2 / 0.4 / 0.8). Prompt guide3 = guide2 plus three lines; E019's 99.0% was
    measured on guide2 and the old schema, not re-run. Live check: Sonnet 5.5 turns the sentence into one_sitting mild
    for problem sets + medium for everything else. Engine check: a strong soft one sitting takes the test week's
    sessions from 2-3 per task to 1.
37. **(After program 2, from use, 2026-10-18) A capped cushion, every due date a deadline, and saying when a week does
    not fit.** On the user's real week (51 estimates, 0 recorded lengths) p95 reserved 3.3x each estimate (CATC: 2 h
    -> 6 h 35 m, due in 3.4 h) and 14 tasks came out late. E021's p95 assumed a learned spread; with none recorded the
    spread is the prior's. Now the cushion is at most 1.25x the user's estimate (1.5x Friday's guess) until 3 lengths of
    that kind are recorded, then at most 2x; `questions` measures savings with the same caps. Readings and emails with
    a due date were soft (soft_late, weight 3) and were the first pushed late in an overloaded week ("Math read 16.2",
    1 h, due today); every due date is now firmness hard, in the deadline stage (weight 1e6, as late_work already was).
    Same week, no events: 14 late -> 7. The rest is real overload (76 h due by Thursday night, 60 h free under the
    user's 10:00-23:30 rule and the 12 h daily cap), which the plan's notes now say. Not re-run in simulation: E021 and
    E025's miss rates were measured at uncapped p95 with soft readings.
38. **(After program 2, from use, 2026-10-18) Fewest late tasks, and parts of a set in order.** On the user's real week
    (82 calendar events, office hours and room bookings not busy) the plan had 21 late tasks; an earliest-deadline
    bound on the same free time was also late on ~20, but Moore-Hodgson on the free-time line shows 6 is possible
    (128 h of dated work, 129 h free before the last deadline: the overload is front-loaded). late_work prices units x
    hours late, which prefers many tasks a little late; people count late tasks. Added: rule `late_tasks` (product only,
    deadline stage: a fixed cost per late task, unplaced work costing at least as much); `fewest_late` picks the tasks to
    slip (biggest first, the later part on ties, dependants follow) and gives them importance 1; `edf_start` builds an
    alternative start (on-time work as late as its deadline allows, slipped work forward into the earliest free time,
    whole sessions, caps, dependencies), kept when the deadline-only search leaves it valid and less late. And tasks of
    one course, type and due date are ordered (the user saw "odds / evens / odds / evens"): each waits for the one before.
    User's week: 21 late -> 7 (6 slipped + one part waiting on a slipped part). Price: a slipped task can slip far (one
    half problem set to Oct 31). Not run in simulation.

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
| E006b-stage-polish | Weighted search + capped polish? | lexpolish: same median wellbeing, preferences 2.3x better than tiered and 19% better than weighted-1000 (better on 95% of instances); wellbeing slightly worse on 20% (p90 +5.5%). Recommended stage policy. |
| E009b-warm-churn | Does lexpolish cut warm churn? | Yes, 9-12% (to 38.6 h at 3 s, ~CP-SAT-30's 37.6 h) with half the preference cost; with repair, zero late matches CP-SAT (93%). CP-SAT-30 still has lower wellbeing on ~63% (approximate pairing). v3 warm is 9-27x faster. |
| E017-semesters | v3 vs v2 over semesters (report seeds) | v3: 0 misses, 0 invalid in 288 plans, 1.3 s vs 19.8 s, regret 0.087 vs 6.13 (beats v2 every week); v3_lex (same stage policy as v2) beats v2 in 78% of weeks; v2: 3 weeks with misses, 2 invalid. Right rule added for 3/3 missing-feature users, no wrong rules. Units never auto-on (gate slow). |
| E018-E018d weakness hunt | Break v3 | v3 deadline-safe 36/36 (CP-SAT 64%). Failures: packing without CP-SAT; the fallback ate the budget on 150 items. Fixed: size-ordered pipeline (CP-SAT first <= 60 items). Still behind CP-SAT-30 on tight 2 h-chunk packing (3/6 vs 6/6 at best lateness on E-cores). Bug: the fallback stage got 2 s, not 5 s (fixed). |
| E006-stages | Lexicographic vs weighted vs tiered? | Weighted r<=10 sacrifices wellbeing; r=1000 matches tiered wellbeing on 80% and has 3x better preferences: plain tiered search is the weak one. Round 2 (E006b): weighted-1000 search + capped preference polish. |
| E012-rbm-from-data | RBM from lived weeks only | Dead end as a scheduler: cannot tell lived weeks from Friday's (lower F for Friday's 60-80%), ranking acc 0.62-0.64 vs rules 0.80-0.87, samples ignore amounts. |
| E013-hidden-units | Hidden units for mood? | Dial-seeded units cut moody users' regret by a third but cost easy users (false attribution 23-42% of weeks); a per-user predictive test separates state from noise for 8/9 users -> gate the units. Pace clamping helps most. |
| E014-missing-features | Can the supervisor find a missing rule? | Right rule for 6/6 evaluation users by week 4, never a wrong rule for them; false proposals on users without one 33% at week 4 -> 0% by week 10. Regret effect inconclusive (noise). Policy: propose from week 6, add on the user's yes. |
| E015-soften-walls | Should walls soften? | Ask once at the first contradicting event: regret 15 vs 50 (3 events) vs 94 (auto) vs 114 (never). Never soften silently. |
| E016-active-queries | Which comparisons to ask? | Easy users: QBC/uncertainty reach 90% in 10-12 questions vs 25 random. Noisy users: every strategy loses accuracy vs the prior for 20-60 answers; QBC degrades least. |
| E019-constraint-parsing | Text -> typed constraints with Sonnet 5.5 | guide2 prompt: 98.5% tuning, **99.0% held out** (3 runs x 33); round-1 guide 97.0%, no guide 87.9%; structured output beats schema-in-prompt (fewer needless questions); zero invented constraints held out; ~3.3 s, ~$0.006 per text. |
| E020-duration-models | Which duration model? (prediction) | Estimates as given CRPS 0.29; one personal bias 0.22; hierarchical fused with history 0.19 (noisy estimators 0.35 -> 0.22); recalibration fixes p80 coverage (0.75 -> 0.80); round 3: fusing from day one helps the first 2 weeks even when population defaults are off, but the user asked for their own numbers first -> fa3. |
| E021-durations-downstream | Do better predictions mean fewer missed deadlines? | Learning cuts hard misses 2-4x at every quantile. At p80 the one-bias model looked better (10.9% vs 15.1%: wider spreads pad more), but along the frontier the shipped model wins at equal unused time; p95: 4.3% late, 1.57 h/day unused. -> plan hard deadlines at p95. |
| E022-three-schedules | How to make options 1-2? | Round 1: learning the same for all generators; pick regret seeds 0.086, thompson 0.093, temperature/diverse worse; recommended = user's best only 23-30% (alternatives get extra steps). Round 2: ranking by posterior pick probability -> recommended picked 63% (from 27%), lived regret 0.088. |
| E023-pick-learning | How to learn from the pick? | MNL on picks alone: regret of the recommended 0.110 -> 0.082, cosine 0.904; + pairs/drags 0.094 (hurts missing-rule and adversarial users); pairs only 0.130 (worse than none); status-quo lean slows, does not bias. |
| E024-asking-policy | When to ask for lengths? | p80: estimates raised misses (overconfident fusion, p80 covers 74%); actuals cut them. p95: two actual-length questions a week 2.9% -> 0.2%; estimates trade padding (-21 min/day unused, misses n.s.). |
| E025-end-to-end | The whole loop | As shipped (picks only) vs v3 as built: hard late 8.8% vs 67.5%, hours late 52 vs 1098, habit conflicts 0.08 vs 7.8 h/week, lived regret 0.014 vs 0.039. Ablations: constraints carry habits (11.7 h/week without), options carry regret (0.093 without), duration learning n.s. here (10.4%). |
| E003-strict-qubo | Pairwise QUBO with penalties, price-only slice | Dead end: never meets hard deadlines (0-5%) at any penalty scale; alpha < 3 cheats, alpha >= 3 freezes (slack bits absorb unplaced work); 25-200x worse than optimum. Hopfield descent same. |

- **E001 findings in one line each:** time-limited quality is the baseline at n>=40; v2 determinism needs 1 worker; stage-1 can
  freeze a bad plan (n=40 seed 1: 606 h late, FEASIBLE only); EDF is a one-directional certificate; overflow is large at 45% load.

## Next steps (if the program continues)

1. Re-measure speed on an idle machine (all session-2 timings ran under a co-tenant's load).
2. Open questions (REPORT section 11): answer temperature inside the fit; faster state detection; a "rebuild item" move for
   reachability at T > 0; a tuned size threshold for the deadline pipeline; interval CP-SAT (6A.9); DST scenario.
