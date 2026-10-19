# E015 notes — should a "never" wall soften?

Run: per-week costs of the wrong wall state measured on 5 Cornell-style instances (best of 3 sampler seeds x 1M steps per
plan), then 300 simulated users per type x 12 weeks x 5 policies, 2026-10-17 14:29-14:31. `results/week_costs.csv`,
`results/policy_sim.csv`.

**Measured costs (points per two-week plan):** keeping the wall when the user changed their mind (A): 28.4 (17-43 over
instances); dropping it when the user still means it (B, C): 29.5 (24-38). Both are ~3% of a plan's energy: real but small,
and of the same size, so false softening is as bad as a stale wall.

| policy | regret A (changed mind) | regret B (one-off) | questions per user (A / B) | false softening (B) |
| --- | --- | --- | --- | --- |
| never soften | 341 | 0 | 0 / 0 | 0% |
| soften after 1 event | 45 | 236 | 0 / 0 | **100%** |
| ask after 1 event | **45** | **0** | 1 / 1 | 0% |
| ask after 3 events in 6 weeks | 148 | 0 | 0.98 / 0 | 0% |
| soften after 3 events in 6 weeks | 148 | 0 | 0 / 0 | 0% |

All users together (A, B, C equally common): ask after 1 event 15.0, ask/auto after 3 events 49.5, soften after 1 event 93.7,
never 113.6 regret points, with 0.67 / 0.33 / 0 / 0 questions per user.

## Against the hypotheses

Confirmed. One question at the first contradicting event resolves both kinds of user (the evidence alone cannot: a one-off and
a change of mind look the same after one event). Without questions, "3 events in distinct weeks within 6" is the best
compromise: it never softens for a one-off user and costs a changed-mind user about 4 extra weeks of the stale wall.
Softening on one event is the worst policy for one-off users and is never recommended.

**Policy:** a wall never softens silently. A contradicting event (work logged inside a "never" window) triggers one plain
question ("You worked on Sunday morning. Keep 'never Sunday mornings'?"); with questions turned off, propose softening
only after 3 events in 3 distinct weeks within 6, and then as a price, not by deleting the rule.

Limitations: the event process is simulated, not lived through the planner week by week; the cost per week comes from real
plans but the policies only rescale it. The question is assumed to be answered truthfully.
