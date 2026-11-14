## 14. Program 2: durations, three schedules, picks and constraints from text

Program 2 (`RESEARCH_PROMPT_2.md`, experiments E019-E025) answers what the Friday app needs on top of the v3 engine, as the
user asked for it: (1) start from the user's own estimates of how long assignments take, record how long they really took,
predict future lengths from that, and occasionally ask for more lengths; (2) offer three schedules to pick from; (3) learn
from the pick so the recommended schedule becomes the one the user would pick; (4) accept many constraints written in plain
language (sleep habits, no work after a time, commitments, limits), parsed by an LLM. Same rules as program 1: one shared
evaluator, tuning seeds vs report seeds, at least two improvement rounds per main question, everything reported.

### 14.1 Constraints from text (RQ16, E019)

**Design.** The LLM never plans. It translates text into twelve typed constraint kinds (`src/fr/product/constraints.py`):
sleep, avoid a window, prefer a window, commitment, daily limit, keep time free, session length, one sitting, pacing,
finish early, buffer around events, order of two tasks; plus "questions" (ask instead of guessing) and "unsupported"
(report what cannot be expressed). Each constraint carries the words it came from and a one-line paraphrase the user
confirms; only confirmed constraints are stored. Compilation into the engine is deterministic: hard constraints become
walls (forbidden slots, chunk limits, earlier deadlines, the daily cap, fixed events, sleep core), soft ones become rule
weights at three strengths. Claude Sonnet 5.5 runs through the `claude` CLI exactly as the Friday app already runs it (no
tools, no MCP servers, no saved session), with the CLI's structured output.

**Evaluation.** 101 hand-labeled texts written before any model call (sleep, windows, commitments, limits, sessions,
pacing, buffers, ordering, multi-constraint paragraphs, ambiguous texts that require a question, unsupported requests,
chatter and permissions); every third held out. A case counts only if the stored constraints equal the labeled reading
(or a listed alternative) with nothing extra, a question is asked exactly when required, and unsupported requests are
reported. Targets are compared by the tasks they select.

| prompt | tuning (68) | held out (33) |
| --- | --- | --- |
| role + schema only | 91.2% | 87.9% |
| + translation guide (round 1) | 97.1% | 97.0% |
| guide with the schema in the prompt instead of structured output | 89.7% | - |
| **guide v2** (round 2: "useless / impossible" = hard; non-constraint requests are reported) | 98.5% | **99.0%** (3 runs; 32/33 right every time) |
| guide v2 + six worked examples | 98.5% | - |

- Every reply was valid and compiled; no invented constraints on the held-out split. Median 3.3 s per text, about
  $0.006 at list price.
- Without the guide, the model asks needless questions and turns unsupported requests into something else (alternating
  subjects became "spread out"). Passing the schema in the prompt made it ask about every missing optional field.
- The one held-out miss reported "sessions of about 2 hours" as inexpressible (true: the schema has no target length)
  instead of reading it as a 1-2 hour range.
- Limits: one context, 101 texts by one author, English, typed. Real users will be more varied; the confirmation step is
  the safety net (figure: `experiments/E019-constraint-parsing/figures/accuracy.png`).

### 14.2 Predicting how long tasks take (RQ11, RQ12, E020, E021)

**Simulated students** (`src/fr/sim/durations.py`): a term of four courses (problem sets, readings, labs, essays, two
prelim preps, a project). True length = kind base x course difficulty x course-kind effect x a drift over the term x item
noise. The student's preliminary estimate sees the expected length and part of the item's own noise, shifted by a
personal bias and estimate noise; six types: calibrated, optimist (estimates ~64% of the truth), noisy, kind-biased
(underestimates problem sets and essays only), drifting (bias grows 6% a week), sparse (estimates 30% of tasks, records
half). Recorded lengths carry a little noise and are sometimes missing.

**Models** (`src/fr/product/durations.py`): estimate as given; one personal bias; per-kind bias; the hierarchical
log-normal of ENGINE_REFERENCE section 11 (two Bayesian ridge regressions over all / kind / course / course x kind: one for
log(actual / estimate), one for log length) with or without fusing the two; fading memory (4-week half-life); nearest
recent tasks; online recalibration from the model's own one-step-ahead errors.

