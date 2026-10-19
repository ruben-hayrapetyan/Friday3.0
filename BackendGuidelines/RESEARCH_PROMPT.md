# Friday v3 engine research — instructions for Claude Code

You are running a long, multi-session research program in this repository. It has no app and no user interface. The goal is to work out how Friday's scheduling engine should work if it is rebuilt around a **Boltzmann machine / energy-based model with a logical supervisor**, to test that idea rigorously against the existing CP-SAT design, and to finish with one reference report, `REPORT.md`.

Expect many sessions. Build several versions of each piece, benchmark them, look for their weaknesses, improve them, explore dead ends on purpose, and record everything. Thoroughness matters more than speed.

## 1. Files

| File | What it is |
| --- | --- |
| `ENGINE_REFERENCE.md` | The scheduling problem (items, rules, constraints, dials) and the v2 CP-SAT engine. It defines what any engine must solve and the baseline to beat. Read it in full in session 1; later, re-read only the sections you need |
| `RESEARCH_PROMPT.md` | This file |
| `RESEARCH_LOG.md` | Your memory across sessions (you create it). Keep it short: status, decisions, key numbers, next steps, links to experiment folders |
| `experiments/E###-name/` | One folder per experiment (section 6) |
| `REPORT.md` | The final deliverable (section 9) |

## 2. Background: the ideas under test

v2 schedules with CP-SAT: a three-stage lexicographic solve (deadlines → wellbeing → preferences) over a 15/30-minute slot grid, with convex rule costs. The energy of a plan is already linear in the rule weights:

```latex
E(x) = \sum_r w_r\, \varphi_r(x)
```

The v3 idea, as discussed so far:

1. **Sample plans instead of solving for them.** Treat E as an energy, p(x) ∝ exp(−E(x)/T), and find low-energy plans by annealing or parallel tempering. Hoped-for gains: faster solving (warm replans especially), anytime behaviour, diverse good plans at T > 0, and probabilities such as "PS5 lands Tuesday 70% of the time".
2. **Hard guarantees stay hard.** Deadlines (never late when an on-time plan exists), one thing per slot, locks and the sleep core must hold for certain. The working hypothesis is that these should be **walls**: moves that never leave the feasible set, plus the exact earliest-deadline-first check (reference §9). Very large penalty weights are expected to fail, either by freezing the search or by guaranteeing nothing. Test that hypothesis; don't assume it.
3. **Built-in learning.** Boltzmann learning moves each weight by Δw_r ∝ ⟨φ_r⟩_model − ⟨φ_r⟩_data, where the data is the weeks the user actually lived and the model term comes from Friday's own samples. Use a prior that pulls weights toward the hand-set values.
4. **Hidden units for state.** Hidden units h modulate rule weights:

   ```latex
   E(x,h) = \sum_r \Big(w_r + \sum_j U_{jr} h_j\Big)\varphi_r(x) + \sum_j c_j h_j
   ```

   v2's four dials (capacity, rest, spread, growth; reference §10) are hand-set hidden units. When the user picks a pace, the units are clamped to it; otherwise they are inferred from evidence (reviews, skipped blocks, sleep debt, check-ins). Seeding the units from the dials keeps them nameable.
5. **A logical supervisor** that manages the machine from feedback, sorting each kind of feedback to the right mechanism:
    - a plan that breaks a hard rule, or a new hard rule from the user → a wall;
    - a ranking "A better than B" while E(A) > E(B), or a manual drag (the user's version beats Friday's) → a ranking constraint w·(φ(A) − φ(B)) ≤ −margin. All rankings are kept, and the supervisor solves a small convex QP for the weights closest to the current ones (with slack, a step cap and the prior);
    - contradictory rankings over time → probably state, so explain them with hidden units;
    - lived weeks → likelihood learning;
    - skips and "not done" → evidence about hidden state.

   If no weights can satisfy the rankings, some feature is missing. The supervisor can then propose a new rule from a grammar of rule templates, or only flag the gap.

The user's answers to the open policy questions were all "it depends". Treat them as research questions (RQ7 and RQ8 below).

## 3. Research questions

