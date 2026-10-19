# E012 notes — an RBM trained only on lived weeks

Run: 3 easy users x 60 lived weeks (fresh Cornell-style instance each), RBM 336 visible (day x hour x {deep, other work})
-> 32 hidden, CD-1, 300 epochs on 50 weeks, 10 held out, 2026-10-17 14:31-14:33. `results/*.csv`.

| user | held-out lived weeks have lower free energy than Friday's own plan | pairwise accuracy RBM | pairwise accuracy rules (theta = 1) |
| --- | --- | --- | --- |
| 0 | 40% | 0.615 | 0.855 |
| 1 | 20% | 0.640 | 0.865 |
| 2 | 20% | 0.630 | 0.795 |

Re-ranking 16 T > 0 samples of a held-out week (true-energy regret of the pick, points, median): random pick 45.5, RBM 0.86,
rules 0.00. RBM samples (Gibbs, 500 sweeps): 64-65 hours of work per week drawn, against 68-70 in lived weeks and 97 required
over the two weeks; 0.2-0.5 h of work in the 01:00-06:00 night per sample.

## Against the hypotheses

1. **Refuted.** The RBM does not tell the user's week from Friday's: Friday's plans get *lower* free energy in 60-80% of held-out
   weeks, because lived weeks are Friday's plan plus a small personal drift, and an occupancy picture mostly learns "Friday's
   typical week".
2. **Confirmed.** Above chance (0.62-0.64) but far below the rule energy (0.80-0.87). It cannot see items, amounts, deadlines or
   chunking, so it ranks plans only by when work happens.
3. **Partly.** Used to re-rank good candidates it avoids bad picks (regret 0.9 vs 45 for random) but never beats the rules.
4. **Confirmed.** Its samples are not schedules: they ignore amounts (64 h drawn vs 97 h needed), items and fixed events, and put
   some work at night. A data-only RBM cannot be the scheduler; at most an "occupancy prior" feature inside the rule energy,
   and E011 shows the rule weights are learned faster from rankings than this prior from weeks.
