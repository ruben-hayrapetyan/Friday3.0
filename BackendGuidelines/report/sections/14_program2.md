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

**Evaluation.** 101 hand-labelled texts written before any model call (sleep, windows, commitments, limits, sessions,
pacing, buffers, ordering, multi-constraint paragraphs, ambiguous texts that require a question, unsupported requests,
chatter and permissions); every third held out. A case counts only if the stored constraints equal the labelled reading
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

E021_PLACEHOLDER