- **RQ1 Representation.**
    - Strict Boltzmann machine: binary units, pairwise energy, constraints as penalties, helper bits for hinges.
    - Potts or slot-assignment model.
    - Chunk-level state with walls.
    - Hybrids: CP-SAT or EDF for the feasibility skeleton, energy sampling for preferences, large-neighbourhood search where the sampler proposes and a small exact solve repairs.

    Which is best, and why do the others fail?
- **RQ2 Hard constraints.** Penalty weights vs walls vs repair operators.
    - Show the deadline guarantee holds on every instance where the CP-SAT baseline finds zero late work.
    - Close the gap EDF leaves with minimum chunks and one-sitting items.
    - Decide how overloaded weeks (some lateness unavoidable) are handled: a CP-SAT fallback vs a heuristic, by quality and speed.
- **RQ3 Stages.** Lexicographic vs weighted vs tiered annealing for wellbeing vs preferences. How often, and by how much, do the weighted versions disagree with the lexicographic reference?
- **RQ4 Samplers and speed.**
    - Methods: simulated annealing schedules, parallel tempering, population annealing, Gibbs vs Metropolis, tabu hybrids.
    - Move sets: shift, swap, split, merge, resize, cross-day swaps, ejection chains.
    - Implementation: incremental energy deltas, compiled code (numba), multiple cores, warm starts at low temperature.
    - Compare against CP-SAT on equal wall-clock budgets, cold and warm.
- **RQ5 Learning.** Likelihood learning (contrastive divergence, persistent CD) vs ranking QP vs combined vs v2's inverse optimization from moves alone vs no learning. Measure sample efficiency, robustness to noise, and stability.
- **RQ6 Hidden units.** None vs dial-seeded vs dial-seeded plus free units. Inferring state, learning U, clamping on pace switches.
- **RQ7 Mood vs taste.** When rankings contradict, when should the system blame state, and when noise? What evidence separates them? What is the false-attribution rate?
- **RQ8 Supervisor policies.**
    - Missing-feature detection and automatic rule proposal vs flagging only (discovery rate vs false rules).
    - Whether a "never" wall should ever soften from evidence, and under what policy.
    - Active querying: which comparisons to show, uncertainty sampling vs random, measured as queries needed to reach an accuracy.
- **RQ9 Guarantees that must survive.**
    - Determinism: the same input, seed and profile give the same plan.
    - Exact explanations: energy decomposes into per-rule terms.
    - "Why not elsewhere": the energy difference.
    - Stability on warm replans: churn.
- **RQ10 Diversity and calibration.** Are T > 0 samples meaningfully different plans? Are the probabilities calibrated?

Add questions you discover along the way and log them.

## 4. Phases

Work through these in order. Inside a phase, iterate: build at least two variants where it makes sense, benchmark, hunt for weaknesses with adversarial instances, improve, and re-benchmark. Main phases (P3–P7) need at least two improvement rounds. Every dead end is logged with evidence.

