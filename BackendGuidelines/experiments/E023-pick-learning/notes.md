# E023 notes

## Round 1 (15 tuning users, 12 weeks, generator thompson+post; results/weeks_*.csv, report_r1.txt, figures/regret_by_week.png)

"feedback" = also learn from the pairs and drags of program 1 (six pairs and a drag a week); "lean 0.3" = the user takes
the recommended option outright 30% of the time (status-quo bias).

| learning | regret of the recommended | vs no learning (paired) | regret of the pick | recommended picked | cosine at end |
| --- | --- | --- | --- | --- | --- |
| none | 0.110 | | 0.098 | 68% | 0.875 |
| **picks, multinomial logit** | **0.082** | **-0.028 +- 0.007** | **0.075** | 67% | **0.904** |
| picks, rank breaking | 0.086 | -0.023 +- 0.007 | 0.077 | 60% | 0.887 |
| picks + pairs and drags (MNL) | 0.094 | -0.016 +- 0.009 | 0.083 | 63% | 0.875 |
| picks + pairs and drags (rank breaking) | 0.091 | -0.019 +- 0.009 | 0.083 | 63% | 0.854 |
| pairs and drags only (picks ignored) | 0.130 | +0.020 +- 0.012 | 0.112 | 58% | 0.859 |
| picks + pairs and drags, lean 0.3 | 0.098 | -0.012 +- 0.009 | 0.093 | 71% | 0.873 |
| pairs and drags only, lean 0.3 | 0.134 | +0.024 +- 0.012 | 0.118 | 74% | 0.832 |

- **Learning from the pick works**: picks alone cut the regret of the recommended plan by a quarter (0.110 -> 0.082)
  and of what the user lives by the same (0.098 -> 0.075), and recover the weights best (cosine 0.904).
- **Expectation wrong: pairs and drags do not add to picks.** They help users whose answers are consistent (easy,
  moody, noisy: end cosine 0.94-0.96 with them vs 0.90-0.94 without) but hurt users with a missing rule (0.93 -> 0.80)
  and adversarial users (0.85 -> 0.73), whose pairwise answers are confounded or deliberately flipped; on average picks
  alone are as good or better (-0.012 +- 0.008). Ignoring the picks and learning from pairs and drags alone is worse
  than not learning (+0.020), driven by adversarial users (pick regret 0.228 vs 0.091).
- MNL and rank breaking are close (0.082 vs 0.086).
- **"Recommended picked" again misleads**: no learning scores 68% because the alternatives, drawn from the wide prior,
  are poor plans; with learning the posterior narrows and the alternatives become real contenders.
- **A status-quo lean** slows learning (MNL + feedback: -0.016 -> -0.012) but does not bias it (cosine 0.873 vs 0.875).
- The step size per week (1 - cosine between consecutive weights) is 0.008 for picks alone vs 0.022-0.029 with pairs:
  one odd pick does not flip the recommendation.
- **Decision:** learn from picks with the multinomial logit, no pairs or drags — which is what the app as built
  collects. E025 round 2 tests that system end to end.
