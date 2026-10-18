# E025 notes

## Rounds 1-2 (report seeds, 12 people, 6 weeks; results/runs_r*_*.csv, report_r2.txt, figures/systems.png)

| system | hard tasks late | hours late per term | work against a real habit (h/week) | questions / week | regret of the lived plan | cosine |
| --- | --- | --- | --- | --- | --- | --- |
| v3 as built in program 1 | 67.5% | 1098 | 7.83 | 0 | 0.039 | 0.800 |
| full (picks + pairs and drags) | 8.2% | 49 | 0.08 | 2.8 | 0.020 | 0.810 |
| **full, picks only (as shipped; round 2)** | **8.8%** | **52** | **0.08** | 2.8 | **0.014** | **0.843** |
| full - constraints | 16.4% | 82 | 11.73 | 2.8 | 0.019 | 0.799 |
| full - duration learning (estimates as given, p95, no questions) | 10.4% | 65 | 0.05 | 0 | 0.021 | 0.797 |
| full - options (one plan, pairs and drags) | 7.5% | 52 | 0.10 | 2.8 | 0.093 | 0.787 |

Paired against the shipped system (per person, +- s.e.): v3 as built +58.7 +- 6.5 points of hard misses, +1046 +- 174
hours late, +7.8 +- 1.5 h/week against habits; full - constraints +8.2 +- 2.7 points and +11.7 +- 2.4 h/week;
full - durations +2.2 +- 2.5 points (not significant); full - options +0.079 +- 0.033 regret of the lived plan.

- **The shipped system beats v3 as built on every person** (12/12 on misses and on habit conflicts). Most of the gain
  is the p95 padding and the deadline walls together with taking real lengths into account: v3 planned with the
  estimates themselves, and these people underestimate.
- **Constraints carry the habit result**: without them ~12 hours a week of planned work fall inside someone's real
  sleep, commitments or limits and are lost, and misses double. With Sonnet's parses (E019) almost nothing is lost (5
  minutes a week, all from one reading: "Friday evenings are off limits" became "from 18:00" where the labelled
  reading says 17:00; the paraphrase shows the hour, so a real user could correct it before confirming).
- **Options and picks carry the regret result**: one plan with pairs and drags lives 0.093 regret vs 0.014-0.020 with
  three options and pick learning.
- **Duration learning is not significant here** (10.4% vs 8.2-8.8%, 12 people, 6 weeks): the p95 padding already covers
  most bias at this load, and 6 weeks give the model little history. E021 (24 students, 8 weeks, load 1.5) is the
  cleaner test of learning (4.3% vs 9.8% at p95).
- Picks only vs picks + pairs and drags: the same misses and habit conflicts, slightly lower regret and higher cosine
  (0.843 vs 0.810, n.s.) — consistent with E023.
- **The hard case**: one person (missing rule, kind-biased estimates; no work before 10, at most 7 h a day, 90-minute
  sessions) misses 28-36% under every system: their habits leave less room than their work needs. Friday should say so
  rather than plan silently; the engine reports late and unplaced tasks per option, and the app shows them.