| Phase | Work | Exit criteria |
| --- | --- | --- |
| **P0 Setup** | Detect hardware (CPU model, cores, RAM, GPU), set up the environment with `uv`, create the repo skeleton and `RESEARCH_LOG.md` with a phase plan and rough budgets | Hardware profile logged; `pytest` runs |
| **P1 Problem core** | Instance model; grid with both zones (DST may be simplified, but say so); **every reference rule as a feature φ_r** with an independent exact evaluator; a hard-rule checker; the EDF feasibility check; instance generators (the reference benchmark spec, a realistic Cornell-semester template, stress cases up to 150 items, adversarial families such as tight deadlines, overload, fragmented free time, many dependencies, many one-sitting items, many pins); a brute-force solver for tiny instances | The evaluator and checker agree with brute force on tiny instances; reference scenarios encoded as tests |
| **P2 Baseline** | A faithful minimal v2 CP-SAT grid model (staged, lexicographic) scored by the shared evaluator. Interval CP-SAT (reference §6A.9) if time allows. Quality-vs-time curves, bounds, proven optima on small instances | Baseline numbers for the full benchmark matrix |
| **P3 Representations and hard constraints** | RQ1, RQ2, RQ3. At least: strict QUBO/Boltzmann machine (expected to struggle; quantify how), Potts/slot model, chunk-level with walls, one hybrid | A shortlist of ≤ 2 representations, with evidence |
| **P4 Samplers and speed** | RQ4, RQ9 (determinism, churn), RQ10 on the shortlist | Best sampler configuration; speed and quality vs CP-SAT |
| **P5 Simulated users and learning** | Build simulated users (section 5); RQ5 | Learning curves; a recommended method |
| **P6 Hidden units** | RQ6, RQ7 | A recommendation with accuracy and regret evidence |
| **P7 Supervisor** | Build the propose → check → learn loop; RQ8 | Policies recommended, with evidence |
| **P8 Integration and weakness hunt** | The best end-to-end system (engine, learning, hidden units, supervisor) vs the v2 baseline (CP-SAT plus v2-style inverse optimization) over full simulated semesters, several users and seeds. Then attack it: craft instances and users to break it, fix it, re-run | A final comparison table and a failure-mode catalogue |
| **P9 Report** | Write `REPORT.md` (section 9) | Section 10 criteria met |

You may reorder or split phases if the evidence calls for it. Log the reason.

## 5. Simulated users

There is no real data, so learning is tested only on simulated users. Build a family of them:

- **Hidden truth:** true weights w*, a hidden state process (a Markov chain over moods such as normal, tired and motivated, which shifts weights through a true U*), true duration multipliers per area, and an energy curve over the day.
- **Living a week:** each day the user departs from Friday's plan, choosing among nearby alternatives in proportion to exp(−E_true/τ). They also skip blocks with some probability, have noisy durations, start late, and give noisy reviews.
- **Feedback:** occasional drags, chosen from local alternatives by true energy. Rankings follow a Bradley–Terry model on true energies with noise. Contradictory rankings arise naturally from mood changes.
- **Variants:**
    - easy users (stable, low noise);
    - noisy users;
    - mood-heavy users;
    - users whose true preferences include a feature **missing** from the rule library (for missing-feature detection);
    - adversarial users whose feedback is inconsistent on purpose.
- **Semester template:** realistic Cornell-style load, about 20–60 items in two weeks and 15–20 h of fixed time per week (reference §12.3).

## 6. How to work

**Session protocol**
- **Start:** read `RESEARCH_LOG.md` (status and next steps) and `git log --oneline -20`, then continue.
- **During:** log as you go and commit after every meaningful step. Run long jobs in the background, writing progress lines to a file, and check on them; don't sit and wait.
- **Before the context fills or the session ends:** update the log's Status and Next steps so a fresh session can pick up cold, then commit.

**Autonomy.** Don't stop to ask me questions. When a decision is genuinely open, pick the most reasonable default, record it as an assumption in the log, and continue. Stop only when something outside the project blocks you (permissions, missing tools). Don't build any app, UI, database or server.

**Context hygiene.**
- Never print large outputs; summarize CSVs with short scripts.
- Keep the log concise: decisions, numbers, links. Details go in each experiment's `notes.md`.
- Don't reread files you've already summarized.

**Each experiment folder** `experiments/E###-short-name/` contains:
- `README.md`: the question, hypothesis, setup and time budget, written **before** running;
- `run.py` and `config.toml`;
- `results/*.csv`;
- `figures/*.png`;
- `notes.md`: the findings, what surprised you, and what's next.

**Repo layout (suggested).**
- `pyproject.toml`.
- `src/fr/`:
    - `core/`: instances, grid, features and evaluator, checker, EDF;
    - `baseline/`: CP-SAT;
    - `engines/`: one module per representation;
    - `samplers/`, `learn/`, `sim/`, `supervisor/`.
- `tests/`, `experiments/`, `RESEARCH_LOG.md`, `REPORT.md`.

**Tools.**
- Python with numpy, numba, scipy, OR-Tools, pandas, matplotlib, pytest and hypothesis.
- cvxpy with OSQP, or scipy, for the QPs.
- JAX, PyTorch, C or Rust only if you write down why the speed is needed. Check `numba` and multi-core first.
- The laptop is the target hardware.

