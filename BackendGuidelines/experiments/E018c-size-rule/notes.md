# E018c / E018d notes — ordering the deadline steps by size, and the fallback's time

E018c (36 instances, 2026-10-17 18:46-19:08, background QoS = efficiency cores): `run_v3` with CP-SAT first for <= 60 items.
E018d (the 12 tight instances, 19:09-19:13, same QoS): the same, with the deadline stage given its full 5 s (a bug had passed
5 s as the total limit, so the deadline stage got 2 s; this also applied to E005's fallback, which nevertheless reached the
proven optimum on 5/5).

Share of instances at the best known lateness (all engines valid and deadline-safe on every instance here):

| family | CP-SAT 30 s | E018 v3 (CP-SAT first, P-cores) | E018b annealing first | E018c size rule, 2 s | E018d size rule, 5 s |
| --- | --- | --- | --- | --- | --- |
| tight one-sitting | 100% | 100% | 100% | 100% | 100% |
| tight + 2 h chunks | **100%** | 83% | 50% | 0% | 50% |
| long dependency chain | 0% | 100% | 100% | 100% | - |
| 40 pins | 0% | 100% | 100% | 100% | - |
| 2.2x overload | 0% | 67% | 83% | 67% | - |
| 150 items | 0% | 17% | 83% | 83% | - |

## Findings

- The size rule keeps annealing-first's gains on 150 items (83% vs 17%) and CP-SAT-first's exactness on tight one-sitting packing.
- **Remaining weakness: tight packing with 2-hour minimum chunks.** v2's CP-SAT at 30 s (8 performance cores) reaches the best
  lateness on 6/6; v3's 5 s deadline fallback on efficiency cores on 3/6 (others 1-21% later: 105k vs 87k, 163k vs 139k, 323k vs
  241k points). E018 ran the same CP-SAT-first path on performance cores and matched CP-SAT on 5/6. So on small, densely packed
  overload instances the exact fallback needs its seconds on fast cores; the user is already in an overload week, so a 10-30 s
  fallback there is an acceptable product choice. This is the one family where v2 at 30 s stays ahead.
- Overload with 30 items prefers annealing first (83-100% vs 67%): the size threshold of 60 items is a heuristic, not tuned.
