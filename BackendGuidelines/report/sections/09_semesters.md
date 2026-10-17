## 9. End-to-end semester simulations (P8)

**E017 (report seeds only: instances 10000+, users 20000+; 4 user types x 3 users x 12 weeks).** Each system keeps its own
trajectory: it plans the week, the simulated user lives it, drags, answers six comparisons (chosen by the system), picks a pace
in 30% of non-normal weeks, and the system learns.

| | **v3** (recommended) | v3_lex (v3 with lexicographic stages) | **v2** (staged CP-SAT 30 s + drags-only learning + paces) |
| --- | --- | --- | --- |
| weeks with a hard deadline missed | **0 / 144** | 0 / 144 | 3 / 144 (9 items late) |
| plans breaking a hard rule | **0 / 144** | 0 / 144 | 2 / 144 |
| plan time, median (p90) | 1.3 s (2.9 s) | 0.8 s (1.5 s) | 19.8 s (29.3 s) |
| relative regret, median | **0.087** | 1.62 | 6.13 |
| weeks with lower regret than v2 | 144 / 144 | 112 / 144 | - |
| learned-weight cosine with the truth | 0.955 | 0.939 | 0.866 |
| missing-feature users given the right rule | 3 / 3 | 3 / 3 | cannot |
| users given a wrong rule | 0 (false proposals refused) | 0 | - |

The simulated users' utility is a weighted sum without stage order, so lexicographic planning carries a built-in regret: v3 vs
v3_lex (0.087 vs 1.62) measures the stage policy, v3_lex vs v2 (1.62 vs 6.13, better in 78% of weeks) measures the engine under the
same policy. Both levers favour v3; the stage policy is the larger one and is a product decision (section 1).

v2's misses came from CP-SAT's deadline stage stopping at FEASIBLE within 30 s on one user's weeks (4-5 hard items late); its
invalid plans came from the lock repair on a partially pinned one-sitting item. v3's construction + walls met every deadline
in all 288 v3 plans. Hidden units never switched on by themselves in 12 weeks (the calibrated gate is slow); moody users were
helped in the weeks they picked a pace, and their regret (0.070) stayed close to consistent users' (0.057). The supervisor asked
on average 0.3-2 rule questions per user over the semester and never added a wrong rule.

![Semester regret](report/figures/semester_regret.png)

**Weakness hunt (E018, E018b-d).** Six adversarial families x 6 seeds, built to break one assumption each. All plans from every
engine were valid. v3 was deadline-safe on every instance; CP-SAT-30 s on 64% (it found no deadline-feasible plan on any
30-item dependency chain or 40-pin instance, and missed 67 hard items on median at 150 items). The hunt broke v3 twice and
both were fixed and re-run:

| failure | evidence | fix |
| --- | --- | --- |
| Without CP-SAT the sampler stays 2-6x later than the optimum on tight one-sitting packing (coordinated moves of whole one-sitting items are rarely accepted under walls) | E018: at best lateness 0/6 vs CP-SAT 6/6 | keep the exact CP-SAT deadline fallback |
| The fallback ran before annealing and on 150 items ate the whole budget, improving nothing | E018: 150 items at best lateness 1/6 (v3) vs 3/6 without CP-SAT | anneal first on large instances: 5/6 (E018b) |
| Annealing first loses on small packed instances | E018b: tight + 2 h chunks 3/6 vs 5/6 | order by size: CP-SAT first up to 60 items (E018c-d) |

**What still stands against v3:** tight overload packing with 2-hour minimum chunks, where CP-SAT at 30 s on 8 performance cores
reaches the best lateness on 6/6 and v3's 5 s fallback on efficiency cores on 3/6 (1-21% more lateness on the others; 5/6 when
the same path ran on performance cores). In an overload week a longer fallback (10-30 s) is acceptable and closes most of it.
