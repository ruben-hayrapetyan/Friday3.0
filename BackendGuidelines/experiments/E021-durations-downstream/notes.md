# E021 notes

## Round 1 (report seeds, 24 students, 8 weeks, load 1.5; results/runs_r1_*.csv, report_r1.txt)

| model @ p50 flexible / p80 hard | hard tasks late | hours late (sum) | readings late | unused reserved h/day |
| --- | --- | --- | --- | --- |
| oracle (true lengths) | 0.0% | 0 | 35% | 0.13 |
| global_bias_recal | **10.9%** | 89 | 64% | 1.42 |
| hier_fused_drift_recal | 14.5% | 113 | 62% | 1.25 |
| as_given | 36.5% | 262 | 75% | 1.08 |

By student type (hard late): as_given is best only for the calibrated student (5.4% vs 10-12%); it misses 54-64% for
optimists and kind-biased students, where learning cuts misses 4-5x.

- Learning lengths is worth it downstream: misses fall from 36.5% to 11-15%.
- **The ranking flips against E020**: the global bias model misses fewer deadlines than the hierarchical one although
  it predicts worse (CRPS 0.22 vs 0.19). Its spreads are wider (p80 covered 83% vs 80%), so hard deadlines get more
  padding; what matters downstream is the tail of the prediction, not its accuracy. Round 2 therefore compares the
  models along a frontier (misses vs unused reserved time) instead of at one quantile, and includes global_bias_recal.
- Readings (soft deadlines, p50) are late often even with true lengths (35%): the planner trades soft lateness against
  wellbeing; not a duration question.
- Calibrated students lose with any learned model at p80 (5% -> 10-12%): with good estimates, the fixed 0.35 spread of
  as_given is the larger padding.

## Round 2 (frontier; report seeds, 24 students; results/runs_r2*_*.csv, report_r2.txt, figures/frontier.png)

Flexible tasks at p50 throughout; the hard-deadline quantile varies.

| model | p50 | p80 | p90 | p95 |
| --- | --- | --- | --- | --- |
| as_given: late / unused h/day | 67.9% / 0.64 | 36.5% / 1.08 | 20.5% / 1.31 | 9.8% / 1.49 |
| global_bias_recal | 41.9% / 0.91 | 10.9% / 1.42 | 5.6% / 1.62 | 3.6% / 1.84 |
| hier_fused_drift_fa3_recal | 46.8% / 0.79 | 15.1% / 1.18 | 8.4% / 1.49 | **4.3% / 1.57** |

- **On the frontier the hierarchical model wins after all**: at equal unused time it misses fewer deadlines at every
  point (1.57 h/day: 4.3% vs ~7% interpolated for the global model; 1.18 h/day: 15% vs ~25%). Round 1 compared the
  models at the same quantile, where the global model's wider spreads simply bought more padding. E020's choice stands.
- **The quantile matters more than the model**: p80 -> p95 cuts hard-deadline misses from 15.1% to 4.3% and hours late
  from 116 to 34, for 0.39 more reserved-but-unused hours a day (about 23 minutes). A missed hard deadline costs far
  more than 23 minutes of slack, so **the product plans hard deadlines at p95** (`service.Q_HARD`).
- Per type at p95 the model misses 3.0-6.2% (calibrated 3.0%, drifting 6.2%); as_given at p95 misses 0% for the
  calibrated student but 24% for the kind-biased one.
- Readings (p50) stay late 59-63% for every learned model; that is a planner trade-off with wellbeing (oracle: 35%).
