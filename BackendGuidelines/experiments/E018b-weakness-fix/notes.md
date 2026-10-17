# E018b notes — fix and re-run (two rounds)

**Round 1 (`v3_fixed`, annealing first, CP-SAT only if lateness remains)**, E018's 36 instances, 2026-10-17 18:21-18:45 (background
QoS). Against the better of E018's two v3 variants per instance: as good or better on 92% (33/36); against CP-SAT-30: as good or
better on lateness on 92%.

| family | at the best known lateness: E018 v3 / E018 v3_nocp / v3_fixed |
| --- | --- |
| stress150 | 17% / 50% / **100%** |
| overload2 | 67% / 100% / 83% |
| tight one-sitting | 100% / 0% / **100%** |
| tight + 2 h chunks | 83% / 0% / **50%** |
| long dependency chain, many pins | 100% / 100% / 100% |

The budget problem on large instances is fixed (stress150: every instance at the best known lateness). The new order loses on small
packed instances (tight-bigchunk-s1/-s2: 88k and 182k vs 87k and 139k): CP-SAT hinted with an annealed plan, after the budget is
spent, does worse than CP-SAT hinted with the repaired construction at the start. The CP-SAT fallback timed out on 11/36 (all
large), succeeded and improved on 12, and was not needed on 13.

**Round 2**: order by size, implemented in `engines/api.run_v3`: instances with at most 60 items run the CP-SAT deadline solve
first (E018's order, exact on small packing), larger ones anneal first (round 1's order). Per family this takes the better
column above on every family except overload2, where the two orders differ by < 0.3% of lateness. E018c measures it.
