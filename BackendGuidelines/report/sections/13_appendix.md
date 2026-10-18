## 13. Appendix

### 13.1 Experiment index

| id | question | folder | finding (one line) |
| --- | --- | --- | --- |
| E001 | How fast and good is faithful v2? | `experiments/E001-v2-baseline` | Misses every speed target (cold p90 20-31 s, warm p90 18-26 s); preferences never proven optimal; not deterministic with 8 workers |
| E002 | Can v2 work at 10 s with fair tuning? | `E002-baseline-tuning` | No: times out or hundreds of late hours in every variant; fair baseline = 30 s |
| E003 | Strict QUBO / Hopfield with penalties | `E003-strict-qubo` | Dead end: 0-5% deadline-safe at any penalty scale; cheats or freezes |
| E004 | Representations on equal budgets | `E004-representations` | Walls: 100% valid and deadline-safe, best quality at 7 s; CP-SAT-30 s 30% deadline-safe under load |
| E004b | Penalty scale on the full model | `E004b-penalty-scale` | Penalties cheat (small) or cost 15-30% preferences (large); deadlines as weights leave avoidable lateness on 25% |
| E005 | Deadline guarantee | `E005-deadline-guarantee` | Construction + sampler repair: zero late on 72/72 where possible (CP-SAT alone 51%); CP-SAT fallback exact on proven overload |
| E006 | Stages: lexicographic vs weighted vs tiered | `E006-stages` | Weighted 1000:1 matches tiered wellbeing on 80% with 3x better preferences |
| E006b | Weighted search + capped polish | `E006b-stage-polish` | lexpolish: preferences 2.3x better than tiered at the same median wellbeing |
| E007 | Samplers on equal wall clock | `E007-samplers` | 8-core multi-start ~ PT ~ population annealing, best; PT on 1 core worst; heat-bath = Metropolis |
| E008 | Which moves matter | `E008-move-ablation` | split essential; insert/drop/shrink essential for elastic/target/open items |
| E009 | Warm replans, churn, determinism | `E009-warm-determinism` | Warm 0.4-2.3 s vs CP-SAT 24 s; identical reruns with a fixed step budget; CP-SAT-30 better on quality and churn |
| E009b | Warm churn with lexpolish | `E009b-warm-churn` | Churn down 9-12% to CP-SAT-30's level; zero late equal to CP-SAT with the repair step |
| E010 | Diversity and calibration | `E010-diversity-calibration` | Samples diverse; calibrated when T matches the user's noise; walls make the chain reach only ~20% of tiny valid sets |
| E011 | Which weight learner | `E011-learning` | QP fastest on consistent users but bends to noise; drags cleanest; CD alone weak |
| E011b | Bradley-Terry likelihood | `E011b-learning-round2` | BT best on average and on adversarial users; replicates vary by up to 0.1 |
| E011c | Fitted answer temperature | `E011c-learning-round3` | Detects noise (0.08 vs 0.18-0.5); used for policies, not the fit |
| E012 | RBM from lived weeks only | `E012-rbm-from-data` | Dead end: 0.62-0.64 ranking accuracy vs 0.80-0.87; samples are not schedules |
| E013 | Hidden units, mood vs taste | `E013-hidden-units` | Seeded units help moody users, cost the rest; state-vs-noise test right for 8/9 users |
| E013b | Gate units per user | `E013b-gated-units` | Naive gate fails (units win by softening predictions) |
| E013c | Gate vs a calibrated baseline | `E013c-gate-vs-temperature` | Safe for mood-free users; keeps a quarter of the gain for moody users |
| E014 | Missing-feature detection | `E014-missing-features` | Right rule for 6/6 by week 4; false proposals 33% -> 0% by week 10; propose, add on yes |
| E015 | Softening walls | `E015-soften-walls` | Ask once at the first contradicting event; never soften silently |
| E016 | Active querying | `E016-active-queries` | QBC/uncertainty halve the questions for consistent users; noisy users: asking hurts |
| E017 | End-to-end semesters, v3 vs v2 | `E017-semesters` | Report seeds: v3 0 misses / 0 invalid in 288 plans, 1.3 s vs 19.8 s, lower regret in 144/144 weeks |
| E018 | Weakness hunt | `E018-weakness-hunt` | v3 deadline-safe 36/36 (CP-SAT 64%); two v3 failures found (packing without CP-SAT; fallback eating the budget) |
| E018b | Fix: anneal before CP-SAT | `E018b-weakness-fix` | 150 items fixed (5/6 at best lateness); small packed instances worse |
| E018c | Fix: order by size | `E018c-size-rule` | keeps both gains; tight 2 h-chunk packing still behind CP-SAT-30 |
| E018d | The fallback's time | `E018d-fallback-time` | 5 s on efficiency cores: 3/6 at best (P-cores: 5/6) |
| E019 | Constraints from text (program 2) | `E019-constraint-parsing` | Sonnet 5.5 + guide v2 + structured output: 99.0% of held-out texts fully right (3 runs); no guide 87.9% |
| E020 | Duration models | `E020-duration-models` | Hierarchical fused + fading memory + recalibration: CRPS 0.187 vs 0.290 as given; user's estimate first until 3 recordings |
| E021 | Durations downstream | `E021-durations-downstream` | Learning cuts hard misses 2-4x; p95 for hard deadlines: 4.3% late for 23 min/day unused |
| E022 | Three schedules | `E022-three-schedules` | Thompson alternatives ranked by posterior pick probability: recommended picked 63% (from 27%), lived regret unchanged |
| E023 | Learning from the pick | `E023-pick-learning` | Picks alone (MNL): -25% regret; adding pairs and drags hurts missing-rule and adversarial users |
| E024 | When to ask | `E024-asking-policy` | Two "how long did it take?" a week: misses 2.9% -> 0.2% at p95; estimates only trade padding |
| E025 | The whole loop | `E025-end-to-end` | As shipped vs v3 as built: hard misses 8.8% vs 67.5%, habit conflicts 0.08 vs 7.8 h/week |

### 13.2 How to reproduce

```
cd BackendGuidelines
uv sync                                  # Python 3.12, numpy, numba, OR-Tools 9.15, scipy, cvxpy, pandas, matplotlib
uv run pytest                            # 195 tests: evaluator, checker, EDF, kernel exactness, walls, determinism, learning, product
cd experiments/E004-representations && uv run python run.py && uv run python analyze.py   # any experiment the same way
uv run python report/make_figures.py     # rebuilds report/figures from the results
```

Every experiment folder has `README.md` (written before running), `config.toml`, `run.py` (`--smoke` for a 1-instance check,
`--shard=i/n` where the user loop is long), `results/*.csv`, `analyze.py`, `notes.md`. `experiments/refs/best_known.json` holds the
best valid value any engine found per instance (all gaps are measured against it). Seeds: instances 0-99 for tuning, 10000+
(and users 20000+) for the end-to-end evaluation. Order matters: OR-Tools must be imported before cvxpy (both bundle HiGHS;
`fr/__init__.py` takes care of it).

### 13.3 Hardware

Apple M3 Max, 16 cores (12 performance, 4 efficiency), 64 GB RAM, macOS 26.6, Python 3.12 via uv, numba 0.68, OR-Tools 9.15.
Session 1 ran on an idle machine (E001); from session 2 the machine was shared with a live service (load average 10-190), all
jobs at `nice 19`, BLAS/OpenMP threads at 1 (see section 2 on what that means for timings).
