# E008 notes — which moves matter

Run: geometric SA, tiered stages, 4 s, reference n=40 and Cornell, tuning seeds 0-9 (20 instances), all 11 moves vs each
removed in turn vs a minimal set (shift, far, insert, drop), 2026-10-17 15:16-15:30. Paired against "all" per instance.

| variant | worse than all moves | better | median wellbeing change | median preferences change (when wellbeing ties) |
| --- | --- | --- | --- | --- |
| minimal (shift, far, insert, drop) | **100%** | 0% | **+810%** | - |
| no split | **100%** | 0% | +209% | - |
| no shrink | 90% | 10% | +5% | +268% |
| no drop | 80% | 20% | 0 | +672% |
| no insert | 75% | 25% | 0 | **+3711%** |
| no far shift | 70% | 30% | 0 | +27% |
| no swap | 65% | 35% | 0 | +30% |
| no transfer | 60% | 40% | 0 | -10% |
| no eject | 55% | 45% | 0 | +0.7% |
| no merge | 55% | 45% | 0 | +5% |
| no grow | 45% | 55% | 0 | -11% |
| no shift (1-4 slots) | 40% | 60% | 0 | -9% |

All plans valid in every variant (walls hold whatever the move set).

## Against the hypotheses

1. **Confirmed for split, refined for far.** Without split (cut a legal-size piece off a chunk and move it) wellbeing is 3x worse on
   every instance: it is the move that breaks long runs into pieces that respect minimum chunk lengths, which walls otherwise
   forbid one slot at a time. Far shift matters for preferences (+27%) more than for wellbeing.
2. **Partly.** Merge, eject and transfer are near-neutral at 4 s; swap is not (+30% preferences without it).
3. **Confirmed strongly.** The minimal set is 9x worse on wellbeing: chunk-reshaping moves are what make walls workable.
4. **New:** the amount-changing moves are essential for preferences: elastic, target and open items start empty (construction
   only places fixed amounts), so without insert the sampler cannot give them time at all (+3711%), and without drop/shrink
   it cannot take time back.
5. Small shifts are redundant with far shifts and relocations: removing them is slightly better (the budget goes to other moves).

**Move set recommended:** split, shrink, grow, drop, insert, far shift, swap, plus transfer/merge/eject at low probability
(neutral here, cheap insurance for chunk-heavy and packed instances, E018); small shifts at reduced probability.