| E020 (60 students, weeks 2-9) | CRPS (log min) | median abs log error | p50 / p80 coverage |
| --- | --- | --- | --- |
| estimate as given | 0.290 | 0.338 | 0.27 / 0.55 |
| one personal bias | 0.218 | 0.248 | 0.47 / 0.79 |
| hierarchical, not fused | 0.223 | 0.250 | 0.47 / 0.77 |
| hierarchical, fused, fading memory | 0.186 | 0.219 | 0.44 / 0.75 |
| **+ recalibration (chosen; fused after 3 recordings)** | 0.187 | 0.217 | 0.47-0.48 / 0.80 |

- The planning fallacy is mostly one number per person: a single bias multiplier removes most of an optimist's error
  (0.333 -> 0.178). Fusing the estimate with the student's own history is what helps noisy estimators (0.318 -> 0.215).
- Calibrated students lose a little with any learning (0.143 -> 0.155): their estimates were already right.
- Round 3 checked two things. Students whose typical lengths sit far from Friday's population defaults (0.5 log sd) do not
  change the ranking. And the user asked for their own estimates to be the starting point: fusing with population defaults
  from the first task predicts better in the first two weeks (CRPS 0.236 vs 0.267), but turns "I think 2 h" into 2 h 40 m
  on day one. The shipped model uses the user's estimate (times the learned ratio) until three lengths are recorded; after
  week 2 the two are identical.

**Downstream (E021).** What matters for the user is missed deadlines, not prediction scores. A term simulator replans
every morning with v3 at a fixed step budget, reserving for each open task a quantile of its predicted remaining length
(p50 for flexible tasks, a higher quantile for hard deadlines); work proceeds on the true lengths. 24 students on report
seeds, 8 weeks, a heavy load (1.5x).

| hard-deadline tasks late / reserved-but-unused h per day | p50 | p80 | p90 | p95 |
| --- | --- | --- | --- | --- |
| estimate as given | 67.9% / 0.64 | 36.5% / 1.08 | 20.5% / 1.31 | 9.8% / 1.49 |
| one personal bias | 41.9% / 0.91 | 10.9% / 1.42 | 5.6% / 1.62 | 3.6% / 1.84 |
| **shipped model** | 46.8% / 0.79 | 15.1% / 1.18 | 8.4% / 1.49 | **4.3% / 1.57** |
| true lengths (reference) | | 0% / 0.13 | | |

- Learning lengths cuts missed hard deadlines by 2-4x at every quantile.
- Round 1 compared models at p80 only, and the single-bias model looked better downstream (10.9% vs 15.1%) despite
  predicting worse: its wider spreads buy more padding. Along the whole frontier (round 2; figure
  `experiments/E021-durations-downstream/figures/frontier.png`) the shipped model misses fewer deadlines for the same
  unused time at every point, so E020's choice stands.
- **The quantile matters more than the model.** p80 -> p95 cuts misses from 15.1% to 4.3% and hours late from 116 to 34
  per student-term, for 23 more minutes a day of reserved time that ends up unused. The product plans hard deadlines at
  p95.
- Readings and other flexible tasks finish late often (59-63%; 35% even with true lengths): the planner trades soft
  lateness against wellbeing, as designed.

**When to ask (RQ13, E024).** The user asked that Friday "occasionally, if needed" ask for more lengths. Two kinds of
question: an estimate for a new task, and the actual length of a finished task nobody recorded (answered from memory,
so rougher than a timer). 18 "sparse" students (estimates for 30% of tasks, half the lengths recorded), 8 weeks.

| asks for (p95 planning) | questions / week | hard tasks late | hours late per term | unused h/day |
| --- | --- | --- | --- | --- |
| nothing | 0 | 2.9% | 14.9 | 2.42 |
| estimates, when one would save >= 60 min of padding | 3.1 | 3.4% | 13.3 | 2.07 |
| estimates, always | 6.1 | 3.9% | 14.0 | 2.06 |
| **actual lengths, at most 2 a week** | 2.0 | **0.2%** | **0.5** | 2.27 |
| actual lengths, always | 3.8 | 0.4% | 0.9 | 2.35 |

