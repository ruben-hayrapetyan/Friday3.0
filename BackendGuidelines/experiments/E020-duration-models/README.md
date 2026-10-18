# E020 — Which duration model? (RQ11, prediction quality)

**Question.** Given a student's preliminary estimates and the actual lengths they record, which model predicts the
length of the *next* task best: the estimate as given, a personal bias multiplier, a per-kind bias, the hierarchical
log-normal of ENGINE_REFERENCE section 11 (kind -> course -> course x kind, partial pooling), the same fused with the
student's own history of lengths, a fading-memory (drift) version, or nearest recent tasks (knn)?

**Set-up.** Simulated students (`src/fr/sim/durations.py`), six types: calibrated, optimist (estimates ~64% of the truth),
noisy (estimate noise 0.5 in log), kind-biased (underestimates problem sets and essays only), drifting (bias grows 6%
a week), sparse (estimates on 30% of tasks, records 50%). A 10-week term of 4 courses: problem sets, readings, labs,
essays, two prelim preps, one project (about 70 tasks). True lengths drift by course over the term. Each task is
predicted when it is released, from what was recorded before; a recorded length becomes known at the due date.
Tuning seeds 0-9 per type here; the downstream experiment (E021) uses fresh seeds.

**Metrics.** Median absolute log error of the median (|log p50 - log truth|; 0.1 = 10%), CRPS on the log scale,
coverage of p50 and p80 (calibration: should be 0.5 / 0.8), learning curve by week, and the same split by whether the
task had an estimate.

**Expectation.** Hierarchical models beat the raw estimate for biased students within 2-3 weeks; fusion helps the noisy
and sparse students; fading memory helps only the drifting student; knn is noisier.
