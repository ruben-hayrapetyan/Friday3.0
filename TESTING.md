# Testing Friday

Nothing should be able to break without the tests saying so, several times over. Every feature is tested in three
layers, in depth, and against a stream of generated situations. This file says what each layer is, where its tests
live, how to run them, and what every bug fix and new feature has to add. `tests/test_features.py` checks the parts
of it a machine can check.

## The layers

| Layer | What it proves | Where | Run |
|---|---|---|---|
| Regular | The code does what it says, case by case: commands, the planner, the words Friday says | `tests/` (Python), `web/src/**/*.test.ts(x)` | `uv run pytest`, `pnpm --dir web test` |
| Headless | The whole pipeline: a command sent over HTTP to a real `fridayd`, the plan made, every view read back the same way | `tests/system/` | `uv run pytest tests/system` |
| Web | What you see: a real Chrome, headless, drives Friday's pages and checks what they show | `web/e2e/<feature>.e2e.mjs`, `web/scripts/*-check.mjs` | `node web/e2e/run.mjs`, `node web/scripts/agreement-check.mjs`, `node web/scripts/overflow-check.mjs` |
| Depth | The tests notice a wrong change: each line changed on purpose (a mutation) must fail a test | `scripts/mutation.sh` | `scripts/mutation.sh [module] [tests]` on debian |
| Generated | Thousands of made-up weeks, settings and changes, every plan checked against what must always hold, and against the last release's plans | `tests/stress/` | `uv run python -m tests.stress.run --out DIR` |

`tests/features.toml` lists every feature with the commands and queries it runs and the pages it's on. Every command
and query belongs to one feature; every one is named in a regular test and a headless test; every feature with a page
has a web test. `tests/features_todo.txt` lists what isn't there yet, while the suite is being built: it only shrinks,
and `tests/test_features.py` fails if something is missing from it or listed but already done.

## Fixing a bug

1. Reproduce it first, the way it happened: on a scratch Friday (a test, or `fridayd demo --case alex --ready`), never
   the real one. If it was seen on a page, reproduce it on that page in Chrome (`web/scripts/browser.mjs`).
2. Write the test that fails because of it, in the layer it was seen in:
   - seen on a page: a web test (`web/e2e/`, or a screen test in `web/src` if Chrome isn't needed);
   - wrong data or a wrong answer: a headless test in `tests/system/` through the real server;
   - and always a regular test at the code that was wrong, as close to it as you can get.
3. Check each new test fails without the fix: restore the old file from git by copy (never stash), run, put it back.
4. Fix it, with one plain idea, not a patch for the symptom.
5. Ask what else could break the same way, and test that too:
   - the same fact said in other places (the agreement check, `web/scripts/agreement-check.mjs`, has a check for it);
   - the same kind of plan in other situations: add what must always hold to `tests/stress/harness.py`
     (`plan_issues`) or a scenario to `tests/stress/scenarios.py`.
6. Run the layers it touches, then the whole suite (heavy runs on debian: `remote-run`), then the mutation run of the
   module you changed: no new surviving mutants.
7. Write the test's comment with the date and what happened ("23 Nov, a user: …"), so the next reader knows why it's there.

## Adding a feature

- Add it to `tests/features.toml`: its commands and queries and its pages.
- Write all three layers before it ships: regular tests of each command and query, a headless test sending each over
  HTTP, and a web test driving its page. Nothing goes on `tests/features_todo.txt` for a new feature.
- Words Friday says about the plan are checked against the plan: a new number or sentence gets a check in
  `web/scripts/agreement-check.mjs`.

## Any hour of the day

The server tests run against the real clock. A test that sets something up "today" can hold only by daylight (24 Nov:
the meals test made a 5-7pm Dinner and failed when run after 7pm, since a repeat made after its time rightly isn't
backfilled). `FRIDAY_TEST_HOUR=H` runs the server tests in a zone where it's H o'clock now; before a release, run
`tests/system` at 23, 3, 4 (the day's start), 7 and 19 (on debian, it's heavy). A test that needs a time of day says so
itself (`TZ = zone_for_hour(12)`), not by when it happens to run.

## What "in depth" means

Line coverage only says a line ran. A mutation run changes the code on purpose, one small change at a time (a `<`
made `<=`, a branch taken away, a number off by one), and runs the tests: each change has to fail at least one test.
A change that no test notices (a surviving mutant) is a missing test, and is written before the work counts as done.
The first run, on the pro tips (24 Nov), let 65 of 341 changes through its 15 passing tests: coverage alone said 100%.

Coverage itself: `scripts/coverage.sh` (Python and the web app). The planner's inner loops are compiled (numba), so
the coverage tool can't see them run: measure with `NUMBA_DISABLE_JIT=1` to count them.

## Generated situations

`tests/stress/` makes worlds: people from `friday.sim.profiles` and generated ones, with random settings (sleep, day
start, paces, rules, breaks, time zones including half-hour ones and daylight-saving nights), random schedules and
random changes (add, edit, finish, skip, pin, lock, wait for, undo). After each change every plan is checked for what
must always hold (no overlaps, no work over events, sleep and meals kept, nothing past a hard due unless it's said
late, waits in order, locks kept, the pages' words agreeing with the plan). The same worlds also run on the last
release, and the plans are compared: a difference no change explains is flagged.
