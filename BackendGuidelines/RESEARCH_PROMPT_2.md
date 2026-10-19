# Research program 2: durations, three schedules, picks, and constraints from text

Continues `RESEARCH_PROMPT.md` (P0-P9, done; `REPORT.md`). Same rules: one shared evaluator, tuning seeds 0-99 vs report
seeds >= 10000, >= 10 seeds per engine cell, every experiment folder has README (written before running), run.py,
config.toml, results/*.csv, figures/*.png, notes.md; >= 2 improvement rounds per main phase; dead ends logged; commit
after every meaningful step; autonomy (log assumptions, don't ask). Jobs run at `nice -n 19`, BLAS threads 1 (shared machine).

## What the user asked for (2026-10-17, verbatim intent)

1. **Durations.** The user gives a preliminary prediction of how long each assignment will take. Friday records how long
   it actually took (the recording UI is frontend work), predicts future assignment lengths from that, and occasionally,
   when needed, asks the user for more estimates.
2. **Three schedules.** Friday outputs three different possible schedules to pick from.
3. **Picks teach.** Based on which one the user picks, Friday adjusts future schedules so the "recommended" one is the
   one the user would pick.
4. **Constraints from text.** Many constraints of many kinds (e.g. sleep habits, so no work is placed too late) are written
   in plain language and parsed by an LLM (Claude Sonnet 5.5, chosen by the user) into the engine's typed rules.

The consumer is the Friday macOS app (`../UI`, SwiftUI, no dependencies). It already runs the `claude` CLI with no tools
and applies structured replies itself; Friday's tasks are Todo List's `todos.json` (title, bucket, due date, progress in
quarters, done), and the standalone Todo List app drops unknown keys, so nothing new may be stored in `todos.json`.

## Principles carried over

- The plan is decided by the deterministic engine. The LLM only translates text into typed constraints, which the user
  confirms and which are then stored; it is never called while planning (ENGINE_REFERENCE section 1).
- Hard rules and avoidable deadlines stay guarantees in all three schedules.
- Learning must be uncertainty-aware: consistent evidence moves an estimate fast, one odd week barely moves it
  (ENGINE_REFERENCE section 11).

## Research questions

- **RQ11 Duration model.** Which predictor of actual length works best from a user's preliminary estimates plus recorded
  actuals: the estimate as given, a personal bias multiplier, a hierarchical log-normal (item type -> course -> all, with
  the estimate as a covariate, ENGINE_REFERENCE section 11), a drifting (Kalman) version, or a title/course similarity
  pool? Judge by log error, quantile calibration (p50/p80), and, most of all, downstream: deadline misses, hours of
  replanning and regret when the engine plans with each model's quantiles.
- **RQ12 Which quantile to plan with.** p50 for flexible and p80 for hard-deadline items (the reference's proposal), or
  something else; trade-off between misses and over-reserved time.
- **RQ13 When to ask.** Never, always, uncertainty threshold, or value of information (ask only when the answer could
  change the plan or the deadline risk). Judge by misses and regret per question asked.
- **RQ14 Three schedules.** How to generate three plans that are all valid and deadline-safe, clearly different, each
  good, and whose pick is informative: three seeds, T > 0 samples, a diversity penalty (distance to earlier picks of
  the set), posterior weight samples (Thompson), or query-by-committee designed sets. Also the time cost (target: three
  plans within the single-plan warm budget x 2).
- **RQ15 Learning from picks.** A pick among three is a choice (multinomial logit / Plackett-Luce over plan features). How
  fast does "the recommended plan is the one picked" rise, compared with learning from rankings and drags alone, across
  user types (easy, noisy, moody, missing rule, adversarial)? Does one odd pick flip the recommendation?
- **RQ16 Constraints from text.** How accurately does Sonnet 5.5 translate plain-language constraints into the typed
  schema (correct type, parameters, hard vs soft, scope), detect unsupported or ambiguous requests, and avoid inventing
  constraints? Which prompt and validation design (schema, examples, self-check, round-trip paraphrase for confirmation)
  is best? Measured on a held-out gold set.
- **RQ17 End to end.** Simulated semesters with Friday-shaped data: does the full loop (durations + three schedules +
  pick learning + parsed constraints) beat v3 as built (estimates taken as given, one plan) on misses, regret, pick rate
  and questions asked?

## Phases

| Phase | What | Done when |
| --- | --- | --- |
| Q0 | Contract with the app: Friday data -> `Problem` adapter; sidecar store (estimates, actuals, picks, constraints, profile) keyed by task UUID; `fr serve` JSON-lines over stdio (the app launches it like the `claude` CLI); `PROTOCOL.md` | adapter + store + server tested on fixtures |
| Q1 | Duration simulator + models (RQ11, RQ12): >= 2 rounds | best model chosen on downstream metrics, report seeds confirm |
| Q2 | Asking policy (RQ13) | policy chosen |
| Q3 | Three schedules (RQ14): >= 2 rounds | generator chosen; all three valid + safe on every evaluation instance |
| Q4 | Pick learning (RQ15): >= 2 rounds | learner chosen; pick-rate curves by user type |
| Q5 | Constraint parsing (RQ16): schema, gold set (tuning / held-out split), prompt rounds | accuracy on held-out set; failure modes listed |
| Q6 | End to end (RQ17) on report seeds | comparison table |
| Q7 | Report: new sections in `REPORT.md` (assembled), spec additions, log | all RQs answered |

Not in scope: changes to the Swift app (`../UI`). The protocol is written so the app can adopt it next.
