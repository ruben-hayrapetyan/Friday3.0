# E009b notes — warm replans round 2: churn with weighted search + polish

Run: E009's 30 warm instances, warm start repaired first (construction from the previous plan + sampler repair), tiered vs
lexpolish at 1 s and 3 s, 2026-10-17 16:49-16:55. The previous plans were recomputed with a time-sized sampler run, so they are
not identical to E009's; comparisons with E009's CP-SAT rows are therefore approximate (same instances, different previous plans).

| warm replan | zero late | median wellbeing | median preferences | churn h, median (p90) | seconds, median (p90) |
| --- | --- | --- | --- | --- | --- |
| tiered, 1 s | 93% | 1,031 | 430,616 | 47.3 (64.0) | 0.88 (0.94) |
| **lexpolish, 1 s** | 93% | 1,169 | 177,185 | 41.5 (63.9) | 0.89 (0.94) |
| tiered, 3 s | 93% | 931 | 261,397 | 42.3 (72.0) | 2.61 (2.79) |
| **lexpolish, 3 s** | 93% | 1,094 | 137,043 | **38.6** (67.9) | 2.65 (2.85) |
| CP-SAT warm 30 s (E009) | 93% | - | - | 37.6 (62.2) | 23.7 (27.2) |

Zero late on 28/30; the other two (ref-n40-s7, -s8) are late for every engine including CP-SAT's deadline stage (pins).
With the repair step the sampler now matches CP-SAT's zero-late rate (E009 without repair: 90%).

## Findings

1. **lexpolish cuts churn by 9-12%** (47 -> 42 h at 1 s, 42 -> 39 h at 3 s) and halves preference cost against tiered, as
   predicted (minimize_changes counts during the search), at a 12-17% higher median wellbeing.
2. **Against CP-SAT-30 s (approximate pairing)** lexpolish at 3 s moves about as much work (38.6 vs 37.6 h median; less on 47%
   of instances), has better preferences on 83% and equal-or-better wellbeing on only 37%: CP-SAT's lexicographic wellbeing stage,
   given 10x the time and a good hint, still finds lower wellbeing more often.
3. **So, honestly:** for warm replans v3 is 9-27x faster (0.9-2.7 s vs 24 s) and at least as stable, and v2 at 30 s keeps an edge
   on wellbeing. Increasing `minimize_changes` for warm replans (a policy knob, untested) would lower churn further.
