# E018b — Weakness hunt, fix and re-run

**Why.** E018's v3 pipeline ran the CP-SAT deadline fallback *before* annealing. On 150-item instances the fallback used the
whole budget (25-28 s) without reducing lateness, and the annealing that would have reduced it never ran (v3_nocp, which skipped
CP-SAT, ended 7x less late on stress-n150-s1). **Fix** (`engines/api.run_v3`): construction -> sampler repair -> wall sampler
(lexpolish) for the budget -> only if lateness is left, CP-SAT's deadline stage hinted with that plan -> short polish of the less
late plan. **Setup.** E018's 36 instances, same seeds, 10 s budget; compared with E018's three engines (CP-SAT rows reused).
**Hypothesis.** The fixed pipeline is never later than either E018 variant, and is the least late on stress and overload.
