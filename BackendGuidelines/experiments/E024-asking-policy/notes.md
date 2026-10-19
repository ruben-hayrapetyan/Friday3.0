# E024 notes

## Round 1 (p80 for hard deadlines; tuning seeds, 18 sparse students; results/runs_r1_*.csv, report_r1.txt)

| asks for | questions / week | hard tasks late | change vs never (paired) | hours late | unused h/day |
| --- | --- | --- | --- | --- | --- |
| nothing | 0 | 12.5% | | 54.6 | 1.89 |
| estimates, always | 6.1 | 17.0% | +4.5 +- 1.6 | 89.3 | 1.61 |
| estimates, spread >= 0.45 | 4.4 | 17.0% | +4.5 +- 1.3 | 83.7 | 1.62 |
| estimates, voi30 | 3.1 | 15.0% | +2.5 +- 0.9 | 70.1 | 1.63 |
| estimates, voi60 | 2.3 | 13.2% | +0.7 +- 0.7 | 51.7 | 1.71 |
| actual lengths, always | 3.8 | **8.4%** | **-4.1 +- 1.1** | 30.7 | 1.78 |
| actual lengths, 2 a week | 2.0 | 11.2% | -1.3 +- 1.1 | 40.1 | 1.80 |

- **Expectation wrong**: asking for estimates *raised* misses, by more the more Friday asked. An estimate narrows the
  prediction, so the p80 padding shrinks (unused time falls 1.89 -> 1.61 h/day): estimates move along the padding
  frontier rather than improving it.
- **Why the move is a bad one**: a coverage check (scratch script, same students, p_record 0.5) shows the shipped model's
  p80 covers 82% of tasks without an estimate but only 74% once every task has one (z-score mean +0.14, sd 1.05):
  the fused prediction treats the ratio and length predictions as independent, and early on the ratio correction is
  shrunk toward the (optimistic) estimate. Without fusion (hier_drift_recal) coverage is 79%. A correlation-aware
  fusion is a follow-up for E020, not done here.
- **Actual lengths help**: asking for the length of every unrecorded finished task cuts misses by a third for ~4
  questions a week; two a week gives a third of that gain. This matches the user's own phrasing ("ask me for more
  assignment lengths").
- Round 2 repeats the comparison at p95, the quantile the product now uses.

Scratch follow-up (same coverage check): fusing with an assumed error correlation rho between the ratio and length
predictions (`durations.make("..._rhoN_recal")`, rho = N/10) moves p80 coverage with every estimate given from 74% to
76% (rho 0.5) and 78% (rho 0.7); p95 coverage is 94-96% for all. Part of the gap is a median bias (z mean +0.14) from
the ratio prior shrinking toward the optimistic estimate. Not adopted: small gain, and at p95 coverage is near nominal.

## Round 2 (p95 for hard deadlines; same 18 students; results/runs_r2_*.csv, report_r2.txt)

| asks for | questions / week | hard tasks late | change vs never (paired) | hours late | unused h/day (paired change) |
| --- | --- | --- | --- | --- | --- |
| nothing | 0 | 2.9% | | 14.9 | 2.42 |
| estimates, always | 6.1 | 3.9% | +1.0 +- 0.8 | 14.0 | 2.06 (-0.36 +- 0.10) |
| estimates, voi60 | 3.1 | 3.4% | +0.5 +- 0.8 | 13.3 | 2.07 (-0.35 +- 0.12) |
| actual lengths, always | 3.8 | 0.4% | -2.5 +- 0.9 | 0.9 | 2.35 (-0.07) |
| **actual lengths, 2 a week** | 2.0 | **0.2%** | **-2.7 +- 1.0** | 0.5 | 2.27 (-0.15 +- 0.08) |
| actual lengths, 4 a week | 3.1 | 0.2% | -2.7 +- 1.0 | 0.6 | 2.33 (-0.10) |

- At p95 the sparse students miss 2.9% of hard deadlines with no questions at all (12.5% at p80): the quantile does
  most of the work.
- **Asking for actual lengths nearly removes the rest**: two questions a week take misses to 0.2% and hours late from
  15 to 0.5 per term; more questions add nothing.
- **Asking for estimates is now a padding trade, not a loss**: voi60 frees 0.35 h/day of reserved time (21 minutes)
  for +0.5 points of misses (not significant), with half the questions of "always".
- **Decision:** ask for at most two actual lengths a week (`service.ACTUALS_PER_WEEK`), and keep the voi60 rule for
  estimates (`service.ASK_SAVING`, padding measured at p95). The combination is tested end to end in E025.
