# E024 — When should Friday ask for a length? (RQ13)

**Question.** The user asked that Friday "occasionally, if needed" ask for more assignment lengths. Two kinds of
question: an *estimate* for a new task the user gave none for, and the *actual length* of a finished task nobody
recorded. Which policy buys the most (fewer missed deadlines, less reserved-but-unused time) per question asked?

**Set-up.** The E021 term simulator (8 weeks, load 1.5, daily replans, true lengths) with students who give estimates
for only 30% of tasks and record 50% of lengths (each of the six bias types in this "sparse" form). Duration model
`hier_fused_drift_fa3_recal`, plans at p50 / p80. A recalled length (asked later) is rougher than a timer: twice the
recording noise, rounded to 15 minutes. Tuning seeds 0-2 per type (18 students); the chosen policy is checked again in
the end-to-end experiment on report seeds.

Estimate policies (actual = never): never; always (every task without an estimate); spread (ask when the model's
predictive spread s >= 0.45); voi30 / voi60 (ask only for a hard-deadline task, and only when an estimate would cut its
p80 padding by at least 30 / 60 minutes). Actual policies (estimate = never): always; budget2 (at most two a week).

**Metrics.** Hard-deadline tasks late (share), hours late, idle reserved hours per day, questions per week.

**Expectation.** Asking always helps a little per question; value-of-information policies keep most of the gain with
a fraction of the questions; asking for actuals helps learning more than estimates do.
