# E006b notes — stage handling round 2: weighted search + capped polish

Run: E006's 20 instances, 10 s each, 4 variants, 2026-10-17 16:39-16:49. `results/runs.csv`.

| variant | median wellbeing | median preferences | wellbeing worse than tiered (p90 change) | preferences better than tiered |
| --- | --- | --- | --- | --- |
| tiered (E006's scheme) | 512.5 | 79,829 | - | - |
| tiered, preferences at weight 0.001 in tier 1 | 525 | 36,535 | 45% (+18.5%) | 85% |
| weighted 1000:1 | 512.5 | 43,004 | 15% (+1.1%) | 60% |
| **lexpolish** (60% weighted 1000:1, then 40% preference polish under a wellbeing cap) | **512.5** | **34,694** | 20% (+5.5%) | **95%** |

lexpolish has better preferences than weighted-1000 on 95% of instances and better than tiered on 95%, with the same median
wellbeing; its wellbeing is at least as good as weighted-1000's on 65% (its weighted phase is shorter).

## Findings

- Confirmed: the polish phase converts the weighted search's head start into a 2.3x preference improvement over strictly
  tiered annealing (34.7k vs 79.8k median) and 19% over the pure weighted search, at the cost of a few percent of wellbeing on a
  fifth of the instances.
- Even a tiny preference weight in tier 1 (0.001) recovers most of the loss of strictly tiered search (36.5k) but costs
  wellbeing more often (45%, p90 +18.5%).
- **Recommended stage policy: lexpolish.** For a product that promises "wellbeing first", the polish cap guarantees the final
  plan's wellbeing is the value the search reached; the residual risk is that the weighted search reached a slightly worse
  wellbeing than a pure wellbeing search would have (median 0, p90 +5.5%).
