# E015 — Should a "never" wall ever soften from evidence? (RQ8)

**Question.** A user set "never work on Sunday mornings" (a forbid rule: a wall). Later, work shows up in that window
(logged manually). Should Friday soften the wall, and under what policy?

**Users.** A "changed": the aversion is gone and they would rather work Sunday mornings than on evenings (true energy: no
Sunday-morning cost, weekday evenings x3); they log Sunday-morning work in 60% of weeks. B "one-off": still truly averse
(Sunday-morning price 6 in their true energy) but log work there once, in week 3 (a crunch week). C "steady": averse, never
logs work there.

**Policies.** `never` (walls never soften); `auto1` (soften after one event); `ask1` (after one event, ask "keep this rule?";
the user answers truthfully); `ask3` (ask after 3 events in distinct weeks within the last 6); `auto3` (soften after 3 such events,
no question). A softened wall becomes a price (it no longer forbids).

**Cost model.** Per week, the cost of a wrong state is measured on real plans (5 Cornell-style instances, sampler 600k steps):
for A, regret of planning with the wall vs without it under A's true energy; for B and C, regret of planning without the wall
(Friday does not know their price) vs with it under their true energy. Then 300 simulated users per type x 12 weeks per policy.

**Metrics.** cumulative regret over 12 weeks (points), questions asked, false softening (B or C softened), weeks A waits.

**Hypotheses.** `ask1` dominates: one question per event resolves both A and B. Among no-question policies, `auto3` is the
best compromise (B never reaches 3 events, A waits 4-5 weeks). `auto1` softens every B, `never` costs A every week.
