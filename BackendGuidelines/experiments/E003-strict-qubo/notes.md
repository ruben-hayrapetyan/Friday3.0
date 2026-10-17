# E003 notes — strict QUBO / Hopfield (a deliberate failure, quantified)

Run: price-only slice, 6 and 10 items over 2 days (765 and 1275 binary units incl. slack bits), 10 tuning seeds each,
penalty scale alpha in {0.1 ... 1000} x P0 (P0 = largest single-unit price), T0/P0 in {0.01, 0.05, 0.2, 1}, 3M single flips
per run (about 1-3 s), 560 annealing runs + 80 greedy descents. Optimum from the staged CP-SAT on the same slice.
`results/runs.csv`, `figures/feasibility_and_gap_vs_penalty.png`, `analyze.py`.

## Results (best temperature per instance, i.e. an oracle-tuned QUBO)

| alpha | no double booking / over-placing | and no hard deadline missed | median (total - opt) / opt |
| --- | --- | --- | --- |
| 0.1 | 0% | 0% | 2.4x |
| 0.3 | 0% | 0% | 1.8x |
| 1 | 0% | 0% | 11x |
| 3 | 85% | 5% (1 of 20) | 25x |
| 10 | 85% | 0% | 86x |
| 100, 1000 | 85% | 0% | 207x |

The CP-SAT optimum misses no hard deadline on 19 of 20 instances. The QUBO misses 2-4 hard items per instance at every alpha.
A greedy single-flip descent (a Hopfield network at T = 0) is no better: 0% feasible at alpha 1, 75-80% "feasible" at alpha 10
with 4 hard items missed and a 190-200x gap.

## Hypotheses

1. **Confirmed.** Below alpha ~3 the sampler cheats on the penalties: at alpha = 1 an item gets one unit more than its amount
   (over-placing pays because the overflow price it avoids is larger than B). Below 1 it also double-books.
2. **Confirmed, and the mechanism is specific.** Above alpha ~3 the plans are "feasible" but useless, and identical across
   temperatures (the landscape is frozen). Inspection (seed 0): a hard item with need 12 sits at 9 placed units with its
   slack bits reading 3. The slack encoding of "placed <= need" turns every unplaced unit into a state with zero amount penalty,
   and leaving it needs two coordinated flips (place a unit and lower the slack), whose intermediate state costs ~alpha x P0.
   So large penalties do not guarantee deadlines; they freeze the search at whatever partial state it reached first.
3. **Confirmed.** Descent ends in such partial states.
4. **Not as feared:** the coefficient dynamic range is 80-128 on this slice, within reach of annealing hardware. The rule set
   it can hold is the real limit.

## What a strict pairwise energy cannot hold at all

Hinge measures (daily load, reserves, deep runs, even load, shortfalls), chunk starts (chunk cost, minimum chunks),
one-sitting items, dependencies and the daily cap all need helper bits or higher-order terms: each hinge needs a slack
register per measure (hundreds of measures per instance, E001: 432 at n=40), each inheriting the freezing above.
So the strict QUBO / Boltzmann machine is a dead end for this problem, by evidence on the part it can express and by
construction on the rest. The energy view survives (E004) only with walls and non-binary state.
