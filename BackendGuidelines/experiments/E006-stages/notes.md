# E006 notes — stages: lexicographic vs weighted vs tiered

Run: reference n=40 and Cornell, tuning seeds 0-9 (20 instances), 8 variants x 10 s, single thread, deadlines walled,
2026-10-17 14:12-14:34. `results/runs.csv`, `analyze.py`.

| variant | wellbeing worse than tiered | preferences better than tiered | median wellbeing | median preferences |
| --- | --- | --- | --- | --- |
| tiered (wellbeing, then preferences with wellbeing capped) | - | - | 575 | 126,562 |
| tiered, 5% tolerance on the cap | 50% (median +1.2%) | 60% | 525 | 114,718 |
| weighted r = 1 | 100% (median +372%) | 100% | 6,169 | 24,494 |
| weighted r = 3 | 100% (+28%) | 100% | 1,619 | 27,711 |
| weighted r = 10 | 85% (+7%) | 95% | 781 | 30,336 |
| weighted r = 30 | 45% (0%, p90 +115%) | 90% | 669 | 33,212 |
| weighted r = 100 | 30% (0%, p90 +50%) | 80% | 669 | 33,470 |
| weighted r = 1000 | 20% (0%, p90 +2.8%) | 70% | **525** | 43,741 |

(Each "worse/better" is per instance against the tiered run on the same instance; all plans valid and zero late.)

## Against the hypotheses

1. **Confirmed.** r <= 10 trades wellbeing for preferences on 85-100% of instances (a 4x worse wellbeing at r = 1).
2. **Refuted, and the surprise of P3.** r = 1000 is *not* worse on preferences; it is 3x better than tiered (43.7k vs 126.6k)
   while matching tiered's wellbeing on 80% of instances (median equal; the other 20% lose at most a few percent, p90 +2.8%).
   The tiered scheme is the weak one: tier 1 optimises wellbeing with preferences switched off, so it leaves preferences in
   a poor state that tier 2 cannot repair without raising wellbeing above the cap, and almost every useful preference move
   touches wellbeing a little. A strictly lexicographic search is a narrower search.
3. **Confirmed but small**: a 5% tolerance gives 4% better preferences for 1% worse wellbeing.

## Consequence for the design (and a round-2 experiment)

The stage policy should be "lexicographic in effect, weighted in search": anneal one energy with ratio ~1000 between
stages (deadlines walled), then polish preferences with wellbeing capped at the value reached. That keeps the
lexicographic guarantee for wellbeing at the end (the polish can only lower preferences) while searching like a weighted
sum. E006b measures it against tiered and pure weighted-1000 on the same instances. E004/E007-E009 used the plain tiered
scheme, so their absolute preference values understate the sampler; comparisons inside each experiment are unaffected.
