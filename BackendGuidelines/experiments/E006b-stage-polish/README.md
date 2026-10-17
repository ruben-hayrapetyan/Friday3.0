# E006b — Stage handling, round 2: weighted search + capped polish (RQ3)

**Why.** E006: plain tiered annealing (wellbeing first, preferences off) leaves preferences 3x worse than a weighted energy
with ratio 1000, which matches tiered on wellbeing on 80% of instances. **Variants** (10 s each, same 20 instances as E006):
`tiered` (E006's), `tiered_eps` (tier 1 keeps preferences at weight 0.001), `weighted_1000` (E006's), `lexpolish`
(weighted 1000 for 60% of the time, then 40% polishing preferences with wellbeing capped at the value reached).
**Hypothesis.** lexpolish matches weighted_1000 on preferences and never loses wellbeing to it; tiered_eps sits between.
