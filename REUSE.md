# Reusing the research code

The scheduler and learning designs in `DESIGN.md` §10–12 and §21 come from a research program. Its code lives read-only in `reference/research/` (`src/fr/`, `tests/`, `REPORT.md`). That code is tested and measured, so port it instead of rewriting it. But it was written for experiments, not for this app, so every module changes on the way in.

## Rules for porting

1. **Never import from `reference/`.** Copy a module into its v3 location, then adapt it. Nothing in `src/friday/` or `tests/` may import `fr`.
2. **Bring the tests with the code.** Port the module's tests, get them green on the copy **before** changing behavior, then make the changes below and add tests for each.
3. **Golden fixtures first (start of M2).** Before changing any engine code, use the research code once to write fixtures to `tests/fixtures/golden/`:
    - 40 generated instances, across sizes and adversarial families;
    - for each, 5 plans (the constructed start plan, an annealed plan, and 3 random valid plans);
    - for each plan, its stage values and per-rule totals from `fr.core.evaluate`.

    v3's evaluator and kernel must reproduce these exactly, for as long as the rule definitions agree. If DESIGN.md deliberately changes a rule, regenerate that rule's fixtures and record why in PROGRESS.md. The fixture script is the only code that may touch `reference/`, and it runs once.
4. **`REPORT.md` explains why.** Before porting a module, read the report section that motivated it. Its numbers are the bar the port has to meet.
5. **Record every port in PROGRESS.md:** source file, destination, what changed, tests brought.
6. **If the research code and DESIGN.md disagree, DESIGN.md wins.** Tell me about it.

## Module map

| Research (`src/fr/`) | v3 location | When | Port as | Changes |
| --- | --- | --- | --- | --- |
| `core/grid.py` | `core/time.py` | M1 | Port, then extend | Add daylight-saving days (the research assumed every planning day is 24 h); keep units vs slots exact across the 15/30-minute boundary |
| `core/settings.py`, `core/defaults.py` | `core/settings.py` | M1 | Merge | DB-backed pydantic models with TOML export (DESIGN §17); the reference rules from §12.4 as defaults |
| `core/generate.py` | `sim/generate.py` and `tests/bench/generator.py` | M1 (generators), M7 (semester) | Port | Emit v3 items (facets, presets) rather than research instances; keep the adversarial families |
| `core/pwl.py` | `engine/pwl.py` | M2 | Port | Lin over the symbolic variables in §12.1 |
| `core/context.py` | `engine/rules/__init__.py` (BuildContext) | M2 | Port | Variable constructors only; no kernel or CP-SAT exposure |
| `core/rules.py` | `engine/rules/__init__.py`, `prices.py`, `measures.py` | M2 | Port and split | v3 `Rule` interface (§12.1): scope fields, `reason`, dial factors via `problem.scales[day]`, learned multipliers θ (§12.2). Keep every formula identical unless §12.2 says otherwise |
| `core/problem.py`, `core/plans.py` | `engine/problem.py` | M2 | Port, then extend | `EngineItem` fields from §11.1; `Solution` per §11.12 |
| `core/evaluate.py` | `engine/evaluate.py` and `engine/checker.py` | M2 | Port and split | Stage values and per-rule totals in `evaluate.py`; `check()` in `checker.py`, with walls named W1–W9 |
| `core/direct.py` | `tests/engine/direct_eval.py` | M2 | Port as a test oracle | The independent evaluator from slot arrays; tests assert it equals `evaluate()` |
| `core/brute.py` | `tests/engine/brute.py` | M2 | Port as a test helper | Exhaustive search on tiny instances |
| `engines/compile.py` | `engine/compile.py` | M2 | Port | Fold in dial factors and θ when compiling; the integer rounding must stay identical to the evaluator's |
| `engines/kernel.py` | `engine/kernel.py` | M2 | Port | Keep the no-runtime compilation and the flat-array model; walls named W1–W9; the 11 moves of §11.7. This is the most valuable file in the research. Change it only with the exactness tests running |
| `engines/construct.py` | `engine/construct.py` | M3 | Port | Warm start with a previous plan; lock demotion and rerun |
| `engines/repair.py` | `engine/repair.py` | M3 | Port | `engine.repair_steps` from settings |
| `engines/prepare.py`, `core/remap.py` | `engine/scheduler.py` (helpers) | M3 | Port | Temperature calibration from the median valid Δ (excluding deadline deltas); plan remapping for warm starts |
| `engines/api.py` (`run_v3`) | `engine/scheduler.py` | M3 | Port, then rewrite the edges | The pipeline construct → repair → fallback (ordered by size) → anneal from §11.6. **Step budgets only**: remove any budget computed from measured speed or time |
| `samplers/anneal.py`, `chains.py`, `runner.py` | `engine/sampler.py` | M3 | Port and merge | Geometric Metropolis schedule; the stage policies (`lexpolish`, `weighted`, `strict`); chains as threads with per-chain seeds; tabu finish; cancellation every 50k steps |
| `samplers/tiered.py` | `engine/sampler.py` (`strict` policy) | M3 | Port | One of the three stage policies |
| `baseline/cpsat.py` | `engine/cpsat_deadlines.py` | M3 | Port the deadlines stage only | Drop the wellbeing and preferences stages; keep C1–C8 and the unsat-core lock relaxation; time limits from `engine.fallback_s` and `fallback_overload_s` (the research had a bug passing the stage time as the total, so check this) |
| `engines/explain.py` | `engine/explain.py` | M3 | Port, then extend | Per-block costs, `why`, `why_not` by relocation, naming the wall when a move is forbidden (§16) |
| `baseline/allocator.py` | `engine/allocator.py` | M4 | Port | Dial capacity factors (§13.1) |
| `core/edf.py` | `engine/executor.py` | M4 | Port, then extend | Slack, safe swaps, `now`, provisional placement (§14) |
| `baseline/whatif.py` | `planner/service.py` (`what_if`) | M5 | Rewrite from it | v3's `what_if` runs construct → repair → fallback, not a CP-SAT stage (§15.3) |
| `core/builder.py` | `planner/build.py` | M5 | Port the parts that fit | Pruning (§11.2) and lock repair (§15.2) carry over; building from a research instance becomes building from a snapshot |
| `sim/world.py`, `sim/user.py` | `sim/world.py`, `sim/users.py` | M7 (world), M9 (learning users) | Port | The loop drives Friday through the command registry with a fake clock (§24.4); keep the five user families |
| `learn/methods.py` | `learn/preferences.py` | M9 | Port only Bradley–Terry and answer noise | Drop the ranking QP, contrastive divergence, PCD and max-margin learners (research dead ends, §21.2) |
| `learn/hidden.py` | `learn/state.py` | M9 | Port | The multiplicative units and the calibrated gate (§21.3), off by default behind `learn.state_inference` |
| `supervisor/grammar.py`, `supervisor/discover.py` | `learn/proposals.py` | M9 | Port | Proposals are asked, never auto-added (§21.5) |
| `system.py` | `learn/` wiring and `sim/` loop | M9 | Use as a reference | The research's end-to-end loop: read it to wire feedback routing (§21.1), query choice (§21.4) and wall questions (§21.6) into commands and the review screen |

