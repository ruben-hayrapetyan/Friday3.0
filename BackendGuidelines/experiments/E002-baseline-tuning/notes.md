# E002 notes — tuning the v2 baseline at a 10 s budget

Run: reference n=40, tuning seeds 0-9, six variants, 10 s total limit, 8 workers (except D). Plans mapped onto the
control grid and scored by the shared evaluator/checker. `results/runs.csv`.

| variant | no plan at all (time-out) | zero late | median late hours (when a plan came back) | median total s |
| --- | --- | --- | --- | --- |
| A control | 5/10 | 0/10 | 1017 | 21.0 |
| B fine_days 3 | 0/10 | 0/10 | 1063 | 20.8 |
| C horizon 10 d | 1/10 | 0/10 | 357 | 21.2 |
| D 1 worker | 10/10 | - | - | - |
| E constructive hint | 7/10 | 1/10 | 6.5 | 22.4 |
| F shares .2/.3/.5 | 4/10 | 0/10 | 616 | 24.7 |

(B: 7 of 10 plans break a hard rule once mapped back onto 15-minute slots: coarse slots hide chunk-length violations.)

**Findings.**
1. **At 10 s the v2 design does not work on 40 items**, whatever the tuning: every variant either times out (the stage
   limits double once, so "10 s" runs take 20-25 s) or returns hundreds of late hours. The first deadline-feasible solution
   alone needs 2.4-5 s (E001) and three stages each pay presolve. Hypotheses 1, 2 and 4 are refuted; 3 is confirmed (one worker
   never produced a plan in 10 s).
2. **A good hint does not rescue it.** With a zero-late constructive plan as the hint, CP-SAT still times out in 7/10 runs:
   the hint is feasible (verified: fixing variables to it solves in 0.12 s, and the model's stage values equal the evaluator's
   exactly), but the preferences stage cannot finish presolve inside its 3 s share, so the hinted solution is never reported.
3. The fair baseline is therefore **v2 at its own 30 s budget** (E001: zero late in 80-90% of cold runs), and at equal wall
   clock (10 s) v2 is simply not competitive. Later experiments compare against both: CP-SAT-30 s (quality reference) and
   CP-SAT-10 s (equal time).
