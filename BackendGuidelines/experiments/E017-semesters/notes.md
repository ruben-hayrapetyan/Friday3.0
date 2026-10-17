# E017 notes — end-to-end semesters, v3 vs v2 (P8)

Run: **report seeds only** (instances 10000+, users 20000+, never tuned on); 4 user types x 3 users x 12 weeks = 144 user-weeks
per system; 2 shards; 2026-10-17 16:55-17:35 (load 10-50). Systems:
- `v3`: wall sampler (construct, weighted energy wellbeing + preferences with deadlines walled, 2 s step budget), Bradley-Terry
  ranking learning with drags x3, dial-seeded hidden units behind the calibrated gate (E013c) plus pace clamping, rule proposals
  from week 6 added only on the user's yes (threshold from E014's tuning users), query-by-committee pair selection.
- `v3_lex`: the same system with lexicographic (tiered) stages, to separate the engine from the stage policy.
- `v2`: staged CP-SAT at 30 s, 8 workers; v2's max-margin learning from drags; paces scale the dial rules.
The simulated users' utility is a weighted sum of rule costs (no stage order), so lexicographic planning has a built-in regret.

## Results (144 user-weeks per system)

| | v3 | v3_lex | v2 |
| --- | --- | --- | --- |
| relative regret, median (all users) | **0.087** | 1.62 | 6.13 |
| ... easy / moody / noisy / missing-feature | 0.057 / 0.070 / 0.103 / 0.168 | 2.87 / 1.77 / 1.49 / 0.94 | 1.93 / 3.54 / 28.6 / 6.17 |
| weeks with a hard deadline missed | **0** | **0** | 3 (9 items) |
| plans breaking a hard rule | **0** | **0** | 2 |
| plan time, median (p90) | 1.3 s (2.9 s) | 0.8 s (1.5 s) | 19.8 s (29.3 s) |
| learned-weight cosine with the truth, last week | 0.955 | 0.939 | 0.866 |
| missing-feature users: right rule added | 3/3 (one also added its close twin "night") | 3/3 | - (v2 cannot) |
| users without a missing feature: wrong rule added | 0 (every false proposal refused by the user) | 0 | - |

Per week, v3 had lower regret than v2 in **100%** of the 144 user-weeks; v3_lex beat v2 in 78% (same stage policy, so this is
the engine); v3 beat v3_lex in 97% (the stage policy).

v2's failures: two weeks of one missing-feature user where CP-SAT's deadline stage stopped at FEASIBLE with 4-5 hard items late
(30 s budget), and two weeks with a plan that breaks a hard rule (lock repair on a partial one-sitting lock). Excluding them its
median regret is unchanged (6.11).

## Findings

1. **v3 meets every hard guarantee on the evaluation set** (0 missed deadlines, 0 invalid plans in 288 v3 plans), v2 does not
   (3 weeks with misses, 2 invalid). Hypothesis confirmed.
2. **Speed**: 1.3 s vs 19.8 s median per weekly plan (15x), p90 2.9 s vs 29.3 s.
3. **Regret**: most of v2's regret comes from the stage policy (lexicographic planning vs a user who trades wellbeing for
   preferences), which v3_lex shares (1.6); with the same stage policy the sampler beats CP-SAT in 78% of weeks and has 3.8x lower
   median regret, so the engine itself is better too. **The stage policy is the bigger lever** (v3 vs v3_lex: 0.09 vs 1.6) and is a
   product decision this simulation cannot make: a real user may well want wellbeing first.
4. **Learning**: v3's weights end closer to the truth (cosine 0.955 vs 0.866 for v2's drags-only learner).
5. **Supervisor**: the right rule was proposed and accepted for all three missing-feature users; false proposals (up to 4 per
   user over 12 weeks) were all refused, so no wrong rule entered. That is a cost in questions the product should budget.
6. **Hidden units never switched on automatically** in 12 weeks (the calibrated gate is slow, E013c); moody users were helped only
   in weeks they picked a pace. Moody users' v3 regret (0.070) is still close to easy users' (0.057).

Limits: 3 users per type; regret is single-plan per week; v2 ran 8-worker CP-SAT under load (median 19.8 s; it would be faster on
an idle machine, but E001 shows it still misses its targets there).
