# E018c — Weakness hunt, round 2 of the fix: order the deadline steps by instance size

**Why.** E018b: annealing-first fixes large instances, CP-SAT-first is better on small packed ones. **Change.** `run_v3` runs the
CP-SAT deadline solve first when the instance has at most 60 items, annealing first otherwise. **Setup.** E018's 36 instances.
**Hypothesis.** At the best known lateness on every family at least as often as the better of E018's v3 and E018b's v3_fixed.
