# E001 — v2 CP-SAT baseline matrix

## Question

How fast and how good is the faithful v2 engine (staged CP-SAT on the 15/30-minute grid, reference rules, allocator quotas
off) on the reference benchmark (ENGINE_REFERENCE 12.4), cold and warm, on this laptop? These numbers are what every v3
representation and sampler must beat or match at equal wall-clock budget.

## Hypotheses (written before running)

1. At 20 items every stage reaches OPTIMAL well inside the targets; at 60 items the preferences stage is time-limited
   (FEASIBLE with a visible bound gap).
2. Warm replans (previous plan as hint, +2/-1 items) are faster than cold solves and reach the same stage values or better.
3. The deadlines stage is cheap (<= 3 s) at all three sizes; wellbeing is the expensive stage because of the many
   `deep_run` windows and `reserve` measures.
4. The deadline guarantee holds: on every instance where EDF says the hard deadlines are feasible, the baseline finishes
   them with zero late work (deadlines stage value 0).
5. EDF answers in well under the 50 ms target at 100 items.

## Setup

- Instances: `reference_instance(n, seed)` for n in {20, 40, 60}, 14 days, ~15 h fixed/week, 3 pins, 5 dependencies, load 0.45
  of free time; reference rules (`REFERENCE_RULES`); seeds 0-9 (tuning range, nothing is tuned here; the report-grade run on
  seeds 1000-1099 happens once at P8 with the final configuration).
- Solver: `GridModel.solve` with `workers=8`, `random_seed=0`, per-stage deterministic limit 20 and wall share 0.4/0.3/0.3 of 30 s.
- Cold: no hint. Warm: `warm_variant` (previous plan hint + current-plan costs; 2 added, 1 removed).
- Recorded per run: stage status, CP objective, bound, gap, wall and deterministic time, build time, evaluator stage values,
  overflow hours, late hours, deadline-guarantee flag, first-solution time and objective trajectory.
- Repeat: 3 timing repeats of the cold solve for the first 3 seeds at n=60 to size laptop variance.
- Budget: <= 40 minutes of wall-clock (60 solves, mostly far under the 30 s cap).

## Reads

`results/runs.csv`, `results/traces.csv`, `results/hardware.json`, figures in `figures/`, findings in `notes.md`.
