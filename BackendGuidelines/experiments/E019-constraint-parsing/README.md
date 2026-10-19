# E019 — Constraints from text (RQ16)

**Question.** How accurately does Claude Sonnet 5.5 translate plain-language constraints ("no work after 11", "gym MWF
7-8:30", "I can't focus for more than 90 minutes") into Friday's typed constraints (`src/fr/product/constraints.py`),
and which prompt design is best? Does it ask when the text is ambiguous, report what it cannot express instead of
approximating, and stay silent on chatter and permissions ("I don't mind working late")?

**Set-up.** 101 hand-labelled cases (`gold.py`, written before any model call): sleep, avoid / prefer windows,
commitments, limits, free time, session lengths, one sitting, pacing, finishing early, buffers, ordering, multi-constraint
paragraphs, ambiguous texts (a question is required), unsupported requests, chatter and negations. Every third case is
held out (33); prompts are tuned on the other 68. One fixed context (4 courses, 12 tasks, 4 events, today = Saturday
2026-10-17). Claude runs through the `claude` CLI with no tools, as the Friday app runs it.

**Scoring** (`score.py`). A case is correct when the stored constraints equal the gold reading (or an accepted
alternative) with nothing extra, a question is asked when required (and not when forbidden), and unsupported requests
are reported. Targets are compared by the tasks they select; times allow listed alternatives; "soft" accepts any soft
strength. The scorer accepts the gold itself on every case (`run.py selfcheck`).

**Variants.** Round 1: `bare` (role + schema), `guide` (+ translation guide), `guide_text` (schema in the prompt instead
of the CLI's structured output). Round 2 builds on round 1's errors on the tuning split. The chosen prompt then runs 3
times on the held-out split.

**Metrics.** Case accuracy; constraint-set accuracy; question and unsupported handling; invented constraints (extras);
valid replies; whether the reply compiles into a problem; cost and seconds per case.

**Expectation.** Most errors will be on hard vs soft, the sleep-night convention, and windows running past midnight;
schema enforcement should remove invalid replies.