- Asking how long finished tasks took is the question that pays: two a week remove nearly all remaining misses.
- Asking for estimates does not reduce misses. At p80 it even raised them (12.5% -> 17.0% when always asking): an
  estimate narrows the prediction, and the fused prediction is overconfident once one is in (its p80 covers 74% of tasks
  when every task has an estimate, 82% without). At p95 the effect is small, and estimates mostly buy back reserved
  time (21 minutes a day). Friday keeps asking for an estimate only when it would save an hour of padding on a hard
  deadline.

### 14.3 Three schedules to pick from (RQ14, E022)

Option 0 is the recommended plan. Six ways to make options 1 and 2 (`src/fr/product/options.py`), all starting from the
repaired zero-late plan so none is later than it on a hard deadline: other random seeds; samples at a temperature;
"diverse" (a price on every task-slot an earlier option used); Thompson (plans for two weight vectors drawn from the
learner's posterior); archetypes (a "lighter" and a "push" week); and query-by-committee (the pair of posterior plans
whose pick is most informative). Simulated users from section 6 (easy, noisy, moody, missing rule, adversarial), 3 per
type, 10 weeks, a new semester instance each week; the user picks by true energy with their own noise and Friday learns
from the pick.

| tuning users, 10 weeks | regret of the recommended | regret of the pick | recommended picked | distinct | cosine at end |
| --- | --- | --- | --- | --- | --- |
| seeds | 0.140 | 0.086 | 33% | 0.72 | 0.858 |
| temperature | 0.139 | 0.136 | 88% | 0.69 | 0.858 |
| diverse | 0.136 | 0.124 | 71% | 0.87 | 0.878 |
| Thompson | 0.135 | 0.093 | 27% | 0.42 | 0.852 |
| archetype | 0.137 | 0.102 | 21% | 0.40 | 0.849 |
| query-by-committee | 0.114 | 0.100 | 37% | 0.31 | 0.859 |
| **Thompson, ranked by posterior pick probability (round 2)** | **0.100** | **0.088** | **63%** | 0.43 | 0.867 |

- Every option of every method kept every avoidable deadline. Users pick their truly best option ~90% of the time, so
  the plan they live is the best of the three: good alternatives matter more than different ones. Temperature and
  "diverse" alternatives are worse plans (pick regret +0.03-0.04).
- **"How often is the recommended option picked" misleads on its own.** Temperature and diverse score highest only
  because their alternatives are worse. For seeds and Thompson the recommended plan was the user's best less often than
  chance, because the alternatives start from it and get extra annealing steps.
- **Ranking the three after making them** (option 0 = the highest posterior-mean pick probability) more than doubles
  the pick rate of the recommended option (27% -> 63%; 77% for easy users, 50% for users with a missing rule) and cuts
  its regret by a quarter, with the regret of what the user lives unchanged. Shipped.
- The generator does not change how fast Friday learns the user's weights over 10 weeks (end cosine 0.85-0.89).

### 14.4 Learning from the pick (RQ15, E023)

A pick is a choice among three plans: P(pick k) is a softmax of -theta . phi_k over the three (multinomial logit, with
the same scale normalisation as the Bradley-Terry pairs of E011b), fitted as a MAP with a Gaussian prior toward the
hand-set weights; a Laplace approximation gives the posterior that Thompson sampling and the ranking use
(`src/fr/product/picks.py`). 15 tuning users, 12 weeks, options from the shipped generator.

| learning | regret of the recommended | regret of the pick | cosine at end |
| --- | --- | --- | --- |
| none | 0.110 | 0.098 | 0.875 |
| **picks (multinomial logit)** | **0.082** | **0.075** | **0.904** |
| picks (rank breaking: the pick beats each other option) | 0.086 | 0.077 | 0.887 |
| picks + pairs and drags | 0.094 | 0.083 | 0.875 |
| pairs and drags only | 0.130 | 0.112 | 0.859 |