## Tests to bring

| Research test | v3 location | Notes |
| --- | --- | --- |
| `test_kernel.py` | `tests/engine/test_kernel.py` | **Most important.** Extend to both grid zones, a DST day, dial factors and θ |
| `test_differential.py` | `tests/engine/test_differential.py` | `direct_eval` vs `evaluate()` |
| `test_rules.py` | `tests/engine/test_rules.py` | Add the zone-boundary case per rule (DESIGN §24.1) |
| `test_checker.py` | `tests/engine/test_checker.py` | One test per wall W1–W9 |
| `test_brute.py` | `tests/engine/test_brute.py` | |
| `test_scenarios.py` | `tests/scenarios/` | Map onto DESIGN §24.2's numbering; add 30–33 |
| `test_samplers.py` | `tests/engine/test_sampler.py` | Add determinism across thread counts and cancellation |
| `test_edf.py` | `tests/engine/test_executor.py` | |
| `test_grid.py` | `tests/core/test_time.py` | Add DST days |
| `test_baseline.py` | `tests/engine/test_cpsat_deadlines.py` | Deadlines stage only |
| `test_learning.py` | `tests/learn/` | Bradley–Terry parts only |
| `helpers.py`, `conftest.py` | `tests/helpers.py`, `tests/conftest.py` | |

## Do not port

- `engines/qubo.py`: the strict Boltzmann machine, a research dead end.
- `baseline/lns.py`: the CP-SAT large-neighbourhood polish, slower than annealing.
- The staged CP-SAT wellbeing and preferences stages in `baseline/cpsat.py`.
- `bench.py` and `shard.py`: experiment plumbing (v3 has its own benchmark, §24.5).
- `experiments/` and the analysis scripts.
- Any use of measured speed or wall-clock time to size a step budget.
