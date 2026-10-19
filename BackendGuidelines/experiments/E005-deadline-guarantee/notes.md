# E005 notes — the deadline guarantee

Run: 100 instances (6 adversarial families x 12 seeds, reference 20/40/60 and Cornell x 6, stress 100/150 x 2), tuning seeds,
2026-10-17 13:06-14:12, shared machine. Ground truth: CP-SAT deadline stage alone, 8 workers, 15 s (doubled on no solution).
`results/runs.csv`, `analyze.py`.

**Zero late possible** (CP-SAT proved 0, or some method produced a valid zero-late plan, which certifies it): 72 instances.
**Proven overload** (CP-SAT OPTIMAL > 0): 5 (all `tight`). **Unknown** (no proof either way): 23 (12 overload, 9 fragmented,
1 pins, 1 stress150).

## Results

| on the 72 zero-possible instances | zero-late rate |
| --- | --- |
| construction alone (EDF order, all hard rules) | 95.8% (69/72), median 0.7 ms, max 32 ms |
| construction + sampler repair (deadline stage, penalties) | **100%** (72/72), median 1 ms (repair needed on 3) |
| + CP-SAT fallback | 100% |
| full wall sampler from the repaired start (3 s) | **100%**, never rose above its start |
| penalty sampler from the same start | 100%, never rose (from a zero-late start a 1e6 deadline weight holds) |
| CP-SAT stage 1 alone, 15 s ("truth") | 51% |

Construction failed on 3 instances: ref60-s5 and both stress100 seeds; the sampler repair fixed all three in
under 4 s. CP-SAT alone found zero late on only 51% of the instances where zero is possible (0/12 long dependency chains, 2/11
many-pins, 0/3 stress): it times out or returns a FEASIBLE plan with heavy lateness.

**Overload** (5 proven): construction and sampler repair reach the optimum on 3/5; on tight-s3 and tight-s10 they stay
3.7x and 1.5x above it; the CP-SAT fallback (5 s, hinted with the repaired plan) reaches the proven optimum on all 5.
**Unknown instances** (no proof, mostly 1.6x overload and fragmented time): the sampler path's lateness is at or below
CP-SAT-15 s's on 20/23 (typically 2-3x lower: overload-s0 42M vs 105M); CP-SAT is better on 3 (overload-s6, fragmented-s7,
fragmented-s9).

**EDF** said "feasible" on all 5 proven-overload instances (it ignores the daily cap, chunk rules and dependencies) and never
said "infeasible" where zero late was possible: a one-directional test, as E001 found.

## Against the hypotheses

1. **Confirmed**: construction 95.8%, and repair closes the rest (100%).
2. **Confirmed**: EDF is optimistic on 5/5 proven-overload instances; construction is late on 3 EDF-feasible instances.
3. **Confirmed for walls**; for penalties it also held here because every start was already deadline-optimal for its
   protected items (E004b tests penalties from bad starts).
4. **Mostly confirmed, with a twist**: on proven overload the sampler alone is within ratio 1.0 on 3/5 and up to 3.7x worse;
   CP-SAT with the sampler's plan as hint is exact on all 5. On large or unproven overload CP-SAT alone is much worse than the
   sampler. So the right overload path is: construct -> sampler repair -> CP-SAT polish hinted with the repaired plan,
   each step keeping the better plan.

## The guarantee, as it can be stated

Walls make the guarantee *monotone*: an item that is complete and on time in the start plan can never become late. The
guarantee "never late when an on-time plan exists" then reduces to finding a zero-late start whenever one exists: construction
+ sampler repair did so on 72/72 instances (and CP-SAT fallback did too); no method can promise it in general (the problem is
NP-hard with one-sitting items and chunk minimums), so the design must keep an exact fallback and report the rare case.
