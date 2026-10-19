# E013 — Hidden units for state, and mood vs taste (RQ6, RQ7, section 8 "units without dial seeding")

**Question.** Do hidden units that modulate rule weights, E(x,h) = sum_r (theta_r + sum_j U_jr h_j) phi_r, reduce regret for users
whose preferences shift with mood? Is seeding the units from v2's four dials (capacity, rest, spread, growth) better than
learning free units, and does adding free units to the seeded ones help? Can the system tell mood from noise (RQ7):
how often does it blame state when there is none (false attribution), and how well does it infer the state when there is one?
What does clamping the units to a picked pace give?

**Setup.** Users: moody (5), easy (5, no moods), noisy (5, no moods), 16 weeks, fresh Cornell-style instance per week. A moody
user picks the matching pace (Easy when tired, Push when motivated) in 30% of their non-normal weeks. Modes: `none` (taste only,
same likelihood model), `dial` (4 seeded units), `dial+free` (4 seeded + 2 free), `free` (6 free units, no seeding), `oracle`
(true mood known). Each mode plans with its own predicted units at the start of the week (from last week, the week's one-tap
check-in, and a picked pace) and refits after the week (rankings, skips, check-in). Model: Bradley-Terry on normalised feature
differences, Gaussian priors, joint MAP (L-BFGS).

**Metrics.** regret (as E011); state accuracy (posterior units read as a mood vs the true mood) for dial-seeded modes;
false attribution = share of truly normal weeks read as tired/motivated; predictive log-likelihood of each week's rankings
under the units predicted before the week (does state modelling predict better?) and the resulting per-user decision
"state or noise" (state if the cumulative gain over `none` exceeds 2 nats).

**Hypotheses.** (1) Dial-seeded units cut regret for moody users and cost nothing for the others. (2) Free units without
seeding fit noise: higher false attribution and no regret gain within 16 weeks. (3) Pace clamping is the single biggest help.
(4) The "state or noise" decision is right for most moody users and most noisy users, with false attribution higher for
noisy users than for easy ones.
