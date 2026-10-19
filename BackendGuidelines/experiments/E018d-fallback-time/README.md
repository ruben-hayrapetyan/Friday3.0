# E018d — The deadline fallback's time

**Why.** E018c's small-instance path (CP-SAT first) was worse on tight + 2 h chunks than E018's identical path. Two differences:
E018's tight families ran on performance cores (before the run was moved to background QoS), E018c's on efficiency cores; and
`ensure_deadlines` passed its 5 s as the *total* limit, so the deadline stage (40% share) got 2 s. **Change.** The deadline stage
now gets the full 5 s. **Setup.** The two tight families (12 instances), background QoS as in E018c. **Hypothesis.** With 5 s
the CP-SAT-first path reaches the best known lateness on tight families again.
