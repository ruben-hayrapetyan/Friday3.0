# E025 — The whole loop, end to end (RQ17)

**Question.** Does Friday with everything from program 2 (duration learning from estimates and recorded lengths, asking
when it matters, three schedules, learning from the pick, constraints parsed from the user's own words) beat v3 as built
in program 1 (estimates taken as given, one plan, learning from pairs and drags, no constraints beyond the reference
rules)? And which component carries the gain?

**Set-up.** `src/fr/sim/life.py`. 12 simulated people on report seeds (30000+), each a pair of a preference type (easy,
noisy, moody, missing rule, adversarial) and a duration type (calibrated, optimist, noisy, kind-biased, drifting, sparse),
with a heavier-than-average load (1.3) and estimates for 60% of tasks. Each person holds 3-4 real habits written as text
(sleep, no-work windows, a recurring commitment, a daily limit, a session limit), taken from E019's labeled cases. The
person's habits are the gold readings; Friday sees what Sonnet 5.5 parsed from the same text in E019 (cached replies;
the user is assumed to confirm every paraphrase). 6 weeks; daily replans at 08:00; three options on Mondays.

A block of work that breaks one of the person's real habits (during their commitment, inside their real sleep, in a
window they never work, past their own daily limit) is not worked: it is lost time. Tasks finish when their true length
is reached.

**Systems.** `v3_built`; `full` (E020/E024/E022/E023 choices); ablations `full - constraints`, `full - durations`
(estimates as given), `full - options` (one plan, learning from pairs and drags only).

**Metrics.** Hard-deadline tasks late (share) and hours late; hours of planned work that broke a real habit per week;
questions asked per week; Monday regret of the recommended and the picked plan (relative to the best plan for the
person's true weights, in each system's own model of the week); share of Mondays the recommended option was picked;
weight cosine; median planning seconds.

**Expectation.** Constraints remove habit conflicts almost entirely (lost time falls), duration learning removes most
misses for biased estimators, options and picks lower the regret of what the user lives.

**Changes before running** (after E021 round 2 and E024 round 1): systems plan hard deadlines at the shipped quantile
(`q_hard`, p95) — except `v3_built`, which takes estimates as given (the median), as program 1's v3 did; `full` may ask
for actual lengths of unrecorded finished tasks (`ask_actual`, E024), answered from memory (rougher than a timer).
`full - durations` keeps p95 padding but uses estimates as given and asks nothing, so it isolates learning.

## Round 2 (added after round 1, before running)

Round 1's `full` learned from picks *and* the pairs and drags of program 1; the app as built (the Planner page) collects
only picks, and E023 found picks alone learn as well or better. Round 2 runs `full-picks` (= full, picks only) on the
same 12 people: the system exactly as shipped. Usage: `run.py r2 <shard> <n_shards>`.
