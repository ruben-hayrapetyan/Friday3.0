# E001 notes — v2 CP-SAT baseline

Run: 69 solves (n = 20/40/60, seeds 0-9, cold + warm, plus 9 timing repeats), Apple M3 Max, 8 workers, 30 s budget per solve
(stage shares 0.4/0.3/0.3). Tuning seeds only; nothing here is a report number. `results/runs.csv`, `figures/`, `analyze.py`.
This was the third full run; the first two exposed bugs (below), their partial output is not used.

## Results against the hypotheses

| # | Hypothesis | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | 20 items: every stage OPTIMAL; 60 items: preferences time-limited | **Wrong at 20.** Preferences is never OPTIMAL at any size (0/30) | Preferences hits its 9 s limit with a median bound gap of 63% (n=20), 88% (n=40), 94% (n=60). Wellbeing is optimal 100% / 30% / 10% |
| 2 | Warm is faster and no worse | **Partly.** Faster by 10-15%, nowhere near the target | Total median cold -> warm: 18.3 -> 16.5 s (20), 26.5 -> 23.2 s (40), 29.3 -> 24.9 s (60). Quality: the warm preferences gap is lower at 40/60 |
| 3 | Deadlines stage <= 3 s at all sizes; wellbeing is the expensive stage | **Wrong.** Deadlines is 4.1 / 7.8 / 10.2 s median; wellbeing is time-limited from n=40 | First deadlines solution arrives at 2.4 / 3.6 / 5.0 s (presolve of ~9k x variables + cum chains), model build 0.3-0.9 s |
| 4 | EDF feasible => zero late work | **Refuted.** EDF was optimistic in 6 of 69 runs | Causes seen: the 12 h daily cap (EDF ignores it), dependencies, and for the first two runs pins placed after a due date (generator now keeps pins inside windows). See "Findings" |
| 5 | EDF < 50 ms at 100 items | **Confirmed.** 0.10 ms median | `results/executor_allocator.json`; allocator 0.13 s for the Cornell instance |

Targets (reference 12.4) vs this baseline: warm replan p90 <= 3 s -> **17.7 / 24.7 / 26.2 s (missed 6-9x)**; cold p90 <= 10 s ->
**20.5 / 30.2 / 30.7 s (missed 2-3x, and at the cap)**; deadlines stage <= 3 s -> missed; allocator <= 1 s -> met; executor -> met.
So v2 as specified does not meet its own targets on this laptop with this model. (The reference leaves `fine_days`, `horizon_days`
and slot lengths "to be decided by benchmark"; shrinking them is an obvious baseline improvement for a fair comparison, E002.)

## Findings

1. **Time-limited quality is the real baseline.** At the 30 s budget the preferences stage ends 63-94% above its bound, so
   "CP-SAT optimum" is only proven for the deadlines stage (and for wellbeing at n=20). Gaps to the *best known* value, not to a
   proven optimum, are what v3 must be compared on at n >= 40. Quality-vs-time: `figures/preferences_quality_vs_time.png`.
2. **Not deterministic under load or with workers > 1.** Three cold repeats of the same n=60 instance gave preferences values
   1.65M / 1.70M / 1.65M / 1.83M (seed 0), 0.61M vs 0.77-1.28M (seed 1), 2.06M vs 1.42-2.51M (seed 2): up to 2x spread. Reference
   scenario 20 ("identical plan on the same snapshot") only holds with one worker and a deterministic limit; that costs speed.
   Wall times also vary by up to 3-4 s across repeats (e.g. 25.2-27.4 s).
3. **One run (n=40, seed 1) returned a deadlines stage that was only FEASIBLE, 606 hours late**, i.e. the solver had not found
   a decent deadline plan after 12 s although a proven optimum is 0 in its warm sibling. The staged design means a bad stage-1
   solution is frozen and constrains stages 2-3. This is a candidate failure mode for the "deadline guarantee" of v2 itself.
4. **EDF is not an exact test of the full hard-rule set** (daily cap, dependencies, chunk rules, locks). In this benchmark it
   said "feasible" while the proven deadline optimum was > 0 in 6 of 69 runs (n=20: 1/10 instances, n=40: 2/10). For a v3 wall
   the guarantee must be defined against the CP-SAT/exact deadlines optimum; EDF is a necessary-condition filter and a fast
   certificate in one direction only (EDF infeasible => infeasible).
5. **Overflow is common even at 45% nominal load** (median 1.0 / 7.8 / 13.5 hours at n = 20/40/60): items with soft or no
   deadlines are left out because the `unscheduled` price (weight 0.5) is small against energy/reserve prices. Whether that is the
   intended trade is a policy question for the report; it makes absolute overflow a poor quality metric, so I compare stage values.

## Bugs and spec issues this experiment surfaced (all fixed or documented in RESEARCH_LOG.md)

- Locks can contradict dependency/chunk rules; the reference's repair (8.1) misses it. Fixed with an unsat-core relaxation (`solve`).
- The reference's C2 `need + 1` leeway makes replans churn between equal-cost plans; tightened to coarse slots only.
- The allocator's epsilon-earlier tie-break front-loads work; scenario 19 expects a linear share (both variants kept).
- The default hint matters: without the locks-only hint, first solutions took >5 s in the pinned families.

## What is next

E002 (baseline tuning for a *fair* comparison): shorter horizon / fewer fine days, coarser slots, per-stage time budgets, one worker
vs many, hint choices; so v3 is not compared against a straw-man. Then P3.
