# E006 — Stages: lexicographic vs weighted vs tiered annealing (RQ3)

**Question.** v2 solves deadlines, then wellbeing, then preferences, each frozen before the next. An energy sampler can do the
same with tiers (anneal wellbeing, then anneal preferences with wellbeing capped) or simply anneal one weighted sum
`r * wellbeing + preferences`. How often, and by how much, do weighted versions disagree with the lexicographic answer? Is
there a ratio r that never disagrees but still finds good preferences? Does a small tolerance on the wellbeing cap buy much?

**Setup.** Deadlines are a wall in every variant (E005). Reference n=40 and Cornell, tuning seeds 0-9 (20 instances), 10 s per run,
same sampler and moves. Variants: `tiered` (cap = tier-1 wellbeing), `tiered_tol5` (cap = 1.05 x tier-1 wellbeing),
`weighted_r` for r in {1, 3, 10, 30, 100, 1000}. Reference = the tiered result on the same instance and the best known lexicographic
value from E004.

**Hypotheses.** (1) r <= 10 disagrees on most instances (wellbeing traded for preferences). (2) r >= 1000 agrees on wellbeing but
its preferences are worse than tiered, since the temperature that resolves wellbeing barriers is too hot for preferences
(the same freezing as E003, milder). (3) A 5% tolerance gives a few percent better preferences for a small wellbeing loss: a
policy dial, not a free win.
