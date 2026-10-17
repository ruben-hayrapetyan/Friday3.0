## 2. The problem and how engines were evaluated

The problem is the one in `ENGINE_REFERENCE.md`: place flexible items (fixed amounts, elastic ranges, weekly targets,
open-ended work) into a 14-day grid of 15-minute slots (30-minute slots from day 7), around fixed events and a protected
sleep core, under hard rules (one thing per slot, locks, windows, daily cap, minimum/maximum chunk lengths, one-sitting
items, dependencies, hard deadlines) and 18 reference soft rules in three lexicographic stages: deadlines, wellbeing,
preferences. Every engine in this study solves exactly that problem; nothing was simplified except daylight-saving
changes (a planning day is always 24 h; reference scenario 10 is therefore untested).

**One shared evaluator.** `src/fr/core/evaluate.py` scores any plan by stage and by rule in integer scaled points (100 = one
point) and `check()` lists every hard-rule violation; a plan with any violation is invalid whatever its energy. A second,
independent evaluator (`core/direct.py`, from slot arrays) agrees with it to the integer, both agree with brute force on
tiny instances, and the CP-SAT model's stage values equal the evaluator's on every plan tested. The numba energy kernel
used by the samplers is checked against the evaluator after thousands of random moves of every type
(`tests/test_kernel.py`), as are its hard-violation counts against `check()`.

**Instances.** The reference benchmark (20/40/60 flexible items, 14 days, ~15 h of fixed time a week, 3 pins, 5
dependencies); a Cornell-style semester template (46 items: classes, problem sets, readings, two prelims with prep, a
20-hour project, meals, chores, habits, a weekly goal, social evenings); stress instances (100, 150 items); and adversarial
families (tight deadlines, 1.6-2.2x overload, fragmented free time, long dependency chains, many one-sitting items, many
pins). Tuning used instance seeds 0-99; the end-to-end comparison (E017) used seeds >= 10000 and fresh user seeds, never
tuned on.

**Metrics.** Lexicographic value (late, wellbeing, preferences); per-stage gap to the best value any engine ever found on
that instance (`experiments/refs/best_known.json`), where a later stage is only compared when the earlier ones tie the
best; deadline-safe = valid and zero late work whenever zero is known to be possible (proven by CP-SAT or certified by any
valid zero-late plan); churn = hours of surviving items' work moved by a replan; determinism = identical plan on rerun.
Learning: regret (true energy of Friday's plan minus that of the plan optimised for the user's true weights and mood),
held-out ranking accuracy, weight recovery (cosine), stability, state-inference accuracy, false attribution.
Statistics: medians with IQR and 95% bootstrap confidence intervals; at least 10 seeds per cell for engine comparisons.

**Hardware and a caveat on timings.** Apple M3 Max (12 performance + 4 efficiency cores, 64 GB). From session 2 on, the
laptop was shared with a live service (load average 30-190 on 16 cores); all experiment jobs ran at `nice 19` with BLAS
threads limited to 1. Every timing comparison in this report ran engines interleaved on the same instances under the same
load, so ratios are fair, but absolute seconds are pessimistic for both v2 and v3. CP-SAT was run with 8 workers (its design).
