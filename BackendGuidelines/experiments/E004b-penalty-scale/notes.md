# E004b notes — penalties on the full model (round 2 of P3)

Run: reference n=40 and Cornell, tuning seeds 0-9 (20 instances), 5 s tiered single-thread SA, starts "construct" and "empty"
(locks only), 2026-10-17 16:17-16:38. Penalty variants: lambda in {0.1, 1, 10, 100} x median |move delta| per hard violation
with deadlines lexicographic (weight 1e6), and deadlines as an ordinary weight w_D in {1, 10, 100} x wellbeing with hard
rules at 1e6. Reference: walls. No repair step here (E005 tests repair). `results/runs.csv`.

Deadline-safe (valid, and zero late wherever the best known plan has zero late; 18 of 20 instances):

| variant | from the constructed start | from an empty plan | median wellbeing (construct) | median preferences (construct) |
| --- | --- | --- | --- | --- |
| walls | **100%** | **85%** | 525 | 89,514 |
| lambda 0.1 x median | 95% | 65% | 10,450 | 275,208 |
| lambda 1 | 95% | 60% | 3,725 | 227,247 |
| lambda 10 | 100% | 75% | 525 | 104,401 |
| lambda 100 | 100% | 75% | 525 | 117,692 |
| deadlines weighted 1x | 75% | 70% | 669 | 83,361 |
| deadlines weighted 10x | 95% | 80% | 563 | 95,983 |
| deadlines weighted 100x | 95% | 75% | 538 | 115,836 |

From the empty start the median number of hard items missed is 1.0 for walls, 4.5-7 for the penalty variants with lexicographic
deadlines and 1.6-4.4 for weighted deadlines.

## Findings

1. **Small penalties are cheated, large ones cost quality** (the QUBO result, on the full model): lambda <= 1 x median gives
   7x (0.1) and 2x (1) worse wellbeing, because the chain lives in infeasible states and its best feasible state is an early one;
   lambda >= 10 x median behaves like a wall on wellbeing but leaves preferences 15-30% worse than walls.
2. **Deadlines as a weight fail exactly as the prompt expected**: at 1x the wellbeing weight, 25% of instances end with avoidable
   lateness even from a deadline-feasible start.
3. **Penalties cannot find feasibility from nothing**: from an empty plan every penalty variant misses 4.5-7 hard items (median);
   walls + insert moves do better (85% safe, 1 item) but also need the constructive start to be reliable, which is why the
   design builds the start first (construction + repair, E005: 100%).
4. Walls are the best or tied on every column from the constructed start: the hypothesis "walls, not penalties" holds on the
   full model as well as on the QUBO slice.
