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
