# E020 notes

## Round 1 (`config.toml`; results/overall.csv, by_type.csv; figures/learning_curves.png, by_type.png)

60 students (6 types x 10 seeds), ~70 tasks each, weeks 2-9 scored (weeks 0-1 are the cold start, in the curves).

| model | median abs log error | CRPS | p50 coverage | p80 coverage |
| --- | --- | --- | --- | --- |
| hier_fused_drift | 0.219 | 0.186 | 0.44 | 0.75 |
| hier_fused | 0.222 | 0.189 | 0.43 | 0.73 |
| global_bias | 0.248 | 0.218 | 0.47 | 0.79 |
| kind_bias / hier / hier_drift | 0.249-0.250 | 0.219-0.223 | 0.47 | 0.77-0.79 |
| knn | 0.264 | 0.248 | 0.48 | 0.76 |
| as_given | 0.338 | 0.290 | 0.27 | 0.55 |

- Taking estimates as given is worst for every biased type (CRPS 0.28-0.35) and ties the best only for the calibrated
  student (0.145 vs 0.143 for a global bias).
- A single personal bias multiplier already removes most of the error for optimists (0.333 -> 0.178): the planning
  fallacy is mostly one number per person.
- Fusing the estimate-ratio model with the student's own length history is the big win for noisy students (0.318 -> 0.215)
  and helps kind-biased and sparse students; it costs the calibrated student a little (0.143 -> 0.155-0.159: good
  estimates get shrunk toward history).
- Hierarchy without fusion did not beat a global bias overall (more groups, more noise at ~5 tasks per group).
- Fading memory (half-life 4 weeks) helps the drifting student (0.195 -> 0.187) and costs nothing elsewhere.
- Problem: the fused models predict too short (p50 covered only 43-44%) and too confidently (p80 covered 73-75%). Two
  causes: true lengths grow over the term (+2%/week in the simulator) and the two fused predictions share data, so
  treating them as independent overstates certainty.

## Round 2 (`config_r2.toml`; *_r2 files)

Added a term trend (a per-week slope in the length model) and online recalibration (`Recalibrated`: each recorded length
first scores the model's current prediction; the running mean error shifts medians and the running RMS of standardized
errors scales spreads, both shrunk by 5 pseudo-observations).

| model | MAE | CRPS | p50 cov | p80 cov |
| --- | --- | --- | --- | --- |
| hier_fused_drift | 0.219 | 0.186 | 0.44 | 0.75 |
| **hier_fused_drift_recal** | 0.217 | 0.187 | 0.47 | 0.80 |
| hier_fused_drift_trend | 0.219 | 0.187 | 0.46 | 0.76 |
| hier_fused_drift_trend_recal | 0.219 | 0.189 | 0.48 | 0.80 |
| global_bias_recal | 0.244 | 0.220 | 0.50 | 0.83 |

- Recalibration fixes coverage (p80 0.75 -> 0.80) at the same accuracy; the trend term adds little once memory fades.
- **Decision:** `hier_fused_drift_recal` is the default duration model. E021 tests whether calibrated quantiles matter
  downstream (missed deadlines, reserved-but-unused time), against `as_given` and `global_bias`.

## Round 3 (`config_r3.toml`; *_r3 files): population realism and "your estimate first"

Two concerns after round 2. (a) The simulator drew each student's typical lengths within 0.2 (log sd) of Friday's
population defaults, which flatters any model that leans on those defaults; real students differ more, so round 3 also
runs pop_sd = 0.5. (b) The user asked for their preliminary estimates to be the starting point, but the fused model
blends a new user's estimate with the population default from the first task (an estimate of 120 min for a problem set
became 160). `_faN` uses the estimate (times the learned ratio) until N lengths are recorded, then fuses.

| CRPS | weeks 0-1, pop_sd 0.2 | weeks 0-1, pop_sd 0.5 | weeks 2+, pop_sd 0.2 | weeks 2+, pop_sd 0.5 |
| --- | --- | --- | --- | --- |
| as_given | 0.289 | 0.298 | 0.290 | 0.301 |
| global_bias_recal | 0.275 | 0.283 | 0.220 | 0.222 |
| hier_fused_drift_recal (fuse from the start) | **0.236** | **0.255** | 0.187 | 0.191 |
| hier_fused_drift_fa3_recal | 0.267 | 0.277 | 0.187 | 0.191 |
| hier_fused_drift_fa6_recal | 0.279 | 0.286 | 0.188 | 0.191 |

- Even when the population defaults are far off (0.5), leaning on them in the first two weeks helps, because most
  students' estimates are biased low and the defaults pull them up. After two weeks the variants are identical.
- **Decision:** ship `hier_fused_drift_fa3_recal`. It honours the user's request (their estimate is the prediction until
  three lengths are recorded) at a cost confined to the first ~2 weeks (CRPS 0.267 vs 0.236). Plans still pad hard
  deadlines (p80) from day one, so the cold-start risk falls on reserved time, not deadlines. Switching to fuse from the
  start is a one-word change if the user prefers accuracy over "my numbers first".
