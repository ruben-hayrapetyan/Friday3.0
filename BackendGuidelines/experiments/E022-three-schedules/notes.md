# E022 notes

## Round 1 (tuning users, 5 kinds x 3, 10 weeks; results/weeks_r1_*.csv, report_r1.txt)

| method | regret of the recommended | regret of the pick | best of three | recommended picked | distinct | cosine at end | s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seeds | 0.140 | **0.086** | 0.081 | 33% | 0.72 | 0.858 | 1.7 |
| thompson | 0.135 | 0.093 | 0.087 | 27% | 0.42 | 0.852 | 1.4 |
| qbc | **0.114** | 0.100 | 0.098 | 37% | 0.31 | 0.859 | 1.8 |
| archetype | 0.137 | 0.102 | 0.097 | 21% | 0.40 | 0.849 | 1.4 |
| diverse | 0.136 | 0.124 | 0.120 | 71% | 0.87 | 0.878 | 1.2 |
| temperature | 0.139 | 0.136 | 0.131 | 88% | 0.69 | 0.858 | 1.2 |

Paired by user-week, pick regret minus thompson's: seeds -0.007 +- 0.009, qbc +0.008, archetype +0.009, diverse
+0.031 +- 0.010, temperature +0.043 +- 0.010. Every option kept every avoidable deadline in every week (safe = 1.0).

- **Learning does not depend on the generator** over 10 weeks: end cosines 0.85-0.88 for all. By user kind the cosine
  rises for easy (0.91 -> 0.96), moody (0.87 -> 0.92) and noisy users (0.85 -> 0.89) and falls for the missing-rule
  (0.88 -> 0.81) and adversarial users (0.88 -> 0.72), as for pairs in program 1 (E011).
- **The pick is good when the alternatives are good**: users pick their truly best option ~90% of the time, so the
  regret of the pick is the regret of the best of three. seeds, thompson, qbc and archetype give the user a better plan
  than the recommended one by 0.03-0.05 of |E*|; diverse and temperature alternatives are worse plans.
- **The "recommended picked" rate is misleading on its own**: temperature (88%) and diverse (71%) score high because
  their alternatives are worse, not because Friday predicts the pick. For seeds and thompson the recommended plan is
  the user's best only 23-30% of the time, *below* chance: the alternatives start from it and get 150k more annealing
  steps, so they are simply better optimised. The user asked that the recommended option become the one they pick;
  round 2 fixes the label by ranking the three after making them.
- seeds is as good as thompson here and more distinct (0.72 vs 0.42), but costs three full plans and its options have
  no meaning to show ("seed 2"); thompson's options are each optimal for a plausible version of the user, which the
  app describes rule by rule.
