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

- **Session 1** (2026-10-17): P0 done, P1 done, P2 started. See "Next steps".
- Branch: `rhayrapetyan/backend` (off `main`). Project root: `BackendGuidelines/`.

## Hardware (P0)

Apple M3 Max, 16 cores (12 performance + 4 efficiency), 64 GB RAM, integrated GPU (40 cores, unused).
Python 3.12.13 via uv 0.13.1 (Homebrew). numba 0.68, OR-Tools 9.15, scipy 1.18, cvxpy 1.9, numpy 2.5.
Laptop timings vary with power and thermals: repeat 3x, report variance (RESEARCH_PROMPT section 7).

## Phase plan and rough budgets

| Phase | Budget | State |
| --- | --- | --- |
| P0 Setup | 0.1 session | done |
| P1 Problem core | 1 session | done (see below) |
| P2 Baseline (v2 CP-SAT grid, staged) + quality-vs-time curves | 1-2 sessions | in progress |
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
`tests/`: 84 tests, ~10 s. Run: `cd BackendGuidelines && uv run pytest`.

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
10. Commits go on branch `rhayrapetyan/backend` in the outer Friday repo (the research prompt asks for commits after every step).

## Findings so far

- **EDF exactness is about feasibility.** When jobs cannot all finish, `L_max` depends on a convention for unfinished jobs, so only
  its sign (`<= 0` iff feasible) is exact; it equals the exhaustive optimum whenever it is feasible. 300-example property tests
  against an exhaustive DP agree. Slack >= 0 iff feasible also holds. (reference 9.2 says "exact"; true for the feasibility test.)
- Two of my own hand-written test expectations were wrong (not the code): the differential evaluator caught no code bugs on
  first run, which is why `tests/test_differential.py` asserts that each rule actually fires, so agreement is not vacuous.
- `quota` can't fire without the allocator (not built yet); it is covered with hand-made quotas.

## Experiments

(none yet; E001 = v2 baseline matrix is next)

## Next steps

1. P2: faithful staged CP-SAT grid model (`src/fr/baseline/cpsat.py`): x, over, start, cum, any_of; C1-C8; staged lexicographic
   solve with deterministic time limits; score every plan with the shared evaluator.
2. Reference scenario tests 1-9, 11-24 against the baseline (12.1). Compare CP-SAT optimum to brute force on tiny instances.
3. Allocator (section 8) so `quota` and weekly pacing exist; `what_if`.
4. E001: baseline matrix (20/40/60 items, seeds 0-9 tune / 1000-1009 report), cold and warm, quality-vs-time curves.
5. Then P3.