**Code.** Research code, but clean and readable. Clear names, short functions, comments only for why, and no AI-sounding filler. The evaluator, checker, EDF check, move-set feasibility and sampler determinism get tests, with property tests where they fit.

## 7. Rigor

- **One shared evaluator.** Every plan from every engine is scored by the same independent evaluator (stage values and per-rule totals) and the same hard-rule checker. A plan with any hard violation is invalid, whatever its energy.
- **Separate tuning from evaluation.** Tune on instance seeds 0–99; report on seeds 1000–1099, which you never tune on.
- **Statistics:** ≥ 10 seeds per cell; report median, IQR and 95% bootstrap confidence intervals; report variance, not just means.
- **Fair comparisons:** equal wall-clock budgets on the same machine.
- **Timing:** report JIT and compile time separately. Repeat timings 3× and note laptop variance (power, thermals).
- **Quality metrics:**
    - gap to the CP-SAT best or proven optimum, per stage;
    - time to reach within 0.5%, 1% and 5% of it;
    - success rate within a budget;
    - deadline-guarantee rate (must be 100% for any recommended design);
    - churn on warm replans;
    - determinism (identical output on rerun).
- **Learning metrics:**
    - weight recovery (relative error, cosine);
    - held-out ranking accuracy;
    - regret (true energy of Friday's plan minus true energy of the plan optimal under w*);
    - weeks to converge;
    - weight stability;
    - state-inference accuracy and false-attribution rate.
- **Verify surprises.** Before building on a surprising result, reproduce it with a different seed set.
- **No cherry-picking.** Report everything you ran, including what failed.

## 8. Things you should deliberately try, even if they fail

- Huge penalty weights for deadlines in a QUBO. Measure feasibility vs penalty scale and how the landscape freezes.
- A Hopfield-style energy formulation.
- An RBM trained directly on simulated lived schedules with no hand-written rules: can it learn a scheduler from data alone?
- Pure weighted stages instead of lexicographic.
- Sampling at a fixed moderate temperature with no annealing.
- Learning hidden units with no dial seeding.
- Learning weights from likelihood alone, without the supervisor.

Record why each works or doesn't. These are as valuable as the successes.

## 9. The report (`REPORT.md`, with figures in `report/figures/`)

1. **Summary and recommendation** (one page): what v3's engine should be, how much better or worse it is than v2 and in what, and the confidence of each claim.
2. **The problem and evaluation method:** brief, pointing to `ENGINE_REFERENCE.md`; the benchmark matrix and metrics.
3. **Baseline results.**
4. **Representations and hard constraints,** including the penalty-weight analysis and the deadline-guarantee evidence.
5. **Samplers and speed.**
6. **Learning.**
7. **Hidden units, and mood vs taste.**
8. **The supervisor:** feedback routing, missing features, softening walls, active queries.
9. **End-to-end semester simulations.**
10. **Dead ends:** what failed and why, with evidence.
11. **Risks, limits and open questions,** including what simulated users can't tell us.
12. **Recommended v3 engine specification,** precise enough to write a v3 design document from: state representation, energy, move set, sampler and its parameters, walls, stage handling, overload handling, learning rules, hidden units, supervisor policies, explanation method, expected performance.
13. **Appendix:** experiment index (question → folder → finding), how to reproduce, hardware.

Charts should make each comparison readable at a glance. Use the same metric names throughout.

## 10. Done when

- every phase has met its exit criteria, or is marked a justified dead end;
- every research question has an evidence-backed answer or an explicit "unresolved, because…";
- the recommended design keeps every hard guarantee at 100% across the evaluation set;
- `REPORT.md` is complete, its numbers trace to experiment folders, and a fresh reader could build v3's engine from section 12.

## 11. Start

Session 1:
1. Read `ENGINE_REFERENCE.md` and this file in full.
2. Detect the hardware.
3. Write `RESEARCH_LOG.md` with your understanding of the goal (5–10 lines), a phase plan with rough time budgets, and the first experiments.
4. Then begin P0 and P1 without waiting for me.
