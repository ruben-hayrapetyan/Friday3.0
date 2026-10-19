# E002 — Tune the v2 baseline fairly

**Question.** E001 showed the faithful v2 CP-SAT model misses its own speed targets. Before any v3 candidate is compared with
it, how good can the baseline get at a fixed 10 s cold budget (the reference's cold p90 target) with sensible changes that
keep its design (staged lexicographic CP-SAT on a slot grid)? A weak baseline would flatter v3.

**Variants (all 10 s total, same 10 instances: reference n=40, seeds 0-9, tuning seeds only):**

| id | change | reason |
| --- | --- | --- |
| A | none (8 workers, fine_days 7, horizon 14, shares 0.4/0.3/0.3) | control |
| B | fine_days 3 (coarse 30-min slots from day 3) | smaller model |
| C | horizon 10 days | smaller model |
| D | 1 worker | determinism (reference scenario 20) |
| E | hint = EDF-style constructive plan (my `construct`) | better start; a v3 idea lent to the baseline |
| F | stage shares 0.2/0.3/0.5 | give preferences more time |

All plans are mapped onto the control grid (`core/remap.py`) and scored by the shared evaluator and checker, so grid changes
are compared fairly (a plan that is hard-invalid after mapping counts as invalid).

**Hypotheses.** (1) B and C cut the model enough to reach zero late work in 10 s more often than A. (2) E helps most, since the
first deadline-feasible solution is the slow part (E001: 2.4-5 s). (3) D is clearly worse in quality. (4) F trades wellbeing for
preferences without helping the lexicographic value.

**Metrics.** zero-late rate; lexicographic value (late, wellbeing, preferences) vs the best known for the instance; total time;
hard violations after mapping. 10 instances x 6 variants x 10 s ~= 10 min.
