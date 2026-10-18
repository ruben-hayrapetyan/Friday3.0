# E022 — How to make three schedules worth choosing from (RQ14)

**Question.** Friday shows three plans; option 0 is the recommended plan (best under the learned weights). How should
options 1 and 2 be made so that (a) every option keeps the hard rules and avoidable deadlines, (b) they are clearly
different, (c) each is good for the user, and (d) the pick teaches Friday the most?

**Methods** (`src/fr/product/options.py`): seeds (re-run with other seeds), temperature (T > 0 samples around the
recommended plan), diverse (re-plan with a price on every task-slot an earlier option used), thompson (plans for two
weight vectors drawn from the learner's posterior), archetype (two named directions: "lighter" = rest dials up, "push" =
get ahead), qbc (six posterior plans; keep the pair that maximises the mutual information between the pick and the weights).

**Set-up.** `src/fr/sim/picks.py`. Simulated users from P5 (easy, noisy, moody, missing rule, adversarial), 3 per type
(tuning seeds), 10 weeks each, a fresh Cornell-style instance every week (the same sequence for every method). Each week
Friday makes three options (recommended: 300k steps; alternatives start from it with 150k steps each, so three options
cost about two plans), the user picks one by true energy with their answer noise (Bradley-Terry temperature; adversarial
users pick at random 30% of the time), lives it, and Friday learns from the pick (multinomial logit) plus the usual pairs
and drags (E011b's Bradley-Terry). Reference: the regret of the plan optimised for the user's true weights and mood.

**Metrics.** Regret (relative to |E*|) of the recommended plan, of the picked plan, and of the best of the three; how
often the user picks the recommended option; distinctness (share of work slots that differ, minimum over pairs); weight
cosine with the truth at the end; deadline safety of all three; seconds for three options.

**Expectation.** seeds and temperature give options that differ but teach little; diverse gives the most different
options at some cost in quality; thompson and qbc teach the most; archetype is the easiest to label in the app.

## Round 2 (added after round 1, before running)

Round 1: the generators barely differ in learning (end cosine 0.85-0.88) or in the regret of the pick (seeds 0.086,
thompson 0.093, qbc 0.100, archetype 0.102; diverse 0.124 and temperature 0.136 are worse). Users pick their true best
option ~90% of the time, but option 0 is that option only 23-30% of the time for seeds and thompson, below chance:
the alternatives start from the recommended plan and get extra annealing steps, so they are better plans. temperature
and diverse show the recommended plan picked 71-88% of the time only because their alternatives are worse.

Round 2 ranks the three after making them (`options.rank`): option 0 is the plan with the lowest energy under the
learned weights (map), or the highest pick probability averaged over the posterior (post). Methods thompson+map,
thompson+post, seeds+map, qbc+map; same users and weeks. **Expectation**: the recommended-picked rate rises toward the
share of weeks where the learned weights order the options correctly (> 50% for easy users), with the pick regret and
learning unchanged (the same three plans are shown, only the label moves).