- Picks alone cut the regret of the recommended plan and of the lived plan by a quarter (paired -0.028 +- 0.007).
- Pairs and drags do not add to picks on average: they help users who answer consistently and hurt users with a missing
  rule or adversarial answers (end cosine 0.80 and 0.73 vs 0.93 and 0.85 with picks alone). That is fortunate, because
  the app collects picks only.
- A user who takes the recommended option out of habit 30% of the time slows learning but does not bias it.
- A single week moves the weights little (1 - cosine 0.008), so one odd pick does not flip the recommendation
  (figure: `experiments/E023-pick-learning/figures/regret_by_week.png`).

### 14.5 The whole loop (RQ17, E025)

`src/fr/sim/life.py`: 12 simulated people on report seeds, each a preference type x a duration type, a heavier load
(1.3x), estimates for 60% of tasks, and 2-4 real habits written as text (sleep, no-work windows, a recurring
commitment, a daily limit, a session limit; E019 cases). The person's habits are the labeled readings; Friday sees what
Sonnet 5.5 parsed from the same text. 6 weeks, a replan every morning, three options on Mondays. Work planned against a
real habit is not done.

| system | hard tasks late | hours late per term | work against a real habit (h/week) | regret of the lived plan |
| --- | --- | --- | --- | --- |
| v3 as built in program 1 (estimates as given, one plan, no constraints) | 67.5% | 1098 | 7.83 | 0.039 |
| **Friday as shipped** (picks only) | **8.8%** | **52** | **0.08** | **0.014** |
| shipped + pairs and drags | 8.2% | 49 | 0.08 | 0.020 |
| without constraints | 16.4% | 82 | 11.73 | 0.019 |
| without duration learning (estimates as given, p95, no questions) | 10.4% | 65 | 0.05 | 0.021 |
| without options (one plan, pairs and drags) | 7.5% | 52 | 0.10 | 0.093 |

- The shipped system is better than v3 as built for every one of the 12 people, on misses and on habit conflicts.
- Constraints from text carry the habit result (without them ~12 h a week of planned work is lost and misses double).
  The 5 minutes a week left come from one reading ("Friday evenings are off limits" read as from 18:00, labeled 17:00)
  that the user would see in the paraphrase.
- Options and pick learning carry the regret result (0.093 -> 0.014).
- Duration learning is not significant end to end (10.4% vs 8.8%, +2.2 +- 2.5 points over 12 people and 6 weeks): p95
  padding covers most of the bias at this load. E021 is the cleaner test (4.3% vs 9.8% at p95).
- One person (no work before 10, at most 7 h a day, 90-minute sessions, underestimates problem sets) misses 28-36%
  under every system: the habits leave less room than the work needs. The app shows late and unplaced tasks per option.

### 14.6 Program 2 in brief

| question | answer | evidence |
| --- | --- | --- |
| RQ11 predict lengths | a hierarchical log-normal over the user's ratio actual/estimate and their lengths, the user's estimate first until 3 lengths are recorded, fading memory, recalibration; CRPS 0.187 vs 0.290 for estimates as given | E020 |
| RQ12 plan with uncertainty | reserve the p95 of the remaining work for hard deadlines, the median for flexible tasks: 4.3% of hard deadlines missed vs 36.5% planning on the estimates' p80 | E021 |
| RQ13 when to ask | how long finished tasks took, at most two a week (misses 2.9% -> 0.2%); an estimate only when it saves an hour of padding | E024 |
| RQ14 three schedules | Thompson alternatives, ranked by posterior pick probability: the recommended one is picked 63% of weeks (from 27%), lived regret 0.088 | E022 |
| RQ15 learning from picks | multinomial logit over picks alone: -25% regret; pairs and drags not needed | E023 |
| RQ16 constraints from text | Sonnet 5.5 + a translation guide + structured output: 99.0% of held-out texts fully right, nothing invented; the user confirms each paraphrase | E019 |
| RQ17 the whole loop | vs v3 as built: hard misses 67.5% -> 8.8%, habit conflicts 7.8 -> 0.08 h/week | E025 |

Limits: every result except E019 comes from simulated students and users whose behavior I designed; the parsing test
has one author's texts. The app's Planner page was checked by compiling, snapshots, and a live round trip with the
engine, not by a real term of use.
