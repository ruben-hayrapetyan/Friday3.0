# E009b — Warm replans, round 2: churn with the weighted-then-polish stage scheme

**Why.** E009: warm sampler plans moved more work than CP-SAT warm (44 vs 38 h median), because tiered annealing switches
`minimize_changes` (a preference) off while it optimises wellbeing. **Change.** The E006 "lexpolish" scheme (weighted search
1000:1, then a preference polish under a wellbeing cap) keeps `minimize_changes` active throughout; the start is repaired first
(construction from the previous plan, then sampler repair if late). **Setup.** E009's 30 warm instances and previous plans;
warm sampler with tiered vs lexpolish at 1 s and 3 s. **Hypothesis.** lexpolish halves churn and improves preferences.
