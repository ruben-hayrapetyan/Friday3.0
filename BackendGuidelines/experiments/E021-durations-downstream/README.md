# E021 — Do better duration predictions mean fewer missed deadlines? (RQ11, RQ12)

**Question.** E020 ranked models by prediction error. What matters to the user is downstream: when Friday plans every
morning from predicted lengths, how many hard deadlines are missed, how many hours late, and how much reserved time
goes unused? Which quantile should plans use (RQ12)?

**Set-up.** `src/fr/sim/term.py`: an 8-week term per student, heavier than E020 (load 1.5, about 35-40 true hours of
coursework a week on top of ~15 h of classes). Every day at 08:00 Friday plans the next 14 days with the v3 planner
(fixed steps: construction -> repair -> CP-SAT deadline fallback -> lexpolish), using each unfinished task's predicted
remaining length (the quantile of length given the work already done). The student works exactly the planned blocks of
that day; a task finishes when its true length is reached; recorded lengths update the model. Tasks are known from their
release (no foresight). Report seeds (10000-10003) per type, 6 types = 24 students.

Round 1: models `oracle` (true lengths: the floor), `as_given`, `global_bias_recal`, `hier_fused_drift_recal` (E020's
choice) at the reference quantiles (p50 for flexible items, p80 for hard-deadline items).
Round 2 (RQ12): quantile policies p50/p50, p50/p80, p70/p90, p80/p95 with the chosen model.

**Metrics.** Share of hard-deadline tasks finished late, hours late (sum), late readings, reserved-but-unused hours per
day (idle), planned hours per day.

**Expectation.** as_given misses many deadlines for optimists and drifting students; the learned model cuts misses
most of the way to the oracle; higher quantiles trade misses for idle time.
