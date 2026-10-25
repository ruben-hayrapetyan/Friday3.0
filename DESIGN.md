# Friday — Design Document

Version 3 · Oct 18, 2026

This is the specification for Friday, built from scratch in an empty repository. Its scheduler is an energy sampler with walls (sections 10–11), chosen by a research program that compared it with a staged CP-SAT engine on one shared evaluator; its learning layer (section 21) comes from the same research. Sections 1–21 are specified in full, except 21.7. Sections 22–23 are outlines, to be specified properly after a few weeks of daily use. Where this document gives a number (a weight, a threshold, a time limit), it is a starting value to verify, not a fact.

---

## 0. Purpose, scope and principles

Friday is a calendar and to-do app that decides **when** you do things. You tell it what needs doing (or it reads it from your course feeds). It keeps a detailed plan for the next two weeks and a rough one for the months after, tells you what to do right now, lets you do something else whenever that is safe, and replans as life happens.

The goal: you never think about when to do things; you trust the plan; it lets you be flexible; and it learns how you work.

### Principles (these hold in every milestone)

1. **Deterministic planning.** The same snapshot, settings version, learned-profile version and seed give the same plan. The scheduler is randomized search, but its randomness is seeded and its budget is counted in steps, not seconds (11.9). No LLM decides the plan.
2. **Deadlines first, guaranteed by walls.** Hard rules (one thing per slot, locks, windows, caps, chunk limits, dependencies, and on-time hard deadlines) are walls the search never crosses, not weights it trades. A hard item that is on time in the start plan is never made late. Then wellbeing, then preferences, as the stage policy defines (11.8).
3. **Never infeasible.** Work that does not fit goes to overflow and is priced. Overload becomes a triage decision, never an error.
4. **Exact explanations.** Every cost the engine optimizes can be recomputed from a solution, to the integer.
5. **Convex penalties only.** Every rule is a slot price, a ban, or a linear quantity with a hinge curve whose slopes are non-negative. Every rule is compiled into the kernel and must match the evaluator exactly (11.5).
6. **The plan is a budget, not a script.** The only thing that must hold is that deadlines stay feasible. Everything else bends around what you actually do.
7. **No agent inside Friday.** An LLM may only (a) extract items from documents into a review inbox (mail and documents by `llm.model`; calendar entries' kinds and titles sorted by the smaller `llm.small_model`, M13) and (b) translate a quick-add line the grammar cannot parse into one command that you confirm. Agents drive Friday from outside, through the same commands as everything else.
8. **One command vocabulary.** Every interface is generated from one registry. Every command supports preview and undo and records who issued it.
9. **Mechanism in code, policy in settings.** No personal preference is hard-coded. Settings are data; the personal build may also load Python rule plugins.
10. **Readable code** (section 4.4). You will edit this code by hand.
11. **Personal first, hosted-ready.** Build for one user, but keep the seams in section 23 so a hosted service is possible later.
12. **Nothing external changes the schedule unreviewed.**

### Non-goals

A native mobile app; an in-app agent; editing through Google Calendar; multi-user features beyond the seams; travel time and locations in the engine; scheduling with other people.

---

## 1. Concepts and glossary

| Term | Meaning |
| --- | --- |
| Item | Anything Friday knows about: a class, a problem set, a project, a meal, a store run. Its behaviour comes from its facets (section 6) |
| Facet | One independent property of an item: when, amount, shape, firmness, value, relations, context, certainty |
| Preset | A named set of facet defaults (Assignment, Class, Errand, …). You pick a preset; you never have to pick facets |
| Area | An optional group with a colour: CS 1110, CS Club, FinCity, Health. Rules can target areas |
| Tag | A free-form label (`+reading`). Rules can target tags |
| Series | A repeat rule that creates items (occurrences): every class meeting, a daily shower, gym 3 times a week |
| Occurrence | One item created by a series |
| Fixed item | An item at a set time (class, appointment, shove). Friday schedules around it |
| Flexible item | An item Friday places (work, errands, meals within a window) |
| Unit | 15 minutes; the unit of all durations in the engine |
| Slot | One cell of the scheduler's grid: 15 minutes in the fine zone, 30 minutes in the coarse zone |
| Planning day | From `day_start` (04:00) to the next day's 04:00, so 01:00 work counts as the night before |
| Horizon | The scheduler's detailed window (default 14 planning days from now). The allocator looks further (default 12 weeks) |
| Block | One run of consecutive slots of one item in a plan. Its key is `item_id@start` and is stable across plans |
| Plan | All blocks from one scheduler run. One plan is current. A **provisional** plan is the executor's instant preview |
| Pin | Your instruction that an item happens at a given time: **preferred** (resists moving, may move) or **locked** (cannot move). Pins belong to items, not to plans |
| Stage | `deadlines`, `wellbeing` or `preferences`: the three parts of a plan's cost, in priority order |
| Energy | A plan's cost as the sampler sees it: the stage values combined by stage weights (11.5) |
| Wall | A hard rule enforced by never making a move that breaks it (11.4) |
| Protected item | A hard-deadline item that is complete and on time in the start plan; walls keep it on time |
| Chain | One independent run of the annealing sampler; several run in parallel and the best wins |
| Step budget | How many moves a chain proposes; fixed per problem size so plans are deterministic |
| Learned multiplier | A per-rule factor on the hand-set weight, learned from your comparisons and drags (section 21) |
| Rule | A configured use of a rule type, with a name, weight, stage, scope and parameters |
| Points | The unit of every penalty. Anchor: 1 point = moving 1 hour of already-planned work |
| Overflow | Work that does not fit in the horizon; priced, reported, never an error |
| Quota | The allocator's minimum for an item in one week of the horizon |
| Pacing line | The progress an item should have made by a given date (linear by default) |
| Slack | How long an item with a hard deadline can wait before deadlines become infeasible: its latest start minus now |
| Safe swap | Something you could do now instead of the planned item without making any hard deadline infeasible |
| Reserve | Free time the plan deliberately leaves open (e.g. 2 h on weekday evenings) for spontaneous things |
| Open item | An item with no fixed amount that fills free time, with each extra hour in a day worth less than the one before (a book, a side project) |
| Dial | One of four numbers that scale your settings for a day: capacity, rest, spread, growth (section 17.6) |
| Pace | A saved set of dial values with a name: Normal (the default), Easy, Push, or your own. Switching pace can last a set time, after which Friday returns to the default. Unrelated to pacing lines |
| Shove | Clearing time for yourself: a fixed item of kind `shove` |
| Tentative | An item placed in a gap without committing to a time ("store run sometime this weekend"). It never anchors the plan |
| Progress | Recorded work on an item: from the timer, the evening review, a slider, a retroactive log, or an assumption |
| Review | The daily 30-second check of what actually happened today |
| Command | One action in Friday's vocabulary: `add`, `done`, `pin`, `shove`, … (section 9) |
| Actor | Who issued a command: `you` (web), `cli`, `job`, or `agent:<name>` |

---

## 2. A day with Friday

- **Morning.** A notification shows today's three big rocks: *PS5 (2 h, due Wed), Project draft (1.5 h, on track), Laundry.* Opening the app shows Now: *PS5, 10:00–12:00*, with two safe swaps underneath.
- **10:20.** You type `reading ch 4 #psych due fri ~1h` into quick-add. Chips appear as you type. Enter: the item appears in To-do under This week. A ghost shows where it will probably land, and two seconds later the solver confirms it.
- **11:00.** You'd rather do the reading now. You tap it in Now's safe swaps; the timer starts; PS5 reflows to the afternoon.
- **15:00.** Friends invite you out. You select 15:00–19:00 and press Shove. Friday says that nothing becomes late, and that PS5 moves to 20:00–22:00.
- **Evening.** A notification: *Review today (30 s).* You swipe: reading done, PS5 about half done, laundry not done. Friday asks nothing else.
- **Night.** The allocator notices the project is behind its pacing line and raises its quota for this week. Tomorrow's plan reflects it.
- **Next Monday.** You wake up sick. `friday pace easy --for 5d`. Friday previews the change (book writing paused, hard work spread evenly, heaviest day 4.5 h, every deadline still met) and you apply it. On Saturday it goes back to Normal by itself.

---

## 3. Architecture

### 3.1 Layers

One Python package, `friday`, in layers. A module imports only from its own layer or lower ones. `tests/test_layers.py` parses every module with `ast` and fails on any upward import.

```text
 5  cli/                                   Typer client. Imports only friday.api.
 4  server/                                FastAPI app, SSE, solver worker, job loop, (later) MCP.
 3  commands/ estimate/ notify/ ingest/ sync/ learn/ sim/
                                           Command implementations, estimates, notifications,
                                           outside world, learning, simulator.
 2  planner/                               The only code that turns database state into engine inputs and back.
 1  engine/  learn/                        Pure: scheduler, allocator, executor, rules, evaluator, explain;
                                           learn/: preference fitting and the supervisor's maths. No db, clock or network.
 0  core/   api/                           Time, items, recurrence, text, quick-add grammar, settings, db.
                                           api/ holds the command schemas (pydantic), shared with the CLI.
```

Extra rules:

1. `engine/` imports only `core/` modules that have no I/O (`time`, `items`, `textnorm`), the standard library, pydantic, numpy, numba and OR-Tools.
2. Within layer 3, `commands/` may import the other layer-3 packages. No other layer-3 package imports another, except that `ingest/` may use `estimate/` and `sync/google_auth`, and `sim/` may use `commands/`.
3. `cli/` imports only `friday.api`. It talks to the server over HTTP and runs on any machine.
4. Only `planner/`, `commands/` and `server/` write to the database.
5. The web app (`web/`) is a separate TypeScript project. Its only contract with Python is the OpenAPI schema the server generates.

### 3.2 Processes

| Process | What runs there |
| --- | --- |
| `fridayd` (API process) | FastAPI on uvicorn (one worker); command execution; the executor; SSE; a job thread waking every 30 s |
| Solver worker | One child process (`multiprocessing`, spawn) that receives snapshots and returns solutions. Started and supervised by `server/worker.py` |
| Web app | In development, the Vite dev server proxying `/api` and `/events` to `fridayd`. In production, built files served by `fridayd` |

### 3.3 Flows

1. **A command arrives** (web, CLI, job or agent). In one transaction, Friday validates it, applies it, writes a `command_log` row (actor, input, result, undo data) and raises the plan generation. On commit it publishes an SSE `items.changed` event.
2. **Instant feedback.** If the command affects the schedule, the executor computes a provisional placement in milliseconds. This is returned in the response and published as `plan.provisional`, and the web app draws it as ghosts.
3. **Debounce.** Three seconds after the last schedule-affecting command, the planner takes a snapshot and sends it to the worker. If a newer generation arrives while a solve is running, the worker is stopped (section 15.5) and the newer snapshot is solved instead.
4. **Plan.** The worker runs the allocator, then the scheduler (construct → repair → fallback if needed → anneal), checks the result with the evaluator, and returns it. The planner assembles blocks, costs and the change list, saves the plan as current, and publishes `plan.changed`.
5. **Jobs** (every 30 s, catching up after downtime): nightly replan, series materialization, end-of-day assumptions, notifications, backups, and (later) connectors and Google sync.

### 3.4 When something fails

| Failure | Effect | Recovery |
| --- | --- | --- |
| Server off | Web app shows its last cached plan read-only; CLI exits 2 | Missed jobs run once on start |
| Scheduler result fails the evaluator check (a kernel bug) | Current plan stays; red banner; the snapshot is saved for replay | Logged; fix and replay |
| Worker crashes | Restarted; the snapshot is retried once | Logged; banner if it fails again |
| Invalid settings change | Rejected with the field and reason; old settings stay | Fix and save again |
| Undo of a command whose rows changed since | Refused with the conflicting command named | Undo the later command first, or edit by hand |

### 3.5 Why it is built this way

| Choice | Instead of | Reason |
| --- | --- | --- |
| Three planning layers | One big model | Long horizons, fine timing and instant answers stop competing for one model's solve time |
| Solver in a worker process | Solve inside requests | The API never blocks; stale solves can be cancelled |
| SSE | Polling | Plans appear as soon as they exist; one-way push is all the app needs |
| One command registry | Hand-written routes, CLI and tools | Every interface agrees by construction; agents get exactly what you get |
| Command log with undo data | No history | Undo, audit, "what changed", agent accountability, and training data for learning |
| Settings in the database | A Python file | Editable from the app; versioned; works for a hosted service. Plugins keep code rules for you |
| React + TypeScript | Server-rendered pages | Drag, ghosts, a palette and optimistic updates need client-side state |
| SQLite (WAL) | Postgres | One user, small data, one file. Queries stay portable (section 23) |
| Energy sampler with walls | Staged CP-SAT, or penalties in a Boltzmann machine | ~15× faster plans, deterministic by step budget, every avoidable deadline met; penalties and pure Boltzmann encodings lost the deadline guarantee in research (section 10) |
| An LP for the allocator, CP-SAT for the deadline fallback | Sampling everywhere | Small exact problems where a solver is fast and provably right |

---

## 4. Repository, dependencies and code style

### 4.1 Layout

```text
friday/
  DESIGN.md  PROMPT.md  REUSE.md  PROGRESS.md  CLAUDE.md
  reference/research/             # read-only research code to port from (git-ignored; see REUSE.md)
  pyproject.toml                  # Python package, entry points `friday`, `fridayd`
  src/friday/
    core/
      time.py                     # grid, planning days and weeks, UTC <-> local
      items.py                    # item facets, presets, validation (pure types)
      series.py                   # series -> occurrences (pure)
      recurrence.py               # RRULE expansion, repeat shorthand, describe()
      textnorm.py                 # title normalization and similarity
      quickadd.py                 # quick-add grammar -> ParseResult
      dates.py                    # date, time and duration shorthand
      settings.py                 # settings models, defaults, validation
      pace.py                     # dials, paces, and how dials scale settings per day (pure)
      db.py                       # connection, migrations, small query helpers
      migrations/001_initial.sql
    api/
      commands.py                 # pydantic Input/Output per command, the verb list
      types.py                    # shared response types (Item, Block, Plan, Now, ...)
    engine/
      problem.py                  # Problem, EngineItem, Solution
      pwl.py                      # Lin, Curve, Measure
      rules/__init__.py           # Rule base, Scope, FORBID, registry
      rules/prices.py             # price and forbid rules
      rules/measures.py           # measure rules
      evaluate.py                 # independent exact evaluator: stage values, per-rule totals
      checker.py                  # every wall violation of a plan
      compile.py                  # Problem + rules -> flat arrays for the kernel
      kernel.py                   # numba: state, incremental energy, walls, the 11 moves
      construct.py                # earliest-deadline construction honouring every wall
      repair.py                   # deadline-stage repair with penalties
      cpsat_deadlines.py          # CP-SAT deadline fallback (11.10)
      sampler.py                  # annealing schedule, stage policy, chains, tabu finish, budgets
      scheduler.py                # the pipeline: construct -> repair -> fallback -> anneal
      allocator.py                # day-level LP, pacing and quotas
      executor.py                 # EDF feasibility, latest starts, slack, safe swaps, provisional placement
      explain.py                  # per-block costs, why, why-not by relocation
    learn/
      preferences.py              # Bradley-Terry fit of learned multipliers, answer noise
      state.py                    # dial-seeded hidden state: inference and the gate (opt-in)
      proposals.py                # missing-rule templates and cross-validated gain
      queries.py                  # which comparisons to ask
    planner/
      snapshot.py                 # db state -> Snapshot (frozen, picklable)
      build.py                    # Snapshot -> Problem (grid, pruning, pins, locks)
      inputs.py                   # allocator and executor inputs, over their longer spans
      assemble.py                 # Solution -> blocks, costs, change list, report
      service.py                  # replan, what_if, preview, why, why_not, triage, now
    commands/
      registry.py                 # @command decorator, context, transaction, log, undo
      items.py  pins.py  progress.py  series.py  shove.py  settings.py  review.py  queries.py
    estimate/durations.py         # length estimates and bias (section 6.6); Bayesian version in M9
    notify/                       # rules for when to notify; channels: webpush, ntfy
    sim/                          # semester generator, simulated user families, metrics
    server/
      app.py                      # FastAPI app; routes generated from the registry
      events.py                   # SSE hub
      worker.py                   # solver worker process and supervision
      jobs.py                     # job loop
      main.py                     # `fridayd` (serve, init)
    cli/
      main.py                     # Typer app generated from friday.api.commands
      render.py                   # terminal output
  web/                            # React + TypeScript (section 18)
  tests/                          # one folder per layer, plus test_layers.py, scenarios/, bench/
```

### 4.2 Dependencies

**Python 3.12+, managed with `uv`:**

| Package | Used by | Purpose |
| --- | --- | --- |
| numpy, numba | engine | the compiled scheduling kernel |
| scipy | learn | fitting the preference model |
| ortools | engine | GLOP for the allocator, CP-SAT for the deadline fallback |
| pydantic (v2) | core, api, server | settings, command schemas, validation |
| python-dateutil | core | RRULE |
| rapidfuzz | core | title similarity |
| fastapi, uvicorn | server | HTTP, OpenAPI |
| typer, httpx, rich | cli | commands, HTTP client, output |
| tomli-w | core | writing the TOML settings export (reading uses stdlib `tomllib`) |
| pywebpush | notify | Web Push (M8) |
| pytest, hypothesis, ruff | dev | tests, property tests, lint |

Later milestones add `icalendar`, `anthropic` and the Google client libraries (M10), and `mcp` (M10). Anything else needs approval.

**Web, managed with `pnpm`:** React 18+, TypeScript, Vite, TanStack Query, React Router, Tailwind CSS, shadcn/ui (Radix primitives) and `cmdk` for the palette, `openapi-typescript` for the generated client types, `vite-plugin-pwa` (M8), Vitest and Playwright. There is no calendar library: the grid is our own component (section 18.4). There is no global state library unless one is clearly needed; React state and TanStack Query come first.

### 4.3 Where to change what

| To change… | Edit |
| --- | --- |
| A preference, weight, sleep time, preset, threshold | Settings in the app, or `friday settings set` |
| How hard Friday pushes you right now | The dials, or switch pace: `friday pace …` (section 17.6) |
| A rule only you need | A Python plugin in `~/.config/friday/rules/` (section 17.4) |
| How a built-in rule computes | `engine/rules/prices.py` or `measures.py` |
| What a command does | its function in `commands/` |
| What quick-add understands | `core/quickadd.py` |
| What a screen shows | its component in `web/src/` |

### 4.4 Code style

This code will be read and edited by hand. Optimize for a reader who knows Python and TypeScript but did not write the code.

- **Names do the explaining.** `remaining_minutes`, `latest_start`, `is_safe_swap`, not `rm`, `ls`, `chk`. Functions are verbs, values are nouns.
- **Short functions with one job.** If a function needs a comment to separate its parts, split it.
- **Visible data flow.** Plain functions and dataclasses. Pass what a function needs, and return what it produces. No hidden state, clever metaprogramming, or inheritance trees. The only registries are rule types and commands.
- **Type hints everywhere** in Python, and `strict` TypeScript.
- **Comments only for why.** Plain sentences, the way you'd explain it to a friend. Never restate the code. No banners, emoji, or "This function…" openers. A docstring is one line, and only when the name isn't enough.

  ```python
  # Bad
  # This function calculates the remaining minutes for the item by subtracting progress.
  def remaining(item, progress): ...


  # Good
  def remaining_minutes(item: Item, progress: list[Progress]) -> int:
      # Timer sessions replace the planned block they overlap, so don't count both.
      ...
  ```

- **Files under ~400 lines.** Split by responsibility, not by layer of abstraction.
- **Tests read as examples.** A test name says the behaviour (`test_rest_day_is_used_when_it_is_the_only_time_before_the_deadline`).
- **No dead flexibility.** No options nobody uses, and no interfaces with one implementation.

---

## 5. Time model

All timezone logic lives in `core/time.py`.

- **Storage.** Timestamps are UTC ISO strings ending in `Z`, to the minute. Series start times and per-occurrence edits are stored in local time, so repeats keep their wall-clock time across daylight-saving changes. The API speaks local `YYYY-MM-DDTHH:MM` and converts at the edge.
- **Units.** A unit is 15 minutes. Flexible durations are whole units, with input rounded up (`40m` → 3 units). Fixed items are exact to the minute.
- **Planning day and week.** Day from `day_start` (default 04:00) to the next 04:00; week from `day_start` on `week_start` (default Monday). A slot belongs to the planning day containing its start, so a daylight-saving change at 02:00 falls in the previous date's planning day.
- **The scheduler grid.** It starts at now, rounded up to the next unit boundary, and covers planning days 0 … H−1 (`horizon_days`, default 14).
  - Days 0 … F−1 (`fine_days`, default 7) use 15-minute slots.
  - Days F … H−1 use 30-minute slots; the zone boundary is at `day_start`.
  - Slots are stepped in UTC, and every slot has `index`, `start_utc`, `end_utc`, `units` (1 or 2), `day`, `weekday`, `local_minute` and `week`. Index S is the overflow slot.
  - A daylight-saving day has 4 more or 4 fewer fine slots. A zone whose offset is not a multiple of 15 minutes is rejected.
- **The allocator grid** is one bucket per planning day, from day 0 to `allocator_weeks` × 7 (default 12 weeks).
- **Helpers:** `to_utc(local)` (a local time inside a DST gap moves forward; an ambiguous one takes the first occurrence), `planning_date(utc)`, and `night_utc(date)` / `wake_utc(date)` (that night's bedtime and wake as UTC).

`fine_days`, the slot lengths and `horizon_days` are settings. Daylight-saving days must be handled (they were simplified away in the research), and the kernel must be tested on them.

---

## 6. Items

### 6.1 Facets

Every item has all eight facets. Most have defaults, so a typical item sets two or three.

| Facet | Field(s) | Options | Notes |
| --- | --- | --- | --- |
| When | `when` | `fixed` · `window` · `anytime` | `fixed`: `start_utc`, `end_utc` exact. `window`: `release_utc` (null = now) and `due_utc` (null = no deadline). `anytime`: neither |
| Amount | `amount` | `fixed` · `elastic` · `target` · `open` | `fixed`: `duration_units`. `elastic`: `min_units`, `ideal_units`, `max_units`. `target`: `target_units` and `cap_units` (default ⌈1.5 × target⌉) inside the window. `open`: no amount; `daily_ceiling_units` (default 12 = 3 h) caps it per day. Open items fill free time, never overflow and are never late (section 12.2, `open_value`) |
| Shape | `shape`, `min_chunk_units`, `max_chunk_units`, `chunk_cost`, `spread` | `one_sitting` · `split`; spread `none` · `spread` · `cluster` | `split` items may have a minimum chunk (default 2 units = 30 min) and a maximum. `chunk_cost` (0 … 1, default from the preset) is the size-proportional cost of each extra chunk: with 0.1, each extra chunk of a 4-hour item costs 0.4 × the `chunk_cost` rule's weight in points. `spread` spreads work across days; `cluster` keeps it to few days |
| Firmness | `firmness`, `importance` | `hard` · `soft` · `none`; importance 1–5 | `hard` deadlines are settled in the deadlines stage, guarded by walls (11.4) and watched by the executor. `soft` lateness is a preference. `none` means the due date is only a pacing target |
| Value | `neglect_carry` | 0 … 1 | Targets only: the share of last window's shortfall added to this window's target (default 0.5) |
| Relations | `parent_id`; `dependencies` table | — | Projects are trees. A dependency says B may only start once a fraction of A is done, after a lag (section 6.4) |
| Context | `energy`, `location` | energy `deep` · `light` · `physical` · `social` · null; location text | Energy drives deep-run limits and energy prices. Location is stored but not used by the engine yet |
| Certainty | `certainty` | `planned` · `tentative` | `tentative`: placed in a real gap inside its window, never anchors the plan, never counted as moved; made real by `start` or a matching shove (section 15.4) |

Fixed items also have `event_kind` (class, meeting, shove, other → buffers from settings) and `blocks_time` (0 = shown but schedulable over).

### 6.2 Presets

Presets live in settings as data: name → facet defaults. You can edit them and add your own. The built-in set:

| Preset | When | Amount | Shape | Firmness | Energy | Other |
| --- | --- | --- | --- | --- | --- | --- |
| Assignment | window | fixed | split, min 30 min | hard | deep | importance 3 |
| Project | window | fixed | split, min 60 min, cluster | hard | deep | pacing linear; may have children |
| Reading | window | fixed | split, min 30 min | soft | light | |
| Exam prep | window | fixed | split, min 60 min, spread (chunk cost 0.05) | hard | deep | usually `before:` an exam |
| Class | fixed | — | — | — | — | event_kind class; usually a series |
| Exam | fixed | — | — | — | — | event_kind exam (15 min kept free before); prep comes `before:` it |
| Meeting | fixed | — | — | — | — | event_kind meeting |
| Appointment | fixed | — | — | — | — | event_kind other |
| Event | fixed | — | — | — | — | event_kind other; any other fixed time |
| Errand | window | fixed | one sitting | none | physical | |
| Chore | window | fixed | one sitting | none | physical | |
| Routine | window | elastic | one sitting | none | — | e.g. meals: lunch 11:30–14:30, 20–45 min; not work, so load rules leave it out (M16) |
| Habit | window | fixed | one sitting, spread | none | null | usually a series with a count per window |
| Goal | window | target | split, min 30 min | none | deep | weekly series; neglect carry 0.5 |
| Side project | anytime | open | split, min 45 min | none | deep | a book, a personal project; fills free time; daily ceiling 3 h |
| Maybe | window | fixed | one sitting | none | null | certainty tentative |

### 6.3 Series and occurrences

A **series** creates items. It stores:

- a template (any facets);
- an RRULE with a local `dtstart`;
- `per_window`, a count (default 1);
- window offsets.

**Materialization.** A job creates occurrences from today to `materialize_days` ahead (default 120). It runs nightly and whenever the series changes.

- Each occurrence is an ordinary `items` row with `series_id`, `occurrence_date` and `occurrence_n` (1 … per_window). These are UNIQUE together.
- Fixed series give fixed items at the rule's local time.
- Flexible series give window items. With no offsets, each window is one period: release at the occurrence, due at the next one, so a daily series means "once that day" and a weekly one "once that week". A rule that names weekdays (`mon,wed,fri`, `sun`) means those days: each window is that one day, so "gym every mon, wed and fri" isn't planned on Tuesday (M15). With offsets, release = occurrence + `release_offset_min` and due = occurrence + `due_offset_min`. With no time given, the occurrence time is `day_start`, so the window is exactly one planning day or week.
- A target typed with no window and no repeat ("MCAT practice /goal ~6h") is a weekly series, its length the target (M15).
- No backfilling: occurrences whose due is before the series was created are not made.
- A flexible window that opened before today and is still open comes in: a weekly problem set added on Wednesday,
  its week starting Tuesday, is due next Tuesday (M16). Yesterday's daily window has closed and doesn't.
- `series_delete` deletes a repeat you made: its undone occurrences go, what you did stays as history (no longer
  linked). An imported calendar repeat is switched off instead (`series_stop`), so the calendar doesn't offer it
  again. An imported repeat's own fields (tag, kind, importance, notes) can be changed with `series_edit`; its
  times follow the calendar (M16).
- `per_window` = 3 with a weekly rule gives three items per week sharing that week's window: "gym 3× a week". Add `spread` to keep them on different days.
- Occurrences keep the series' plain title, so rules can target it.
- An occurrence of a flexible series whose preset says firmness `none` is `soft`: its window is when it belongs, so finishing late costs `soft_late` instead of nothing (otherwise a weekly chore could drift into the next week's).

**Writing a repeat.** Nobody writes RRULEs by hand. The shorthand (quick-add `every …`, the CLI `--every`, the app's repeat picker) maps to an RRULE, and `describe(rrule)` shows any rule in words:

| Shorthand | RRULE | Shown as |
| --- | --- | --- |
| `mon` | `FREQ=WEEKLY;BYDAY=MO` | Every Monday |
| `mon,wed,fri` | `FREQ=WEEKLY;BYDAY=MO,WE,FR` | Every Mon, Wed and Fri |
| `weekdays` | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` | Every weekday |
| `day` | `FREQ=DAILY` | Every day |
| `week` | `FREQ=WEEKLY` (on the start's weekday) | Every week |
| `2w thu` | `FREQ=WEEKLY;INTERVAL=2;BYDAY=TH` | Every other Thursday |
| `month 15` | `FREQ=MONTHLY;BYMONTHDAY=15` | Monthly on the 15th |
| `… until 12-11` | `…;UNTIL=<that date, 23:59:59 local>` | … until Dec 11 |
| `rrule:…` | as written | as `describe` renders it |

Rules are evaluated in local time with `dateutil.rrule`, so "every Monday 08:00" stays at 08:00 across daylight-saving changes.

**Editing.**

- *Edit one occurrence:* edit the item row and set `detached = 1`, so regeneration leaves it alone.
- *Skip one:* set `status = 'skipped'`.
- *Edit from a date on:* the old series gets `UNTIL` the day before. A new series starts at that date. Undone, undetached occurrences from that date on are deleted and regenerated. Detached ones are kept, and the response lists them.
- *Stop:* `active = 0`, and undone future occurrences are deleted.

### 6.4 Relations

`dependencies(item_id, depends_on_id, fraction, lag_min)`: the item may not start until `fraction` (default 1.0) of `depends_on` is done, plus `lag_min`.

- Cycles are rejected when the dependency is added.
- If `depends_on` is fixed, the planner turns the dependency into a release time (item after an event) or a due time (`before:`, which stores the reverse dependency).
- An item whose dependency cannot be met inside the horizon overflows. It is reported as "blocked by <title>", not as late work of its own.

Projects: an item with children has no amount of its own. Its due date is the latest-finish date for its children; a child with no due date inherits it. Its progress is the sum of its children's.

### 6.5 Validation (in `core/items.py`, used by every command)

- `fixed` needs start < end.
- `window` with `hard` firmness needs `due_utc`.
- `target` needs `release_utc` and `due_utc` (the window).
- `open` excludes `due_utc`, `firmness` other than `none`, `one_sitting` and dependencies on it (nothing can wait for an item that never finishes).
- `elastic` needs min ≤ ideal ≤ max.
- `min_chunk_units` ≤ the item's amount.
- `one_sitting` excludes `max_chunk_units`.
- `parent_id` must not create a cycle.
- `tentative` needs a window.
- Every violation is a `ValueError` naming the field. The API returns it as 400 with that field.

### 6.6 Titles and length estimates

**Normalizing a title** (`core/textnorm.py`). `norm(title, area=None)` turns a title into a list of plain words in seven fixed steps:

1. Unicode NFKC, casefold, strip accents.
2. Insert a space at every letter–digit boundary: `ps4` → `ps 4`, `cs1110` → `cs 1110`.
3. Every character that isn't a letter or digit becomes a space; split on spaces.
4. If the item has an area, remove the word sequence equal to the normalized area name (`cs 1110`), since the area is compared separately.
5. Replace each whole word found in `text.abbreviations` with its phrase (`ps` → `problem set` never touches `psych`). The same table holds synonyms you want treated as equal.
6. Number words one … twenty become digits. A Roman numeral i … xx becomes digits only directly after a word in `text.numbered_words` (`part ii` → `part 2`, but the `i` in `what i learned` stays). Leading zeros are dropped.
7. Drop the words in `text.stopwords` (default: a, an, the, of, for, on, to).

| Typed (area CS 1110) | Words |
| --- | --- |
| `PS4 (CS 1110)` | problem set 4 |
| `Problem Set #4` | problem set 4 |
| `HW IV – Part ii` | homework 4 part 2 |
| `Reading for Week 03` | reading week 3 |

Two forms come from the words. **Identity text** keeps every word; duplicate checks use it, so problem set 3 and 4 stay different. **Type text** drops numbers; estimates use it, so problem set 3 and 4 count as the same kind of work. **Similarity** is rapidfuzz `token_set_ratio / 100` (1.0 when one set of words contains the other). Rule scopes compare titles by identity text, so `title = "shower"` matches "Shower", "shower!" and every occurrence of a daily Shower series.

**Estimating a missing length** (`estimate/durations.py`). History = completions in the same area (or the same preset if the item has no area) in the last `estimate.window_days` (365) whose actual source is `timer`, `review` or `retro`. The first step that gives a value wins:

1. **Similar past items.** Score = type-text similarity, plus `estimate.area_bonus` (0.2) if the area matches. Keep scores ≥ `min_similarity` (0.6), take the best `k` (5), ties to the most recent. With at least `min_samples` (3), the estimate is the **median** of their actual minutes.
2. **Group median.** The median of the whole history, if it has at least `min_samples` rows.
3. **Preset default** length.

The result is rounded up to whole units. `estimate_detail` stores the method, every past item used with its time and score, the median, and the range, so the app can say *"3.5 h (range 3–4 h), from 3 similar: PS1 3.5 h, PS2 4 h, PS3 3 h"*. `friday_estimate_units` is computed for every new item, even when you give a length, so Friday's own accuracy can be measured.

**How your estimates run.** Per area, take the last `bias_window` (20) completions that have both your typed estimate and a real actual time. Ratio = actual ÷ your estimate. With at least `bias_min_samples` (5) ratios, let m be the median and consistency the share of ratios on the same side of 1 as m. If m > `bias_threshold` (1.15) or m < 1 / 1.15, and consistency ≥ `bias_consistency` (0.7), quick-add suggests your estimate × m (rounded up) next to the length chip. Accepting sets `duration_source = estimate` and keeps your typed value in `your_estimate_units`. Ratios always use what you typed, never an accepted correction, so corrections don't feed back into the ratio. Learning (section 21) replaces this in M9.

---

## 7. Data model

One SQLite file, WAL, foreign keys on, `STRICT` tables, `CHECK` on every enum. Numbered migrations, version in `PRAGMA user_version`. No ORM: dataclasses in `core/` and plain SQL in the modules that own each table. **Every table has `user_id INTEGER NOT NULL DEFAULT 1`** (section 23).

| Table | Key columns | Notes |
| --- | --- | --- |
| `users` | id, name, timezone | One row in the personal build |
| `areas` | id, name, color, archived | |
| `series` | id, template (JSON facets), rrule, dtstart_local, per_window, release_offset_min, due_offset_min, active, timestamps | |
| `items` | id, title, notes, preset, area_id, tags (JSON), parent_id, every facet column from 6.1, event_kind, blocks_time, buffer_before_min, buffer_after_min, status (`todo` `done` `dropped` `skipped`), series_id, occurrence_date, occurrence_n, detached, duration_source (`you` `estimate` `preset`), your_estimate_units, friday_estimate_units, estimate_detail (JSON), timestamps, completed_utc | Fixed items, flexible items and shoves all live here |
| `dependencies` | id, item_id, depends_on_id, fraction, lag_min | |
| `pins` | id, item_id, start_utc, end_utc, kind (`preferred` `locked`), created_utc | Your placements. They survive replans; ids are stable |
| `plans` | id, created_utc, generation, reason, status (`current` `replaced` `preview` `waiting`), stage_values (JSON), solve_seconds, report (JSON) | Only one current plan (partial unique index) |
| `blocks` | plan_id, item_id, start_utc, end_utc, cost (JSON), tentative | Key `item_id@start_utc`. No state column: what happened lives in `progress` |
| `progress` | id, item_id, start_utc (null for slider), end_utc, minutes, source (`timer` `review` `slider` `retro` `assumed`), block_key, created_utc | Section 8 |
| `timer` | item_id, start_utc | At most one row |
| `reviews` | date, submitted_utc | Which days were reviewed |
| `completions` | item_id, area, preset, norm_title, your_estimate_units, friday_estimate_units, actual_minutes, actual_source, completed_utc | Copied at completion so history survives later edits |
| `day_overrides` | date, bedtime, wake, margin_min, cap_hours | |
| `pace_periods` | id, pace_name (null = custom), dials (JSON), start_date, end_date (planning dates, inclusive; null = until changed), created_utc | Section 17.6. At most one period covers any day; days with none use the default pace |
| `settings` | key, value (JSON), version, updated_utc | Section 17 |
| `command_log` | id, at_utc, actor, command, input (JSON), result (JSON), undo (JSON), idempotency_key (UNIQUE), undone_by | Section 9 |
| `notifications` | id, kind, item_id, dedup_key (UNIQUE), channel, sent_utc, acted | Section 20 |
| `comparisons` | id, asked_utc, plan_a (JSON blocks), plan_b, features_a (JSON), features_b, answer (`a` `b` `skip`), answered_utc, source (`question` `drag`), dials (JSON) | Section 21.2; drags are stored here too, with the plan before and after |
| `learned_profile` | version, created_utc, theta (JSON), answer_noise, state (JSON), proposals (JSON), wall_decisions (JSON), evidence (JSON), status (`suggested` `active` `rejected`) | Section 21.8 |
| `checkins` | date, state (`tired` `normal` `motivated`) | Only when state inference is on |
| `push_subscriptions` | id, endpoint, keys (JSON), created_utc | M8 |
| `job_runs` | name, last_run_utc, last_status, last_error | |
| `kv` | key, value | Plan generation, last solve, last push, etc. |

Ingestion and Google tables (`raw_items`, `suggestions`, `connector_state`, `google_events`) arrive in M10 with their own migration.

---

## 8. Progress, drift and review

Progress is recorded, never inferred silently. `remaining(item)` = amount − progress inside its window. Progress comes from:

| Source | When written |
| --- | --- |
| `timer` | `stop` (or `done` while running) writes the session |
| `review` | The evening review: done (the block's minutes), partial (slider share), or not done (nothing) |
| `slider` | `progress` command: "about half done" sets total progress to that share of the amount |
| `retro` | `log` command: "I did X from 19:00 to 20:30" |
| `assumed` | End of planning day: for unreviewed past blocks of that day, written per `planner.assume_unreviewed` (`done` default, or `not_done`) |

Rules:

1. **During the day**, before the review, unreviewed past blocks of today count as progress when `assume_unreviewed = done`. They are not written yet, so the review can still correct them. A timer session that overlaps a block replaces that block.
2. **A running timer** is an overlay on the plan, never a change to it (M16, rebuilt). `start` records the moment to the second and replans nothing; the bar ticks from it, and the calendar draws the session from its start to now. A replan that happens meanwhile (another command, a block boundary) holds the timed item at now for `timer_hold_min`: those slots are `held`, which `minimize_changes` weighs like a preferred pin (×`preferred_multiplier`) without their being one, so no block edge splits the block around them; and a hold's worth of the item stays remaining however long the timer has run, so timing past its length extends it in the plan and reflows what came after (scenario 21). Nothing is locked: the earlier lock split the block around it into pieces, was dropped whenever it couldn't fit, and every Start replanned. `stop` writes the session to the nearest minute (under half a minute, nothing, and it says so) and replans, since what's left changed. `done` while timing stops it first.
3. **Not started?** The block was never recorded. Remaining is unchanged, and the next replan places it later. Nothing needs confirming.
4. **The review** lists today's past blocks, timer sessions and anything logged. You set each to done, partial or not done, and can add things that happened. Submitting writes `review` rows, replaces any `assumed` rows for that day, and marks the day reviewed.
5. **Completion.** An item whose remaining reaches 0 is shown as "finished?" in the review and in its To-do row. You confirm with one tap (`done`). Unconfirmed, it stops being scheduled, and the next review asks again.
6. `done` writes the `completions` row. Actual time is the timer total if there is any, else the review and retro total, else the planned total marked `assumed`. Only `timer`, `review` and `retro` sources are learned from.
7. **Open items** have no remaining amount. Their progress is still recorded (it feeds stats and today's daily ceiling), and they stay in the plan until you mark them done or drop them.

---

## 9. Commands

### 9.1 The registry

Every action is a command, defined once:

```python
@command("pin", mutates=True, affects_plan=True)
def pin(ctx: Ctx, inp: PinInput) -> PinOutput: ...
```

- `PinInput` and `PinOutput` live in `api/commands.py`, so the CLI can import them.
- `ctx` carries the db connection (inside the command's transaction), the clock, the actor, settings, and an undo recorder.
- Queries are registered the same way with `mutates=False`.

From the registry:

- **HTTP:** `POST /api/c/<name>` for commands and `GET /api/q/<name>` for queries. Both are typed in OpenAPI.
- **CLI:** one Typer command per entry (section 19).
- **MCP (M10):** one tool per entry, with read-only and read-write scopes.

### 9.2 Every mutating command

- Runs in one transaction. On success it appends `command_log` with the actor, input, result and undo data.
- **Undo data** is the list of rows before the change (inserts → delete by id; updates → previous row; deletes → full row).
- `undo {command_id}` applies it if none of those rows changed since. Otherwise it is refused, naming the later command. Undo is itself a command and can be undone.
- **`preview: true`** runs the command, computes its effect (provisional placement and changed items), and rolls back. `preview: "full"` also runs a full solve in the worker and returns the change list. Agents and the palette use this to show "this would move PS4 to Thu".
- **`idempotency_key`** (optional): a repeat with the same key returns the stored result without running again.
- **Actor** comes from the request: web → `you`, CLI → `cli`, an MCP token → `agent:<name>`, jobs → `job`.
- If `affects_plan`, it raises the plan generation and returns the executor's provisional plan diff.

### 9.3 The vocabulary

| Command | Does |
| --- | --- |
| `add` | Create an item from fields or from a quick-add line (`text`) |
| `edit` | Change an item's fields (`from_date` for series edits) |
| `drop` · `reopen` | Drop an item; undo a drop or a done |
| `done` | Complete an item (optional actual minutes) |
| `progress` | Set progress as a share of the amount |
| `start` · `stop` | Timer. `start` also pins the item now (section 8 rule 2) |
| `log` | Record past work, or something that happened (creates a fixed item if needed) |
| `pin` · `unpin` | Place an item at a time (preferred or locked), or remove its pins ("let Friday decide") |
| `shove` · `unshove` | Clear time (section 15.4) |
| `depend` · `undepend` | Add or remove a dependency |
| `series_add` · `series_edit` · `series_stop` · `skip` | Repeats |
| `area_add` · `area_edit` | Areas |
| `template_apply` · `template_save` | Make a project from a template; save a project's steps as one |
| `review_submit` | Submit a day's review |
| `settings_set` | Change one settings key (validated, versioned) |
| `pace` | Switch to a saved pace, or set dials directly, from now for a duration (`for 5d`, `until sun`) or until changed. Switching to the default pace ends the current period (section 17.6) |
| `pace_save` · `pace_delete` | Create or edit a saved pace (from given dial values, or from the dials in effect now); delete one |
| `replan` | Solve now |
| `resolve` | Settle a plan waiting on a lock conflict: unlock the listed pins (they become preferred) and replan, or with none listed accept it as is (section 15.3) |
| `compare_answer` | Answer a comparison: `a`, `b` or `skip` (21.4) |
| `proposal_answer` | Accept or refuse a proposed rule (21.5) or a wall question (21.6) |
| `checkin` | Record today's state (only when state inference is on) |
| `learn_apply` · `learn_reject` · `learn_reset` | Approve or reject suggested weight changes; reset a learning module |
| `undo` | Undo a command |

| Query | Returns |
| --- | --- |
| `now` | Current item, next item, safe swaps, alerts, and fits for the current gap (section 14) |
| `fits` | Items that fit a given gap, safe, best first |
| `plan` | Blocks and fixed items in a range, with day totals |
| `items` | Filtered item list with remaining, slack, scheduled chip and status |
| `item` | One item with blocks, progress, dependencies and estimate detail |
| `parse` | Quick-add parse result with spans for chips |
| `why` · `why_not` · `changes` · `preview_weights` · `rule_totals` | Explanations (section 16) |
| `triage` | Options when work does not fit |
| `review` | Today's review sheet |
| `paces` | Saved paces, the default, the dials in effect now, and the current period's end |
| `projects` | Open projects with their descendants, rolled-up progress, planned finish and on-track status |
| `load` | Planned hours against room, week by week: the plan inside the horizon, the allocator's forecast past it |
| `questions` | Pending comparisons, rule proposals and wall questions for the review |
| `learning` | The learned profile: multipliers with evidence, answer noise, state and gate status, proposals, digest |
| `stats` · `status` · `settings` · `log_list` | Insight and system |

### 9.4 Quick-add grammar (`core/quickadd.py`)

One line becomes an `add` input. Tokens may appear in any order, and what remains is the title.

| Token | Meaning | Example |
| --- | --- | --- |
| `#name` | area (a new name is shown as "new area") | `#cs1110` |
| `+tag` | tag | `+reading` |
| `due D` / `by D` | due date (no time = 23:59) | `due tue 5pm` |
| a bare `D` with no time | due that day, as an errand | `groceries sat` |
| `from D` | release | `from mon` |
| `at D` [`for DUR`] | fixed time; a date with a time needs no `at`, and a bare length after it needs no `for` | `at fri 3pm for 1h`, `sat 3pm 30m` |
| `~DUR` / `~DUR-DUR` | length / elastic range (a bare `2h` is a length too) | `~3h`, `~20m-45m`, `2h` |
| `open` (last word) | an open item, preset Side project | `read dune open` |
| `every R` [`Nx`] | series; count per window | `every week 3x`, `every mon wed fri` |
| `Nx a week` / `N times a week` / `twice a week` | weekly series, N per week | `gym 3x a week` |
| `!N` / `!high` / `!low` | importance | `!4` |
| `@deep` `@light` `@physical` `@social` | energy | |
| `after:X` / `before:X` | dependency on an item by title or `T12` | `after:"PS4 draft"` |
| `/preset` | preset | `/errand` |
| `maybe` | tentative | `store run maybe sat-sun ~2h` |
| `one-sitting` / `split` | shape | |

Forms (`core/dates.py`, parsed on the server against its own clock and timezone; the CLI sends text):

| Kind | Forms | Meaning |
| --- | --- | --- |
| Date | `today`, `tomorrow` (`tmrw`), `mon` … `sun` (`tues`, `thurs`), `+3d` / `in 3d`, `10-14`, `10/14`, `10/14/26`, `oct 14`, `2026-10-14`, `next week`, `next fri`, `eow`, `eom` | A weekday is its next occurrence, or today if today is that day. `MM-DD`, `MM/DD` and `oct 14` are the next occurrence. `next week` = next Monday, `next fri` = that day of next week, `eow` = Sunday, `eom` = the month's last day |
| Time | `15:00`, `3pm`, `9:30am`, `noon`, `midnight` (23:59) | Joined to a date with a space, `@` or `at`: `fri 3pm`, `10/30 at 9am` |
| Time range | `3-4pm`, `7:30pm-9pm`, `10:10-11:25` | A fixed item's start and end; the start takes the end's am/pm (`11-1pm` is 11 to 1) |
| Due with no time | — | 23:59 local |
| Length | `30m`, `90m`, `1h`, `1.5h`, `1h30m` | Flexible items round up to 15 min; fixed items are exact |
| Repeat | the shorthand in 6.3 | |

The result is a `ParseResult`: input fields, a span per recognized token (for chips), and warnings (ambiguous date, unknown dependency). With no preset given, one is inferred from the tokens (`at` → Event, `every` with a fixed time → Class, else Assignment if `due`, else Errand — a bare day too). A due you give makes even an errand's deadline hard, unless you set the firmness. No length → the estimator, else the preset default.

---

## 10. Engine overview

The engine is pure: frozen inputs in, a solution out. It never reads the database, the clock or the network. Its parts:

| Part | Horizon | Resolution | Answers | How |
| --- | --- | --- | --- | --- |
| Allocator (section 13) | `allocator_weeks` (12) | one bucket per day | How many hours of each item go on which day; weekly quotas; pacing | A small LP, ~0.2 s |
| Scheduler (sections 11–12) | `horizon_days` (14) | 15 min (days 0–6), 30 min after | Exactly when, under every rule | **An energy sampler with walls**: construction, repair, simulated annealing (section 11) |
| Deadline fallback (11.10) | `horizon_days` | as the scheduler | The least-late plan when construction and repair leave lateness | CP-SAT on the deadlines stage only |
| Executor (section 14) | until the latest hard deadline | exact minutes | What now; is this deviation safe; slack; instant provisional placement | Earliest-deadline-first, milliseconds |
| Evaluator (11.12) | — | — | The exact stage values, per-rule totals and hard-rule violations of any plan | Plain Python, independent of the scheduler |

Inputs are frozen dataclasses built by the planner. They can be pickled, so they cross into the worker unchanged.

**Why a sampler and not CP-SAT.** A faithful staged CP-SAT build of this problem missed its speed targets by 2–9× (cold p90 20–31 s, warm 18–26 s), was not deterministic with several workers, and on a busy laptop met avoidable deadlines on as few as 30% of instances. The sampler with walls plans a week in about 1.3 s (p90 2.9 s), replans in under 1 s, meets every avoidable deadline in every experiment, and ties or beats CP-SAT given 30 s on every comparable stage. Solvers stay only where they are exact and needed: an LP for the allocator, and CP-SAT for the deadline fallback in overloaded weeks. The research behind these numbers compared four representations (a strict Boltzmann-machine/QUBO encoding, slot assignment with penalties, slot assignment with walls, CP-SAT hybrids); only walls kept the deadline guarantee.

---

## 11. Scheduler: an energy sampler with walls

The scheduler holds a plan as "which item owns each slot". Every rule from section 12 is compiled into arrays, so the cost of any change to the plan can be computed incrementally and exactly. Hard rules are **walls**: a move that would break one is never taken. A plan is found in four steps: construct a start plan that honours every hard rule, repair it if it is late, fall back to CP-SAT's deadline stage if lateness remains, then anneal.

### 11.1 Inputs (`engine/problem.py`)

**EngineItem**, one per flexible item being scheduled:

| Field | Meaning |
| --- | --- |
| `key` | `item:42` |
| `title`, `area`, `tags`, `preset`, `energy`, `importance`, `firmness` | Copied from the item (for scopes and prices) |
| `amount` | `fixed`, `elastic`, `target` or `open` |
| `daily_ceiling` | Open: units per day, minus today's progress for day 0 |
| `need` | Fixed: remaining units |
| `min`, `ideal`, `max` | Elastic: in units, minus progress (not below 0) |
| `target`, `cap`, `progress` | Targets: units in the window, including neglect carry |
| `release_utc`, `due_utc`, `window_is_hard` | `window_is_hard` is true for tentative, elastic and target items: they may not pass their window end |
| `shape`, `min_chunk`, `max_chunk`, `chunk_cost`, `spread` | As in 6.1 (chunks in units) |
| `size_hours` | Full amount in hours (for size-proportional costs) |
| `tentative` | Excluded from `minimize_changes` and from change lists |
| `allowed` | Sorted slot indices it may use, after pruning |
| `locked`, `preferred` | Slots from its pins |
| `current` | Slots it holds in the current plan |
| `depends_on` | List of (key, fraction, lag_units) for dependencies on flexible items |
| `quotas` | Week key → units, from the allocator |

**Problem** = the grid, the items, the fixed occurrences in the horizon (title, kind, tags, start, end, buffers), one `Night` per planning day (bedtime, wake, margin, debt multiplier), the day caps in units, the rules, the energy map, the learned weight multipliers (section 21), and one `DayScales` per planning day: the factors the day's dials produce (section 17.6). Rules read dial effects only through `problem.scales[day]`, never the dials themselves, so the mapping from dials to behaviour lives in one place (`core/pace.py`).

### 11.2 Pruning (by the planner)

Slot s is removed from item i's allowed slots if:

1. it starts before i's release;
2. `window_is_hard` and it starts at or after i's due;
3. it overlaps a fixed item that blocks time, buffers included;
4. it lies in a protected sleep core;
5. it is locked to another item;
6. an applicable rule's `forbids(i, s)` is true.

Locked slots are always kept. Pruning is the first wall: no move ever places an item outside its allowed slots.

### 11.3 State

- `owner[s]` ∈ {−1} ∪ items (int16) for every slot s of the grid; −1 is free. "One thing per slot" holds by construction.
- A **chunk** is a maximal run of consecutive slots with the same owner. "Consecutive" means consecutive in time, across the 15/30-minute zone boundary.
- `placed(i)` = Σ units(s) over i's slots. **Overflow** is derived, never chosen: `over(i) = max(0, need(i) − placed(i))` for fixed-amount items.
- Every move and every count works in **units**, not slots: a 30-minute slot is 2 units. Counting slots instead silently traps work in the fine zone.

### 11.4 Walls (the hard rules)

A plan is **valid** when it breaks none of these. The checker (`engine/checker.py`) lists every violation of any plan; the kernel re-checks only the items a move touches (and their dependents) and rejects the move if any check fails.

| # | Wall | Rule |
| --- | --- | --- |
| W1 | One thing at a time | By construction of `owner` |
| W2 | Allowed slots | i only in `allowed(i)` (11.2) |
| W3 | Locks | Every locked slot of i is owned by i |
| W4 | Amounts | Fixed: `placed ≤ need + 1` (the extra unit lets a 30-minute slot hold a 15-minute remainder). Elastic: `placed ≤ max`. Target: `placed ≤ cap`. Open: per day, `placed ≤ daily_ceiling` |
| W5 | Daily cap | Per planning day, total units of flexible work ≤ the day's cap |
| W6 | One sitting | At most one chunk, and either the whole remaining amount or nothing |
| W7 | Chunk length | Every chunk of a split item is between `min_chunk` and `max_chunk` units (a chunk shorter than the minimum is allowed only when it is the item's whole remaining amount) |
| W8 | Dependencies | B may own a slot starting at t only if, by t − lag, A's placed units plus progress reach ⌈fraction × total_A⌉ |
| W9 | Protected deadlines | An item that is complete and on time in the start plan is **protected**: it may only use slots ending by its due, and may never lose units |

W9 is what makes the deadline guarantee monotone: once the start plan has an item on time, no later step can make it late. Items late at the start are not protected; their lateness is the deadlines stage of the energy, weighted so heavily (11.5) that moves can only shorten it.

### 11.5 Energy

**Compiled model** (`engine/compile.py`). The problem is flattened into arrays once per solve:

- per-stage price tables `price[k, i, s]` (points per slot, from every price rule, already × hours(s) and × `scale`), and overflow prices per unit;
- every measure (hinge rule) as a sparse linear expression over: units of item i in slot s, chunk-start indicators, overflow, and "any of group g on day d" indicators, each with its convex hinge curve. Coefficients are integers, rounded exactly as section 12 rounds them;
- per-rule copies of the price tables and measure lists, for explanations;
- the wall data: allowed slots, locks, windows, chunk limits, one-sitting flags, dependency lag tables, day caps, protected items.

**Stage values.** `V_k(x)` is the exact integer value of stage k (deadlines, wellbeing, preferences): the prices of occupied slots, plus overflow prices, plus the hinge costs of the stage's measures. It equals what the evaluator (11.12) computes for the same plan, to the integer.

**Search energy.** `E(x) = Σ_k w_k · V_k(x)`. The stage weights depend on the phase of the stage policy (11.8): `w = (10⁶, 1000, 1)` in the main phase.

**Incremental deltas.** A slot changing owner updates the prices of that slot, every measure the slot appears in (with the change in hinge cost), the chunk-start indicators of the two neighbouring slots, the any-group counts and overflow. A move's Δ is the sum. **Exactness is an invariant, enforced by tests**: after any sequence of random moves of every kind, the kernel's stage values equal `evaluate()` and its violation counts equal `check()` (24.1).

### 11.6 Start plan, repair and the deadline fallback

1. **Construct** (`engine/construct.py`, under 50 ms at 150 items).
    - Order items by earliest effective deadline. A dependency source inherits the earliest deadline of its dependents, and sources are placed before the items that depend on them.
    - Place each into the earliest free slots that honour every wall: windows, the day cap, chunk minimums and maximums (keeping legal remainders), one-sitting runs, dependency readiness. Hard-deadline items use on-time slots first.
    - Elastic items are placed too, after hard ones, by their window's end: as long as fits under their max, at least a chunk (M16; a meal left for the sampler to grow from nothing in a narrow gap between classes was often never found). An elastic item kept from the previous plan stays as it is. Target and open items start empty; the sampler places them.
    - **Warm start:** with a previous plan, every block still allowed is kept and only missing amounts are placed.
    - If locks make construction leave violations, those locks become preferred pins (the lock checks in 15.2 do the same) and construction reruns.
2. **Repair** (`engine/repair.py`), only if the start plan has late work: the sampler on the deadlines stage alone, with walls replaced by penalties of 10⁹ so it can pass through invalid states, for `engine.repair_steps` (400k) proposals. The best **valid** state seen is kept if it is less late.
3. **Deadline fallback** (11.10), only while lateness remains. The order depends on size:
    - up to `engine.fallback_threshold` (60) flexible items: CP-SAT's deadlines stage first (hinted with the repaired plan), then the wall sampler;
    - above it: the wall sampler first for its budget, then CP-SAT hinted with its plan.

    Every step keeps the less late of the two plans.
4. **Anneal** (11.7–11.9) from the result, with W9 protecting every item that is now on time.

**The guarantee, stated precisely.** Every plan Friday returns is valid. An item that is complete and on time in the start plan is never made late. The start plan has zero lateness whenever construction, repair or the fallback finds such a plan. In the research this happened on every instance where zero lateness was possible (72/72, 36/36 adversarial, 288/288 simulated semester weeks), but finding one is NP-hard in general, so the fallback stays and its use is logged. When lateness is unavoidable, the remaining lateness is reported per item and goes to triage (section 16).

The earliest-deadline-first test in section 14 ignores day caps, chunk lengths, one-sitting items and dependencies. It is a necessary condition, used for quick checks, never as proof that a zero-late plan exists.

### 11.7 Moves (`engine/kernel.py`)

Each step proposes one move, chosen at random with these relative weights; the kernel computes its Δ and its wall checks, and the sampler accepts or rejects it.

| Move | What it does | Weight |
| --- | --- | --- |
| shift | Move a chunk 1–4 slots earlier or later | 1 |
| far shift | Move a chunk anywhere in its item's window | 1.5 |
| swap | Swap two equal-unit chunks of different items | 1 |
| split | Cut a legal-size piece off a chunk and move it elsewhere | 1 (essential: without it wellbeing is 3× worse, because walls forbid breaking long runs one slot at a time) |
| merge | Move a chunk next to a sibling chunk of the same item | 1 |
| transfer | Move k units between two chunks of the same item | 1 |
| grow | Extend a chunk by one slot | 1 |
| shrink | Shorten a chunk by one slot | 0.5 |
| insert | Add a new chunk (the minimum chunk, or the whole amount for one-sitting items) | 1 |
| drop | Remove a chunk | 0.3 |
| eject | Move a chunk onto another item's chunk, and re-place the displaced one | 0.5 |

Insert, drop and shrink are essential for elastic, target and open items, which start empty. The weights are starting values from the research; tune them on the benchmark.

### 11.8 Sampler

- **Acceptance:** Metropolis, accepting with probability `min(1, exp(−Δ/T))`.
- **Schedule:** geometric, from `T0 = 0.1 × m` to `T1 = 0.003 × m`, where m is the median |Δ| over 1,500 random valid moves from the start plan that leave the deadlines stage unchanged. (Including deadline deltas would set T near 10⁹.)
- **Stage policy** (`engine.stage_policy`):
    - `lexpolish` (default) — 60% of the steps on `E = 10⁶ D + 1000 W + P`, then 40% on `P` with wellbeing capped at the value reached and deadlines capped at the value reached plus 0.1% (`LATE_TOLERANCE`; any move past a cap is rejected). With nothing late the deadline cap is 0; with work late, the deadlines stage's rounding (a minute of lateness) had outranked every preference and late work went in alternating half-hour slivers (M15). It ends lexicographic for wellbeing and searches like a weighted sum. In the research it matched strictly tiered annealing on wellbeing at the median and gave 2.3× better preferences.
    - `weighted` — one energy, `10⁶ D + r·W + P`, with ratio r from settings. It trades wellbeing for preferences when r is small (r = 1 made wellbeing 4× worse).
    - `strict` — anneal wellbeing with preferences off, then preferences with wellbeing capped. It is the most literal "wellbeing first" and left preferences about 3× worse.
- **Chains:** independent chains from the same start, one per idle performance core (`engine.chains`, default: performance cores − 1, at least 1). Chain c uses seed `engine.seed + c`. The best result by (D, W, P) wins, D within the same 0.1% of the least late counting as equal. In the research this was as good as parallel tempering and population annealing, and better than any single chain on 25–29 of 30 instances.
- **Tabu finish:** when the step budget is large (above `engine.tabu_after_steps`, ~2.5 M), the last 20% of steps run a tabu search over 25 candidate moves with tenure 8.

### 11.9 Budgets, cancellation and determinism

- **Step budgets, not time budgets.** A time budget makes plans depend on machine load. Budgets are proposals per chain, by flexible-item count:

| Items | Cold plan | Warm replan |
| --- | --- | --- |
| ≤ 20 | 300k | 150k |
| ≤ 60 | 800k | 300k |
| ≤ 150 | 2 M | 600k |

  At ~550k proposals per second per core, that is roughly 1.5 s cold and 0.5 s warm at 60 items. The research measured this on a loaded machine; M3 re-measures it on an idle one.
- **Cancellation:** chains check a shared flag every 50k steps. A newer snapshot sets the flag, and the worker starts the new solve as soon as the chains stop.
- **Determinism:** the same snapshot, settings version, learned-profile version, seed and step budget give the identical plan on any machine and any thread count, because each chain has its own generator and the winner is chosen by value, then by chain index.

### 11.10 The deadline fallback (`engine/cpsat_deadlines.py`)

A CP-SAT model of the deadlines stage only, used by 11.6 and by `what_if` when construction and repair leave lateness. Variables:

- `x[i,s]` ∈ {0,1};
- `over[i]`;
- `start[i,s]` only where chunk rules need them, defined exactly: `start ≥ x[s] − x[p]`, `start ≤ x[s]`, `start ≤ 1 − x[p]`, with p the previous slot if it is allowed for i and contiguous in time, otherwise `start = x[s]`;
- `cum[i,s]` only for dependency sources.

Constraints:

- C1: Σ_i x[i,s] ≤ 1;
- C2: amounts as W4, with `need ≤ placed + over` for fixed amounts;
- C4: locks;
- C5: day caps;
- C6: one sitting, `Σ_s start ≤ 1` and `over ∈ {0, need}`;
- C7: minimum chunk, `x[i,s+j] ≥ start[i,s]` for the slots covering `min_chunk` (and no start where they aren't contiguous and allowed); the maximum chunk the same way;
- C8: dependencies, `(N_A − P_A)·x[B,s] ≤ cum[A, s−ℓ]`.

The objective is the deadlines stage value from the compiled model (late-work prices, overflow prices and quota hinges). Solve with 8 workers, `max_time_in_seconds = engine.fallback_s` (5 s; `engine.fallback_overload_s`, 15 s, when the week is overloaded, meaning EDF already reports infeasibility or construction and repair left lateness on more than 2 items). On a warm replan of a week that isn't overloaded the limit is `engine.fallback_warm_s` (1 s): the previous plan already had its full fallback, and on the benchmark's warm instances 1 s left lateness unchanged everywhere while cutting those replans from about 7 s to 3 s (M4). Hint with the best plan so far. Only a valid plan with lower lateness replaces it. This is the one place the engine's result can depend on time; it runs only when lateness remains, and the report says so.

### 11.11 Warm replans

Start from the previous plan (construction with `base`), repair if it is late, protect what is on time, and anneal with the stage policy from `T0 = 0.01 × m` with the warm step budget, with `minimize_changes` active. Research numbers: 0.9 s median for a usable replan, with churn (hours of surviving items' work moved) equal to CP-SAT's given 30 s. The first replan after a pace switch multiplies `minimize_changes` by `pace.switch_stability` (section 17.6), and the first after a change to `rules`, `sleep`, `daily_cap`, `energy_map`, `kind_order` or `event_kinds` by 0: you asked for a different plan, and holding the old one (wellbeing outranks every preference) made a changed rule look like it did nothing (M16). The factor never applies to preferred pins, which keep their full hold.

### 11.12 Solution and the evaluator

- **Solution:** `owner` per slot, the derived blocks, `over` per item, stage values, per-rule totals, chains run, steps run, the fallback's use and status, and wall time.
- **The evaluator** (`engine/evaluate.py`) is plain Python and independent of the kernel. It computes stage values and per-rule totals for any plan from section 12's definitions; `checker.py` lists every wall violation. Every plan the scheduler returns is evaluated before it is saved: a mismatch with the kernel's values, or any violation, raises (it is a bug).
- `Solution.value(var_key)` recomputes every quantity a `Lin` can reference (`x`, `over`, `start`, `cum`, `any`) from the slots alone, which is what keeps explanations exact.

### 11.13 Alternative plans and probabilities

The sampler can also run chains at a fixed temperature T from the current plan. Their samples are genuinely different plans (66–71% of work slots differed in the research), and item-on-day frequencies over 16 samples are calibrated when T matches the user's estimated answer noise (section 21). Because walls limit where a chain can go, these are probabilities over plans reachable from the current plan, not over all valid plans. They feed active questions (21.4); any user-facing use ("other ways this week could go") comes after M9.

### 11.14 Implementation notes

- The kernel is numba-compiled (`@njit(cache=True, nogil=True)`) over flat arrays only. Compile it without numba's reference-counting runtime, which makes moves 10–15× faster. Pass arrays, not tuples of arrays, to hot functions.
- Cold JIT compilation takes about a minute. The compiled cache ships with the app, and the daemon warms the kernel in the background at start.
- Chains run as threads inside the worker process (the kernel releases the GIL).
- Every new rule type must come with the kernel-vs-evaluator differential test (24.1), or "exact explanations" breaks silently.

---

## 12. Rules and rule types

### 12.1 The base class (`engine/rules/__init__.py`)

```python
class Rule:
    type: ClassVar[str]  # registry key, set by @rule_type("...")
    default_stage: ClassVar[str] = "preferences"
    applies_to: ClassVar[set[str]]  # amount kinds it can ever apply to

    class Params(BaseModel): ...

    def __init__(self, name, *, weight=1.0, stage=None, scope=None, reason=None, **params): ...
    def prepare(self, problem) -> None: ...  # once per build
    def price(self, item, slot) -> float: ...  # points per hour; also called on the overflow slot
    def forbids(self, item, slot) -> bool: ...
    def measures(self, ctx) -> Iterable[Measure]: ...
```

- `reason` is a plain sentence used in explanations ("Mondays are rest days"). It defaults to the rule's name.
- Parameters are validated by pydantic when the rule is built from settings.
- Weights and slopes must be ≥ 0.

**Scope** has these fields: `area`, `tags` (any of), `preset`, `energy`, `firmness`, `amount`, `title` (compared after normalization, 6.6) and `title_regex`. Each is a value or a list, and they combine with AND. **EventScope** has `event_kind`, `title` and `tags`.

**Building blocks (`engine/pwl.py`).**

- **Lin** is a linear expression over symbolic variables: `x(i,s)` (units of i in slot s), `start(i,s)`, `cum(i,s)`, `any(g,d)` and `over(i)`. A dict of variable → integer coefficient, plus a constant. One `Lin` is used three ways: `compile.py` flattens it into the kernel's sparse arrays, the deadline fallback turns it into a CP-SAT expression, and the evaluator evaluates it against a `Solution` in plain Python. Rules build every measure from `Lin`, which is what keeps the kernel, the fallback and explanations in exact agreement.
- **Measure** = `name` (unique, e.g. `deep_run@142`), `expr` (a `Lin`), `unit` (`units` or `count`), `curve`.
- **Curve** = a list of hinges, each with a direction (`above` or `below`), a threshold θ and a slope ≥ 0:

```latex
\varphi(g) = \sum_{\text{above}} \mathrm{slope}_i \max(0,\, g - \theta_i) + \sum_{\text{below}} \mathrm{slope}_i \max(0,\, \theta_i - g)
```

  Thresholds are made whole: floor for `above`, ceil for `below`. Slopes are non-negative, so every curve is convex. The sampler doesn't need convexity, but it keeps penalties monotone and the CP-SAT fallback exact.
- **Units in settings:** a value with `h` or `m` (`"3h"`) is a duration and becomes units; a bare number is a count. For `units` measures, slopes are points per hour; for `count` measures, points per count.
- **Integer costs.** A hinge's cost per unit of g is `round(weight × slope × scale)` (per hour: × 0.25 per unit), with `scale` = 100. A positive coefficient that would round to 0 becomes 1, with a logged warning. The kernel, the evaluator and the fallback all use these same integers.
- **`add_curve_penalty(model, measure, weight)`** exists only in the deadline fallback: per hinge an integer z with `z ≥ g − θ` (or `θ − g`) and cost × z in the objective.
- **BuildContext** gives rules the variable constructors (`x`, `over`, `start(i)`, `cum(i)`, `any_of(group, day)`), `busy(s)` as a `Lin`, days and weeks with their slots, `items_in(scope)`, and the Problem. Rules never see the kernel or CP-SAT.

### 12.2 Built-in rule types

Notation: `end(s)` and `start(s)` are slot times; `imp` is importance; w is weight. Prices are points per hour. Measures use hinge curves (slopes per hour for unit measures, per count for count measures).

| Type | Stage | Hook | Applies to | Charge (before × weight) |
| --- | --- | --- | --- | --- |
| `late_work` | deadlines | price | hard, fixed amount | `imp × max(0, hours(end(s) − due))`. Overflow: if due ≤ horizon end, `imp × (hours late at horizon end + overflow_extra_hours)`, else 0 |
| `quota` | deadlines | measure | items with quotas | Per week in the horizon: progress this week + placed this week, below the quota; slope 1/h |
| `late_night` | wellbeing | price | all | `a × max(0, min(τ, B) − G) + b × m × max(0, τ − B)`: τ = slot end in local hours, G = `gradient_start`, B = that night's bedtime, m = the night's sleep-debt multiplier (12.3). Gentle before bedtime, steep in the margin. Plus `morning` (2) points per hour in the first `morning_min` (60) after waking |
| `deep_run` | wellbeing | measure | scope (default energy deep; the reference rule adds light, so a reading doesn't run five hours either) | For every window of K+1 consecutive units with enough allowed in-scope slots: in-scope units placed, above K; slope 1/h |
| `reserve` | wellbeing | measure | all | Per matching day: units busy inside the window, above (free units in the window − `free`); slope 1/h |
| `daily_load` | wellbeing | measure | scope | Per day: in-scope units, above `threshold`; slope 1/h (a soft cap below the hard cap) |
| `even_load` | wellbeing (the reference rule sets preferences, M15) | measure | scope (default firmness hard) | Per day: in-scope units, above E = max(⌈H / n⌉, `floor`), where H is the remaining in-scope work due inside the horizon, n the days before its latest due that have free time, and `floor` (3 h, one long sitting) keeps a light day from being evened out into scraps; slope 1/h. Its weight comes from the spread dial |
| `time_preference` | preferences | price, forbids | scope | A slot matches if its weekday is in `days` (or not in `days_except`; default every day) and, when `start`/`end` are given, its local start is in [start, end), which may wrap midnight. A matching slot costs `price`, or is removed if `price = FORBID`. Covers rest days, preferred days and disliked hours |
| `energy` | preferences | price | scope (default energy deep) | `energy_map[weekday][local time bucket]` (points/h; from settings or the learned profile) |
| `soft_late` | preferences | price | soft, fixed amount | As `late_work`, for soft deadlines |
| `finish_early` | preferences | price | scope (`except_preset` leaves kinds out) | Finish L = `days` before due: `min(L, max(0, days(end(s) − (due − L))))`. The overflow slot uses the same formula at the horizon end. On by default (a day, exam prep excepted, M15): with nothing else to choose between free hours, homework landed on its due evening |
| `unscheduled` | preferences | price (overflow only) | fixed amount, no hard due inside the horizon, no due after it | `base × imp` per overflow hour. Without it, work with no deadline would never be placed. Work due after the horizon is paced by the allocator's quotas instead (13.3) |
| `after_event` | preferences | price | scope | Pulls items to start right after matching fixed items (`events`: an EventScope). Reference time E per day: the end (with buffer) of the day's last match (`measure_from = last`), or of the most recent match before the slot (`any`). A slot at or after E costs `min(cap, slope × hours(start(s) − E))`; before E it costs `cap`. Days with no match: `on_days_without = ignore` (free) or `cap` |
| `buffer` | wellbeing | measure | scope | Breathing room (M11): per slot s and buffer size b (an item's b is the largest of `minutes`, `by_area[area]` and `by_preset[preset]`), g = b × (an in-scope chunk starts at s) + units busy in the b units just before s (flexible work, plus fixed events as constants; the window follows contiguous time, across the day start); above b, slope 1/h. Nothing when b = 0 |
| `chunk_cost` | preferences | measure | split, chunk_cost > 0 | Σ starts, above 1; slope `chunk_cost × size_hours` per extra chunk |
| `spread` | preferences | measure | spread items | Per day: units placed, above ⌈remaining / available days⌉; slope 1/h |
| `cluster` | preferences | measure | cluster items | Days used (`any_of` per day), above 1; slope `per_day` per extra day |
| `batch_by_day` | preferences | measure | scope, grouped `by` area or preset | Per group and day, a helper `y[g,d] ≥ x[i,s]` for every in-scope item of the group and slot of the day. Measure = Σ_d y[g,d]: each extra day a group spreads across costs the weight |
| `target_shortfall` | preferences | measure | target | h = progress + placed in the window. `curve` lists below-hinges at fractions of T′ (target + carry; scaled by the share of the window inside the horizon when the window runs past it), slopes per hour. Decreasing slopes make the first hours count most. Hours above T′ are free |
| `elastic_shortfall` | wellbeing (M16) | measure | elastic | Placed + progress: below `min` slope `steep`, below `ideal` slope `gentle` |
| `open_value` | preferences | measure | open | Per item and day: placed + that day's progress, below-hinges at fractions of the daily ceiling (default curve `[[0.5, 1], [1.0, 0.5]]`). So the first hours of a day are worth the most and later ones less. Slopes × the growth dial |
| `minimize_changes` | preferences (the reference rule sets wellbeing, decision 120) | measure | non-tentative, non-open | Units of the current plan given up: Σ over current ∩ allowed of (1 − x). Slope 1 point per hour; preferred-pin units use `preferred_multiplier`. Past or removed slots are ignored. A trade, not a guarantee |

**Dials.** Where a dial affects a rule (section 17.6), the rule multiplies its weight or threshold by the day's factor from `problem.scales[day]`. Measures that span several days use each day's own factor for that day's part. A factor of 0 switches the rule off for that day.

**Learned multipliers.** Every soft rule's weight is multiplied by its learned multiplier θ_r (default 1, section 21). Hard-deadline rules (`late_work`, `quota`) are never learned. Dials and multipliers combine: effective weight = weight × θ_r × the day's dial factor.

**How open items find their place.** An open item's first hour in a day is worth 1.5 points at the default growth (1 + 0.5 from the curve), and later hours 0.5. Keeping reserve free is worth 2 points an hour. So at Normal pace a side project fills free time outside the reserve. At Push pace (growth 2, rest 0.5) its first hours are worth 3, more than the reserve's 1, so it starts using evenings. At Easy pace (growth 0) it isn't placed at all. These numbers are starting values to tune in real use.

### 12.3 Sleep

Sleep is a setting, not an item: per-weekday bedtime, wake and margin, plus day overrides. The protected core (bedtime + margin → wake) is pruned for every item, and `late_night` prices the evening gradient and the margin.

**Sleep debt.** For night n, D_n is the hours of recorded progress inside the margins of the previous three nights. The night's multiplier is m_n = 1 + `debt_factor` × D_n (default `debt_factor` 0.5). D_n only uses past nights, so m_n is a constant when the model is built, and prices stay linear. Short sleep last night makes working into the margin tonight more expensive.

### 12.4 Reference rules (the defaults shipped in settings)

```toml
rules = [
  { type = "late_work",         name = "late_work",         weight = 10,  params = { overflow_extra_hours = 48 } },
  { type = "quota",             name = "quota",             weight = 3 },
  { type = "late_night",        name = "late_night",                      scope = { except_preset = ["Routine"] }, params = { gradient_start = "22:00", a = 2, b = 20, debt_factor = 0.5 } },
  { type = "deep_run",          name = "deep_run",          weight = 4,   scope = { energy = ["deep", "light"] }, params = { threshold = "3h" } },
  { type = "reserve",           name = "weekday_evenings",  weight = 2,   scope = { except_preset = ["Routine"] }, params = { days_except = ["sat", "sun"], start = "18:00", end = "23:00", free = "2h" } },
  { type = "reserve",           name = "weekends",          weight = 2,   scope = { except_preset = ["Routine"] }, params = { days = ["sat", "sun"], start = "10:00", end = "23:00", free = "4h" } },
  { type = "daily_load",        name = "daily_load",        weight = 5,   scope = { except_preset = ["Routine"] }, params = { threshold = "8h" } },
  { type = "even_load",         name = "even_load",         weight = 1,   stage = "preferences" },
  { type = "energy",            name = "energy",            weight = 1 },
  { type = "soft_late",         name = "soft_late",         weight = 3 },
  { type = "unscheduled",       name = "unscheduled",       weight = 0.5, params = { base = 1 } },
  { type = "chunk_cost",        name = "chunk_cost",        weight = 10 },
  { type = "buffer",            name = "buffer",            weight = 3,   params = { minutes = "0m", by_area = {}, by_preset = {} } },
  { type = "spread",            name = "spread",            weight = 3 },
  { type = "cluster",           name = "cluster",           weight = 3,   params = { per_day = 2 } },
  { type = "target_shortfall",  name = "target_shortfall",                params = { curve = [[0.4, 8], [1.0, 3]] } },
  { type = "elastic_shortfall", name = "elastic_shortfall",               stage = "wellbeing", params = { steep = 20, gentle = 2 } },
  { type = "open_value",        name = "open_value",                      params = { curve = [[0.5, 1], [1.0, 0.5]] } },
  { type = "finish_early",      name = "finish_early",      weight = 1,   scope = { except_preset = ["Exam prep"] }, params = { days = 1 } },
  { type = "minimize_changes",  name = "minimize_changes",  weight = 1,   stage = "wellbeing", params = { preferred_multiplier = 10 } },
]
```

Personal examples (rest day, area days, after-class habits) are added through the preferences screen (17.5), not shipped as defaults.

### 12.5 Adding a rule type

The procedure:

1. Pick the hook.
2. Write the class with `Params`.
3. Register it.
4. Test it: zero when untriggered, an exact hand-computed value, avoidance when a free alternative exists, and a grid crossing the zone boundary.
5. Benchmark it.

Every new type also gets the kernel-vs-evaluator differential test (24.1). Anything non-convex needs a design discussion first.

---

## 13. Allocator and pacing (`engine/allocator.py`)

The allocator decides, at day resolution, how much of each item happens on which day over the next `allocator_weeks`. It then hands the scheduler weekly quotas for the items that would otherwise get no pressure.

### 13.1 Inputs

- **Days 0 … A−1**, each with a capacity in units: `floor(utilization × free_units_d)`, capped at the day cap.
    - `free_units_d` is the day's units minus blocking fixed items (known from materialized occurrences), the sleep core, and the free hours that reserve rules keep.
    - `utilization` defaults to 0.8 and is multiplied by the day's capacity factor (17.6), capped at 0.95.
    - Elastic items' ideal amounts are subtracted from their days' capacity.
    - Target items reserve their weekly target (× the growth factor) spread evenly over the window's days.
    - Open items reserve nothing. They only use time left over, which is the point.
    - Days beyond the current pace period use the default pace's dials.
- **Items:** every todo flexible item with a fixed amount and remaining > 0. Each has remaining units, release day, due day (if any), firmness, importance, pacing curve (from the preset; default `linear` for Project, `none` otherwise), and dependencies.

### 13.2 Model

A linear program, solved with GLOP (OR-Tools' simplex: single-threaded and deterministic). Units per day are continuous; quotas are rounded at the end. A day-level forecast doesn't need integer units, and an earlier CP-SAT model with one worker missed the 1 s target on a quarter of the benchmark instances and sometimes found no solution at all (M4, PROGRESS decision 40).

- `y[i,d]` ≥ 0 units, for days from the item's first allowed day onward, on days with capacity and not forbidden for it by a whole-day `time_preference`. Hard-due items may run past due (late days are priced).
- `over_i` ≥ 0.
- Σ_i y[i,d] ≤ cap_d.
- Σ_d y[i,d] + over_i = remaining_i.
- **Dependencies** are kept outside the LP, so it stays an LP:
    - A dependent item's first allowed day is the day after its source has `required` units allocated, plus the lag in whole days. The LP is solved again until no first day moves (each round can only move days later, so this ends).
    - A dependency source gets an *effective due day*: the dependent's due day, minus the lag, minus the days the dependent needs at a typical day's capacity. Work after the effective due day is priced in stage 2, so sources finish early enough for their dependents.
- **Stage 1 (lateness):** Σ_i imp × (units on days after due × days late), plus overflow priced as imp × (A − due day + 2) if due ≤ day A−1. Only hard items count here.
- **Stage 2 (pacing and shape),** with stage 1's value as a constraint:
    - Pacing hinges at every seventh day boundary b: `deficit = p_i(b) × total_i − (P_i + Σ_{d<b} y[i,d])`, below 0 free, slope `pacing_weight` per hour.
    - Work after the (effective) due day: importance per hour per day late. This is what keeps soft-due work and dependency sources on time.
    - Whole-day prices from rules that expose `day_price(date)`. `time_preference` with no time window implements it as price × hours, and as a ban when its price is `forbid`.
    - Overflow at a price above any placement, so work is left unallocated only when it doesn't fit.
    - **The tie-break leans late:** −d per unit for items with a due date, +d for items without one. Work is placed as late as its due date and pacing line allow, so a far deadline doesn't front-load this week. With a pacing curve that means "on the line"; without one, "by the due date". Items with no due date go as early as possible.

**Pacing curve:** `p(τ) = ((τ − r) / (D − r))^k`, with k = 1 (`linear`), 0.7 (`front`) or 1.5 (`back`). r is the release (else the item's creation, else now), D is the due date, and the result is clipped to [0, 1]. "Half a four-week project in the first two weeks" is the linear line. The curve comes from the preset (`linear` for Project, `none` otherwise).

### 13.3 Output

`Allocation`: units per item and day, plus `quota[i][week]` = Σ y[i,d] over the days of that week that lie inside the scheduler horizon, rounded. Quotas are only passed for items whose due is beyond the horizon end; items due inside it are already handled by `late_work`. Those same items are left out of `unscheduled` (12.2): the quota is what places them, so the scheduler doesn't pull all of a far deadline into the horizon. Their amount in the scheduler is capped at their quotas (at least one minimum chunk when there is a quota, else 0): placing more cost nothing either way, so stray half hours of readings due three weeks later turned up in the plan (M15).

The allocator's day totals are shown in the weekly view as "planned load" for weeks 3–12.

---

## 14. Executor (`engine/executor.py`)

Pure functions over a light input: now, the free-time intervals, and the hard-deadline jobs. No solver is involved.

### 14.1 Inputs

- **Free time:** the intervals from now until the latest hard due (past the scheduler's horizon when a due is further away). It excludes blocking fixed items with buffers, sleep cores, and every locked pin; a job's own locked minutes before its due count as work already placed, so its EDF length is what's left after them.
- **Daily caps are ignored here**, so the check is slightly optimistic. The scheduler still enforces caps.
- **Jobs:** every todo item with `firmness = hard`, a due time and remaining minutes > 0, plus its release. Minimum chunks are ignored, since splitting is assumed free. This is noted wherever slack is shown.

### 14.2 Feasibility: earliest-deadline-first

The jobs are simulated over free time. At each moment, the released, unfinished job with the earliest due runs. Ties go to higher importance, then lower id.

For one worker, splittable jobs and release times, this order is optimal for maximum lateness. So it is an **exact** feasibility test, not a heuristic. Output: each job's finish time, and `L_max` = the largest finish − due (≤ 0 means feasible).

### 14.3 Latest starts and slack

The same simulation runs **backwards** from the latest due. In reversed time, due dates act as release times and the job with the latest original release runs first. This gives an as-late-as-possible schedule.

- An item's **latest start** `L_i` is the start of its earliest piece in that schedule.
- **Slack** = `L_i − now`, in wall time. It is also reported as free minutes between now and `L_i`.
- If the jobs are infeasible, slack is negative for the jobs that cause it.

This latest start is conservative: it assumes every other job is also left as late as possible. That is the safe direction for warnings.

### 14.4 Safe swaps

**Candidates** are todo flexible items that:
- have remaining > 0 (open items qualify until today's ceiling is reached, unless today's growth factor is 0);
- are released;
- have their dependencies satisfied by recorded progress;
- are not forbidden at the current slot by pruning (fixed items, sleep core, `FORBID` rules).

For each candidate c, take Δ = `min(remaining_c, swap_run_min (30), time until the next blocking fixed item)`. Remove [now, now + Δ] from free time, and reduce c's remaining if c is itself a job. Re-run EDF. c is **safe** if `L_max_after ≤ max(0, L_max_before)`.

**Ranking:**
1. The sum of c's wellbeing and preferences prices at the current slot, using the same rule objects. Cheapest first.
2. c's next planned start in the current plan, soonest first.
3. Slack, smallest first.

The top `swap_count` (3) are returned, excluding the currently planned item.

### 14.5 Now

`now()` returns:

- **current:** the running timer's item (until its own block ends, or what's left of it, stopped by the next class), else the planned block covering now, else the class or event you're in (`fixed`), else "free time". Blocks are matched by their real times, not the grid's: the grid starts at the next quarter hour, so a block begun at 08:00 had "not started" at 08:03 (M16);
- **next:** the next block or class, whichever is first (a class used to be skipped: "free until 15:45" past a 13:25 discussion);
- **safe swaps;**
- **alerts:** items whose slack is under `executor.soon_hours` (24 h, "start by …"), under `executor.notify_minutes` (120), or negative ("triage");
- **fits:** for the gap until the next block or blocking fixed item, the safe items whose minimum chunk fits (for a one-sitting item, all of what's left), ranked as above.

### 14.6 Provisional placement

After a schedule-affecting command:

1. Take the current plan, removed items' blocks gone; changed items keep their blocks where still allowed.
2. Apply pins.
3. Place what the changed and new items are missing in EDF order into the earliest free, allowed slots, splitting at its minimum chunk. Nothing else is placed: placing every item's unplanned remainder painted next week's homework into today as ghosts on every command (M16). Open items wait for the solve.

This is construction (11.6) with the previous plan as its base, on the problem with its rules left out, since construction only checks walls. Elastic and target items are kept from the previous plan but not added. The result is flagged `provisional`, never saved, and drawn as ghosts. The scheduler's plan replaces it within seconds.

---

## 15. Planner

### 15.1 Snapshot (`planner/snapshot.py`)

`take_snapshot(conn, now) -> Snapshot` reads, in one read transaction:

- todo items relevant to the allocator horizon, their dependencies and pins;
- progress and timer;
- fixed occurrences in range, and day overrides;
- the resolved settings and their version;
- the pace periods overlapping the allocator horizon, and the saved paces;
- the current plan's blocks;
- the generation number.

The snapshot is frozen and picklable. Everything the engine needs comes from it, so replans are reproducible from a saved snapshot. In debug mode, snapshots are written to `data/snapshots/` for replay.

### 15.2 Build (`planner/build.py`)

Steps:

1. Build the grid, nights (with debt multipliers), caps and blocked slots (fixed items with buffers). Resolve each planning day's dials (the period covering the day's start, else the default pace) and turn them into that day's `DayScales` with `core/pace.py`.
2. Compute remaining work per item (section 8). Items with remaining ≤ 0 are awaiting confirmation and are not scheduled. Tentative items whose window ended are also awaiting.
3. Turn pins into locked and preferred slots. Run the **lock checks**, which make contradictory pins impossible before any solve:
    - overlapping locks → the more recently created one wins and the older becomes preferred;
    - a lock over a fixed item → preferred;
    - locks exceeding remaining work → remaining raised;
    - locks exceeding a day cap → cap raised;
    - a one-sitting lock that can't grow to the full length → preferred.
4. Add the timer pin (section 8 rule 2).
5. Convert dependencies on fixed items into release or due times.
6. Prune (11.2).
7. Build the allocator input, then (after the allocator solves) attach quotas.
8. Instantiate rules from settings, including plugin types.

Every repair becomes a notice in the plan report.

### 15.3 Replan

1. Snapshot at generation g, then send it to the worker.
2. In the worker: build, allocate, schedule.
3. Back in the API process, assemble:
    - Blocks are runs of slots, cut at pin boundaries so pinned blocks stay whole.
    - Each block gets its per-rule cost (`explain.block_costs`): prices summed over its slots, and each measure's cost split evenly among the blocks whose slots appear in its expression. Measures that touch no block are reported as `other`.
    - The report holds stage values, rule totals (whole plan and per day), each block's cost by rule, overflow per item, notices (a lock that had to give, events that overlap: "CHEM Prelim 2 and CHEM 2091 Lab overlap on Thu Oct 22 at 19:30") and conflicts, the change list, solve status and times, plus `allocation_summary`, `quotas`, `slack` and `pace` (the dials per day, and **pace notices**: days where hard deadlines force more work than the day's dial-adjusted `daily_load` threshold, e.g. "Easy pace can't keep Fri under 4.8 h: PS5 and Lab report are due"; each links to triage).
    - The **change list** compares against the previous current plan's future blocks. Moves of open items aren't listed: they fill whatever is left, so they move often and it isn't news. Inputs come from the `command_log` rows since the previous plan, with their actors ("agent:assistant moved Gym").
4. **Lock conflicts:** only if locked pins exist and the deadlines value is > 0 (if nothing is late, no lock can be causing it). Run `what_if` with every lock turned into a preferred pin. If lateness drops by more than `lock_conflict_tolerance` (1 point), find the responsible pins with one `what_if` per locked pin (at most 10), freeing only that pin. Save the plan as `waiting`, keep the current plan, and report e.g. *"Locked Gym Thu 18:00 makes PS4 1.5 h late."* The `resolve` command settles it: the pins you list become preferred and Friday replans, or with none listed the waiting plan is accepted, lateness included.

**`what_if(snapshot, change)`** returns `{item: extra late hours}`: it runs construction, repair and (only if lateness remains) the deadline fallback before and after applying `change` to the problem in memory, and writes nothing. Without the fallback it takes milliseconds. Lock checks, shoves and triage use it.
5. Save it as current unless a plan from a newer generation is already saved. Publish `plan.changed`.

### 15.4 Shove

A **shove** clears a range of time for you: half an hour to eat, an afternoon, or whole days off. It is a fixed item with `event_kind = 'shove'`, titled "Shoved".

- **Ways to give the range:** a length from now (`30m`, `1h`), a time range (`12:00-13:30`), the rest of today (`rest`), or one or more whole days (`day fri`). A whole day runs from `day_start` to the next; if it is today, it starts now. Several days make one shove per day.
- **Exact times.** The range is kept to the minute; any slot it touches is blocked.
- **Work in progress.** A block running at the start is cut there. The part before counts as progress under the usual rules (section 8), and the rest is planned again.

Steps:

1. **The executor answers first.** If EDF stays feasible with the range removed and the current plan has no late work, the shove is created at once and a replan follows.
2. Otherwise `what_if` runs in the worker (milliseconds, or up to `engine.fallback_s` if the fallback is needed). If nothing gets later, the shove is created and Friday reports what moved: *"Cleared 12:10–13:10. Moved PS4 12:00 → 14:00."*
3. If something would get later, nothing changes yet. Friday returns the **must-do list** (each item, its extra late hours, and the hours it had planned in the range), and you choose:
    - **`shove_anyway`:** create the shove and accept the lateness;
    - **`keep_must_dos`:** lock the must-do items' planned blocks inside the range, shove the remaining gaps, and replan;
    - **`cancel`:** nothing changes.

The pending decision is stored in `kv` with a 10-minute expiry, so it survives a restart. `unshove` removes the most recent shove (or a given one); `undo` works too.

**Shoves can complete tentative items.** When a shove lies inside an open tentative item's window and its length is within `planner.tentative_match_min` (30) of the item's remaining time, Friday asks *"Is this Store run?"* Yes completes the item and records the shove as its `retro` progress. No leaves it open.

### 15.5 Worker and debounce (`server/worker.py`)

- Schedule-affecting commands set `replan_at = now + debounce_s` (3 s); each new one resets it.
- The worker plans one snapshot at a time. Chains run as threads inside it (11.8). When a newer generation is waiting, the worker sets the cancel flag; chains stop within 50k steps (well under 0.1 s) and the newer snapshot starts. Only a CP-SAT fallback in progress is stopped through OR-Tools' stop callback.
- The worker warms the numba kernel from its on-disk cache at start, so the first plan doesn't pay compilation.
- A worker that crashes is restarted and the snapshot retried once.

### 15.6 Replans as time passes

- `tick_replan` (every 15 min): a warm replan if a block boundary has passed since the last plan, or a timer is running.
- `nightly_replan` (03:30): a cold full replan, plus series materialization and end-of-day assumptions for the previous planning day.

---

## 16. Explanations and triage

| Query | Answers | Cost |
| --- | --- | --- |
| `why(block)` | Per-rule cost, total, what shaped it (pins, an adjacent fixed item and its buffer, sleep, the cap, a dependency, a quota), and **one plain sentence** | Instant (stored) |
| `why_not(block, start?)` | Relocates the block in a scratch copy of the plan: to `start`, or to the cheapest valid place. If the move would break a wall, the answer is that wall ("Locked: Gym", "Past its due"). Otherwise it returns the exact per-rule energy difference, top three rules first. With `resolve=true` it also re-anneals with the block's slots forbidden and reports what else would move | Instant; a warm run with `resolve` |
| `changes(plan)` | Inputs with actors, added / moved / removed, rule totals before → after, notices, conflicts | Instant |
| `preview_weights(weights, off)` | A warm scheduler run with changed weights or rules switched off, returned as a change list with rule totals before and after; saves nothing | One warm run (~1 s) |
| `rule_totals(plan, day?)` | Per rule | Instant |
| `triage()` | Options when hard work is late or overflowing | Several `what_if` runs |

**The plain sentence** is built from four parts, in this order:
1. deadline context: "Due Tue 23:59; 2 days of slack";
2. pins: "You pinned it here";
3. the two largest non-zero rule costs, using each rule's `reason`: "Avoids late night (−); costs 1.0 for chunking";
4. the first shaping constraint: "Starts right after CS 1110 + 10 min."

When the day's pace isn't the default, it adds one more part: "Easy pace: today's soft limit is 4.8 h."

It never claims a single cause.

**Triage.** When hard-deadline work is late or overflowing, candidate actions are tested with `what_if` (at most 8, sequentially):

- drop each of the top 5 competing items with lower importance in the affected window;
- extend the late item's due by 1 day, then by 3 days;
- allow the sleep margin for the nights in the window;
- unpin locked pins in the window;
- shorten elastic items to their minimum.

The result is a ranked list of (action, late hours saved, side effects). Applying one uses ordinary commands: `drop`, `edit`, `unpin`, `day_override`.

---

## 17. Settings and preferences

### 17.1 Storage

- Settings are rows in `settings`: key → JSON value, with a version number.
- Each key has a pydantic model in `core/settings.py` with defaults.
- `settings_set` validates the value, bumps the version and records the change in `command_log`, so settings changes are undoable.
- Every plan records the settings version it used.

### 17.2 Keys

| Key | Contents (defaults) |
| --- | --- |
| `time` | timezone, day_start "04:00", week_start "mon", horizon_days 14, fine_days 7, allocator_weeks 12, materialize_days 120 |
| `engine` | stage_policy "lexpolish" (or "weighted", "strict"), weighted_ratio 1000, stage_weights (10⁶, 1000, 1), seed 0, chains (performance cores − 1), step budgets by size (11.9), warm_t0 0.01, t0 0.1, t1 0.003, tabu_after_steps 2.5 M, repair_steps 400k, fallback_threshold 60, fallback_s 5, fallback_overload_s 15, fallback_warm_s 1, fallback_workers 8, move weights (11.7), scale 100 |
| `planner` | debounce_s 3, cancel_after_s 1, assume_unreviewed "done", timer_hold_min 30, lock_conflict_tolerance 1, tentative_match_min 30, utilization 0.8, pacing_weight 2 |
| `executor` | swap_run_min 30, swap_count 3, soon_hours 24, notify_minutes 120 |
| `sleep` | per weekday bedtime, wake, margin (set at first run) |
| `daily_cap` | hours per weekday (default 10) |
| `event_kinds` | name → buffers before and after (class 10/10, meeting 5/5, shove 0/0, other 0/0) |
| `presets` | name → facet defaults (section 6.2) |
| `rules` | list of {type, name, weight, stage?, scope?, reason?, params} |
| `templates` | name → ordered steps {title, share, preset?} for projects (Essay: Outline 0.15, Draft 0.5, Revise 0.35; Presentation: Research 0.4, Slides 0.4, Rehearse 0.2). `template_apply` makes a project with one child per step, each after the one before, and every step but the last aims (a soft due, end of day) to be done when its share of the time to the project's due has passed, so an essay is outlined this week rather than in its last three days (M15); `template_save` saves a project's children as one |
| `paces` | name → dials (Normal, Easy, Push; section 17.6) |
| `pace` | default "Normal", switch_stability 0.2 |
| `energy_map` | 7 × 48 half-hour cells, points per hour (default all 0) |
| `learn` | weights "suggest" (off / suggest / auto), drag_weight 3, prior_sd 1, theta_min 0.02, answer_scale 0.05, state_inference "off", state_gate_nats 2, proposals "ask" (off / ask), proposal_from_week 6, proposal_every_weeks 2, proposal_min_gain 0.114, proposal_min_comparisons 40, questions_per_day 3, questions_per_week 15, query_stop_disagreement 0.2 (section 21) |
| `text` | abbreviations, numbered words, stopwords (section 6.6) |
| `estimate` | window_days 365, area_bonus 0.2, min_similarity 0.6, k 5, min_samples 3, bias_window 20, bias_min_samples 5, bias_threshold 1.15, bias_consistency 0.7 (section 6.6) |
| `notify` | channels, ntfy URL, app URL (where the phone reaches Friday, for ntfy's buttons), VAPID contact, brief and review times, daily cap, per-type switches (section 20) |
| `jobs` | schedules |
| `server` | port 8765, data_dir, log_level, allow_plugins true |

**First run.** `fridayd init` and the app's first-run screen ask for timezone, sleep times and daily cap. Nothing personal is shipped as a default.

### 17.3 Export and import

`friday settings export > friday.toml` and `friday settings import friday.toml` write and read every key as TOML. Import validates everything before writing anything.

### 17.4 Python rule plugins (personal build)

If `server.allow_plugins` is true, every `*.py` file in `~/.config/friday/rules/` is loaded at start and on `settings_reload_plugins`. A plugin defines `Rule` subclasses with `@rule_type("name")`, and the rules list then uses them by type.

- A failing plugin is skipped. Its `file:line` error shows in status and the settings screen.
- Rules that reference a missing type are disabled, with a notice.
- The hosted service sets `allow_plugins = false`.

### 17.5 Plain-language preferences

The Preferences screen maps controls to rules. Strength "a little / some / a lot" = weight 3 / 10 / 30. Each control shows the rules it writes, and the expert Rules view shows everything.

| Control | Writes |
| --- | --- |
| Rest days: [days], strength | `time_preference` days, price 1 |
| Prefer [area/preset] on [days] | `time_preference` days_except, scoped |
| Never [area/preset] between [times] | `time_preference` FORBID |
| Good / okay / poor hours (paint on a week grid) | `energy_map` cells 0 / 2 / 6 |
| Keep free: weekday evenings [h], weekends [h] | `reserve` rules |
| Finish [area] [n] days early | `finish_early` |
| Work in longer chunks: a little / some / a lot | `chunk_cost` on presets 0.05 / 0.15 / 0.3 |
| Longest deep stretch [h] | `deep_run` threshold |
| [Habit] right after [event kind] | `after_event` |
| Daily load soft limit [h], hard cap [h] | `daily_load`, `daily_cap` |

The Rules view has a **Preview**: change weights or switch rules off, see the change list and before/after totals, then apply.

### 17.6 Dials and paces (`core/pace.py`)

Your settings say how Friday plans a normal day. The **dials** say how hard to push right now. They scale a few settings up or down per day, and nothing else. The engine, the stages and the deadline guarantee don't change: a dial can make the days around a hard deadline lighter or fuller, but it can never make the deadline itself give way.

**The four dials:**

| Dial | Range | Normal | What it scales, per day |
| --- | --- | --- | --- |
| `capacity` | 0.3–1.5 | 1.0 | `daily_load` threshold × c; `deep_run` threshold × c (never below 1 h); allocator utilization × c (at most 0.95) |
| `rest` | 0.5–3 | 1.0 | `reserve` free hours × r; `late_night` weight × r; sleep `debt_factor` × r |
| `spread` | 0–5 | 1.0 | `even_load` weight × s (how evenly hard work is spread across days) |
| `growth` | 0–3 | 1.0 | `open_value` slopes × g; `target_shortfall` weight and target amounts × g |

`pace.scales(dials) -> DayScales` turns dials into these named factors. It is the only place the mapping lives, and it is a short, plain function. The sleep core, the hard daily cap and every forbid rule are not dials: no pace can touch them.

**Paces** are saved dial settings. The shipped ones (editable, like everything):

| Pace | capacity | rest | spread | growth | For |
| --- | --- | --- | --- | --- | --- |
| Normal (default) | 1.0 | 1.0 | 1.0 | 1.0 | Most weeks |
| Easy | 0.6 | 2.0 | 3.0 | 0 | Sick or worn out: light, even days, nothing optional |
| Push | 1.2 | 0.5 | 1.0 | 2.0 | Motivated: side projects and goals fill free time and evenings |

**Pace periods.** At most one is active at a time. A period covers whole planning days, so switching applies to today immediately.
- `pace easy --for 5d` sets Easy for today and the next 4 days. `--until sun` runs through Sunday. With no duration, it lasts until you change it.
- When a period ends, Friday goes back to the default pace. The morning brief says so.
- Switching while a period is active replaces it from today on. Switching to the default pace simply ends the period.
- `pace --capacity 0.7 --for 3d` sets dials directly. It starts from the dials in effect now and changes only the ones you give, so the current setting doesn't have to be a saved pace. The UI and CLI show it as "Custom".
- There are no future-dated periods for now ("away next week" can come later).

**Editing paces:** `pace_save easy --capacity 0.5` creates or changes a pace. Dials you leave out keep that pace's values if it exists, or the values in effect now if it doesn't. `pace_save mine` with no dials saves the dials in effect now. `pace_delete` refuses the default pace and the one in use. The default is the setting `pace.default`.

**Switching cleanly.** The first replan after a `pace` command multiplies `minimize_changes` by `pace.switch_stability` (0.2). The point of switching is to move things, so stability shouldn't hold the old plan in place. The web app always previews a switch (`preview: "full"`) before applying it. The CLI applies at once and prints the change summary and the undo id; add `--preview` to see it first. Like every command, a switch can be undone.

**When a pace can't be honoured.** The deadlines stage still comes first. If hard work due soon doesn't fit the lighter days, Friday plans it anyway and reports a pace notice (section 15.3), so you see exactly which days the pace couldn't protect and why.

**Learning.** Every plan records each day's dials, so the dials of any past day can be looked up. Learning (section 21) must condition on them, or a sick week will teach Friday that you're slow.

**Inferred state (off by default).** The dials double as hidden state units: in research, inferring them from comparisons, skipped blocks and check-ins cut regret by 30–40% for users whose moods change, but raised it by 30–60% for users without moods, and a safe gate kept only a quarter of the gain. So Friday never changes your dials or suggests a pace on its own. When `learn.state_inference` is turned on, the inferred state acts only after it passes the per-user gate in 21.3. A pace you pick always wins.

---

## 18. Web app (`web/`)

> **Since M11 the app's look and screens follow `design/friday-v22.dc.html`** (Claude Design "Friday v22"; PROGRESS
> decisions 134–141). Where this section and the design differ, the design wins. It is desktop only for now (about
> 1100 px); the phone layout below waits for a phone design. The behaviour described here (commands, previews,
> undo, drag, live updates, offline reading) still holds.

### 18.1 Stack and structure

- React + TypeScript (`strict`), built with Vite.
- TanStack Query for server state, React Router for the handful of screens, and Tailwind with shadcn/ui (Radix) for primitives. `cmdk` provides the palette.
- API types are generated from the server's OpenAPI schema (`pnpm gen:api`) into `src/api/schema.ts`, with a small typed `command(name, input)` / `query(name, params)` wrapper.

```text
web/src/
  api/            schema.ts (generated), client.ts, events.ts (SSE)
  hooks/          useNow, usePlan, useItems, useCommand (optimistic + undo toast)
  components/
    now/          NowBar, SafeSwaps, Fits
    todo/         TodoPane, QuickAdd, TodoRow
    calendar/     Calendar, DayColumn, Block, Ghost, FixedItem, Bands, NowLine, useDrag
    drawer/       ItemDrawer, WhySection, TryElsewhere, ProgressSlider
    palette/      Palette
    dialogs/      ShoveDialog, TriageDialog, ConflictDialog
  screens/        Main, Review, WeeklyReview, Settings/*
  lib/            time.ts (grid math), format.ts
```

Logic that decides anything about the schedule stays in Python. The client owns layout, interaction and optimistic display only.

### 18.2 Data flow

- **Queries:** `['now']`, `['plan', from, to]`, `['items', filter]`, `['item', id]`, `['review', date]`, `['settings']`.
- **SSE** (`/events`):
    - `items.changed` → invalidate items;
    - `plan.provisional` → store ghosts;
    - `plan.changed` → clear ghosts, then invalidate plan, now and items;
    - `status.changed` → banners.
- **Mutations** go through `useCommand(name)`:
    1. Optimistically update the cache (e.g. move the dragged block).
    2. POST the command.
    3. Draw the response's provisional placement as ghosts.
    4. Show an Undo toast (5 s) that calls `undo` with the returned command id.
    5. On error, roll back and show the message.
- The Now bar's clock ticks on the client. `now` is refetched every 60 s and on `plan.changed`.

### 18.3 Layout

**Desktop (≥ 1000 px):**

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Now: PS5 · 0:42 left  [Done] [+30m] [Switch ▾]  Next: Lunch  Pace: Easy ▾│
├───────────────┬────────────────────────────────────────────┬─────────────┤
│ Quick add…    │  Mon     Tue     Wed     Thu     Fri  …    │ Drawer      │
│ Today         │                                            │ (on click)  │
│ This week     │            Calendar                         │             │
│ Later         │                                            │             │
│ Someday       │                                            │             │
│ Waiting on    │                                            │             │
└───────────────┴────────────────────────────────────────────┴─────────────┘
```

- The Now bar (56 px) is always visible.
- The To-do pane is 320 px and collapsible.
- The calendar fills the rest.
- The drawer (380 px) opens on click and closes with Esc.
- Banners sit under the Now bar: amber for a lock conflict, red for a failed solve or worker, blue for triage ("2 h of PS5 doesn't fit").

**Tablet (700–1000 px):** the To-do pane collapses to an icon rail.

**Phone (< 700 px):** a bottom tab bar with **Now** (home), **Agenda** (list by day, not a grid), **To-do** and **More**. There is a floating quick-add button, the drawer becomes a full-screen sheet, and long-press drags on the agenda's day grid.

### 18.4 Calendar component

- **Views:** day, 3-day and week. The vertical axis runs from the earliest wake to the latest bedtime in settings, in 15-minute rows.
- **Day header:** date, planned / cap hours ("6.5 / 10 h"), the day's points, and the pace name on days that don't use the default ("Easy").
- **Due lane:** a thin lane under the headers shows due markers.

| Element | Looks like |
| --- | --- |
| Block | Area colour fill; title; area in small text; `~` before an estimated length |
| Preferred pin | Dashed border |
| Locked pin | Solid border and a lock icon |
| Tentative | Faint dashed outline, "could fit here" |
| Ghost (provisional) | Translucent outline with a soft pulse until the solver confirms |
| Fixed item | Neutral grey, no fill colour; repeating ones marked ↻; shoves striped |
| Sleep | Core in diagonal stripes; margin lightly shaded |
| Reserve window | Faint tint behind the column |
| Now line | Red line across today |
| Moved since you last looked | One pulse, plus a small "from Tue 3pm" label for 10 s |

**Interactions:**
- **Drag a block** to pin it there as preferred; hold Shift to lock it. Moves snap to 15 minutes.
- **Resize the bottom edge** to pin with a new length.
- **Drag a block onto the To-do pane** to unpin it ("let Friday decide").
- **Drag a To-do row onto the calendar** to pin that item there.
- **Select empty time** for a menu: Shove, Add fixed item here, Show what fits.
- **Click** opens the drawer.
- **Keyboard:** arrows move the selected block by 15 minutes, and Enter opens it.

Drag is built on pointer events in `useDrag`, with no library. Block geometry (`top`, `height`, overlap columns) is computed in `lib/time.ts` and unit-tested.

### 18.5 To-do pane

**Quick-add** is at the top. As you type it calls `q/parse` (debounced 120 ms) and shows the recognized tokens as chips under the input; Enter runs `add`.

**Sections:**
- Today
- This week
- Later
- Someday: no due date and nothing planned in the horizon.
- Ongoing: open items, each showing hours planned this week and hours done.
- Waiting on: blocked by a dependency.
- Suggested: from M10.

**Each row** shows:
- a checkbox (done);
- the title and area dot;
- a scheduled chip ("Tue 2:00", or "not planned");
- a slack badge when slack < `soon_hours` ("start by 4 pm");
- the length (`~2h` when estimated);
- a "finished?" prompt when remaining is 0.

Filter chips by area, search, and a drag handle complete the pane.

### 18.6 Now bar

**Content:**
- The current item with elapsed and remaining time.
- **Done**, **+15 / +30 / +1h** (raises the item's remaining amount), **Switch ▾** (safe swaps), and **Stuck**, which logs friction to the command log and opens the safe swaps.
- Next up.
- An alerts badge.
- **Pace chip** at the right end: "Pace: Easy · to Fri" (just "Normal" by default). It opens the pace sheet (18.9).

**Free time:** the bar says "Free until 14:00 · 3 things fit ▾".

**A running timer** shows Stop instead of Start.

### 18.7 Drawer

- **Fields:** title, area, preset and due editable inline. "More" shows every facet.
- **Progress slider.**
- **Dependencies:** add with `after:` search.
- **This item's blocks.**
- **Why:** the plain sentence plus per-rule cost bars.
- **Try elsewhere:** pick a time or "cheapest other place". It answers instantly with the per-rule difference, or the wall that forbids it (16), then **Move there**. "What else would move" loads after a ~1 s warm run.
- **Pins.**
- **History:** this item's command log, with actors.
- **Actions:** Start, Done, Drop, Pin/Unpin, Make tentative.

### 18.8 Palette (⌘K)

Typing free text offers "Add: …" first, with chips. Otherwise it fuzzy-searches commands (Shove 1h, Replan, Review today, Go to week) and items (opens the drawer). Every command in the palette is a registry command.

### 18.9 Other screens and dialogs

| Screen | Contents |
| --- | --- |
| **Review** | Today's past blocks, timer sessions and logs as swipeable cards: Done / Partial (slider) / Not done; "anything else happened?" adds retro logs. Then any pending questions (21.4–21.6), at most 3 a day: a comparison shows two versions of an upcoming day side by side ("Which looks better?" A / B / Skip); a rule proposal or wall question is one sentence with Yes / No. A one-tap check-in when state inference is on. Submit |
| **Weekly review** | Planned vs actual by area; hard deadlines hit; where time went; manual moves; notifications acted on vs dismissed; what Friday learned this week, with evidence and Approve / Reject for suggested weight changes (21.2) |
| **Settings** | Preferences (17.5), Rules (expert, with Preview and Copy as TOML), Presets, Paces (edit dials, rename, set default), Learning (modes per module, the multipliers with their evidence, state inference on/off, reset), Areas, Sleep and caps, Notifications, Plugins status, Export / import |
| **Pace sheet** | Saved paces as a list; the four dials as sliders (moving one makes it Custom); how long: Today, 3 days, Rest of week, 1 week, Until I change it; a preview of the change ("6 h of side projects paused · 4 items moved · heaviest day 4.5 h (Fri) · all deadlines met"); Apply, and Save as… |
| **Shove dialog** | 30 min, 1 h, 2 h, Rest of today, Whole day…, Custom; the result ("Cleared … moved …"), or the must-do list with Shove anyway / Keep must-dos / Cancel; the tentative match question |
| **Triage dialog** | Ranked options with late hours saved; Apply runs the command(s) |
| **Lock conflict dialog** | Each conflicting lock, what it makes late, unlock checkboxes, Apply / Accept lateness |

### 18.10 Keyboard shortcuts

| Key | Action |
| --- | --- |
| `n` | Focus quick-add |
| `⌘K` | Palette |
| `d`, `3`, `w` | Day, 3-day, week view |
| `[` and `]` | Previous and next |
| `t` | Today |
| `s` | Shove |
| `p` | Pace sheet |
| `space` | Start or stop the timer on the current item |
| `⌘Z` | Undo the last command |

### 18.11 Themes, offline, errors

- Light and dark themes follow the system setting. Colours are CSS variables.
- In M8 the PWA caches the app shell and the last plan, so it opens read-only when the server is unreachable, with a banner.
- Every failed command shows its server message; there are no silent errors.

---


### 18.11 Logging and reading a stretch back (M16)

`fridayd` writes `data_dir/logs/fridayd.log` (rotated at 5 MB, five kept; `server.log_level`): every command with its actor, input, time and outcome (queries at debug), every plan with its reason, generation, seconds, block count, late hours and notices, syncs that brought something in, and every error with its traceback. The app reports what breaks on screen (`window.onerror`, unhandled promise rejections) through the `report` command, which lands in the log and keeps the last 50 in `kv` for `diagnose`. The `diagnose` query lists the last `hours` in order: commands (and what undid them), each plan with how today's work was cut into pieces ("Prep: CHEM Prelim 2 in 6 pieces today, 3 touching"), jobs that failed, and reports; the CLI prints it as a table. The `plan` query shows touching blocks of one item as one block: replans cut the plan at the moment they run and the pieces stay in the record.

## 19. CLI

The CLI is generated from the registry: `friday <verb> …`, with arguments from the pydantic input. `add` takes a quick-add line as its argument. Its only setting is `server` in `~/.config/friday/cli.toml` (default `http://localhost:8765`), overridden by `FRIDAY_SERVER`. Every command takes `--json` (print the raw response). Exit codes: 0 success, 1 bad input, 2 server unreachable, 3 server failure. Ids are accepted with or without their letter. Output is plain aligned text built by `render.py` with `rich`; colour only for area dots and warnings, so it reads in any terminal.

**Ids:**
- items print as `T42`;
- plans as `P7`;
- commands as `C881` (for `friday undo C881`);
- blocks as `T42@Tue14:00`.

```text
$ friday add "PS5 #cs1110 due tue 5pm ~3h"
Added T58  PS5 · CS 1110   3 h   due Tue Oct 20 17:00   (C881, undo: friday undo C881)
Probably Mon 19:00-22:00 (planning…)

$ friday now
Now   PS5 · CS 1110          14:00-16:00   0:42 left
Next  Lunch                  16:00-16:30
Safe to switch to:  Reading ch 4 (psych) · Laundry · Blog draft
Start by 18:00:     Lab report (due Wed 09:00, 4 h of slack)

$ friday shove 2h
Cleared 14:10-16:10. Moved PS5 14:00 -> 19:00.

$ friday pace easy --for 5d
Easy pace, today through Fri Oct 23. Then back to Normal.   (C902, undo: friday undo C902)
Side projects paused (6 h). 4 items moved. Heaviest day Fri 4.5 h. All deadlines met.

$ friday pace --growth 0.5 --for 2d
Custom pace (Normal, growth 0.5), today through Sat.

$ friday pace-save easy --capacity 0.5 --rest 2.5
Saved pace Easy: capacity 0.5 · rest 2.5 · spread 3 · growth 0

$ friday paces
Default  Normal   1.0  1.0  1.0  1.0
         Easy     0.5  2.5  3.0  0.0
         Push     1.2  0.5  1.0  2.0
Now: Custom (growth 0.5) through Sat

$ friday why T58@Mon19:00
PS5 · CS 1110   Mon 19:00-22:00
Due Tue 17:00; 21 h of slack. Avoids your poor-energy morning. Costs 1.0 for late night.
  late_night     1.0
  energy         0.0
  total          1.0
```

---

## 20. Notifications and reviews

### 20.1 Channels

| Channel | How | Notes |
| --- | --- | --- |
| Web Push | The installed PWA; VAPID keys generated at `fridayd init`; `pywebpush` | Needs HTTPS: `localhost` in development, `tailscale serve` (HTTPS on the tailnet) for the phone |
| ntfy | HTTP POST to a configured topic URL with `httpx` | A fallback that works without HTTPS on the phone, through the ntfy app |
| None | — | Everything also appears in the app |

### 20.2 Types

| Type | Condition | Actions |
| --- | --- | --- |
| `morning_brief` | At `notify.brief_at` (08:00, or 30 min after wake) | Open today |
| `block_start` | A block starts; off by default, can be switched on per area | Start · Snooze 15 · Swap |
| `slack_low` | A hard item's slack falls under `notify_minutes` | Start · Triage |
| `overload` | A new plan has hard overflow or late work it didn't have before | Triage |
| `conflict` | A plan is waiting on a lock conflict | Review |
| `evening_review` | At `notify.review_at` (21:30, or 1 h before bedtime) if today isn't reviewed | Review |
| `weekly_review` | Sunday at `review_at` | Open |
| `check` | A hard item's last block before its due ended in the past hour with no timer and no answer (until the review it counts as done) | Yes, done · Not yet (`settle` the block as not done) |

### 20.3 Rules

- A `notify` job runs every minute.
- **Dedup:** `dedup_key` = type + item + planning day.
- **Quiet hours:** default from bedtime to wake, except `slack_low` when slack < 30 min.
- **Daily cap:** `notify.max_per_day` (default 8). Batched types — anything except `slack_low` and `overload` — are merged into one notification when several fire within 5 minutes.
- **Actions** carry a signed, single-use, 1-hour token, so the push action can run its command (`start`, `snooze`, …) with actor `you`. The token goes to the `act` command, which checks it and runs the button's command inside its own transaction, so a button is logged and undoable like anything else.
- **`settle`** answers one of today's past blocks before the review (done, partly, not done); the review starts from that answer.
- Acted / dismissed is recorded in `notifications.acted` for the weekly review.

### 20.4 The brief

`q/brief` returns:
- today's big rocks: 3–5 items ranked by (hard deadline within 48 h, slack, planned minutes today);
- today's fixed items;
- alerts;
- the pace, when it isn't the default or has just ended ("Easy pace until Fri", "Back to Normal today");
- a one-line summary.

It returns both JSON and plain text, so the morning brief, a voice assistant or another tool can include it.

---

## 21. Learning and the supervisor (`learn/`)

Friday learns how you like your time arranged from what you tell it and what you do, without letting one odd day move it much. A small logical layer, the **supervisor**, decides where each kind of feedback goes. Everything learned lives in a versioned **learned profile**, separate from your settings: every plan records the profile version it used, so determinism holds, and the profile can be inspected, approved and reset.

The methods and defaults here come from research on simulated users (24.4). Those numbers rank the methods; their absolute values won't transfer exactly to real use.

### 21.1 Where feedback goes

| Feedback | Goes to | How |
| --- | --- | --- |
| A plan that breaks a hard rule (a bug), or a new "never" rule from you | A wall | A forbid rule or a lock; the kernel can never produce it again |
| A comparison you answer ("which Thursday looks better?") | Learned weights | The preference model (21.2) |
| A drag: your version beat Friday's | Learned weights | The same model, counted 3× (drags come from behaviour, so they are the cleanest evidence) |
| Moves in the replan right after a pace switch | Nothing | They reflect the switch, not your taste |
| Comparisons that contradict each other over time | Noise, or state if inference is on | The per-user test in 21.3 decides |
| Skipped blocks, "not done", check-ins | State evidence | Used only when state inference is on (21.3) |
| Comparisons no weights can explain | A rule proposal | 21.5 |
| Work logged inside a "never" window | A wall question | 21.6 |
| The weeks you actually live | Durations and the energy map | 21.7; not used for weights (in research, likelihood learning from lived weeks barely learned) |

### 21.2 Learned weights (`learn/preferences.py`)

- **Features.** φ_r(plan) = rule r's total cost at its hand-set weight. These are exactly the per-rule totals the evaluator already computes. Learned multipliers θ_r scale each soft rule's weight (12.2). `late_work` and `quota` are never learned.
- **Model.** Bradley–Terry: the probability that you prefer A to B is

```latex
P(A \succ B) = \sigma\!\left(-\,\frac{\theta \cdot (\varphi_A - \varphi_B)}{\lVert \varphi_A - \varphi_B \rVert_1 \; s}\right), \qquad s = 0.05
```

  Normalizing by the size of the difference keeps big and small comparisons on one scale.
- **Prior and fit.** θ_r ~ N(1, 1), θ_r ≥ 0.02. MAP fit with scipy's L-BFGS-B over every comparison and drag so far (drags weighted × `drag_weight`, 3). Refit after each evening review that added evidence. It takes milliseconds.
- **Applying it** (`learn.weights`):
    - `off`;
    - `suggest` (default): the weekly digest proposes changes with their evidence, e.g. *"Raise late_night × 1.4: you preferred the earlier plan in 5 of 6 comparisons"*, and applies them when you approve;
    - `auto`: apply within bounds, at most × 1.5 or ÷ 1.5 per rule per week.
- **Answer noise.** A per-user temperature is fitted by cross-validation over 0.02–0.5. Consistent users sit near 0.05–0.08, noisy ones at 0.18–0.5. It sets policy (how many questions to ask, whether contradictions are noise), never the fit itself (using it in the fit hurt users whose moods change).
- **Research result.** Bradley–Terry beat every alternative tested on held-out accuracy (0.85–0.87 vs 0.77–0.79 with no learning), and was the most robust to deliberately inconsistent answers. The alternatives were a ranking QP with hard constraints, contrastive divergence from lived weeks, and max-margin from drags only. The QP learned fastest from consistent users but bent to noise.

### 21.3 State: dials as hidden units (`learn/state.py`, off by default)

When `learn.state_inference` is on:

- **The model.** Four state units h, one per dial. They act multiplicatively on the learned multipliers: θ_eff = θ × exp(U h). U is seeded from what each dial means: capacity lowers the `daily_load` and `deep_run` weights; rest raises `late_night` and the `reserve` rules; spread raises `even_load`; growth raises `open_value`, `target_shortfall` and `unscheduled`. The multiplicative form is deliberate: an additive one let taste and state trade off, so normal weeks read as "motivated". Each week's h is inferred (MAP) from that week's comparisons, skipped blocks and optional one-tap check-ins (tired / normal / motivated), given your taste θ. How strongly skips and check-ins indicate each state is fitted jointly over all weeks.
- **The gate.** Inferred state is used only after it has earned it, per user: it must predict next week's comparisons at least `state_gate_nats` (2) better, cumulatively, than taste alone at taste's best answer temperature. That baseline matters. Compared with an uncalibrated baseline, state units "win" just by softening predictions, which fits noisy answers without any real state.
- **When it acts.** In weeks where you haven't picked a pace, the planner uses θ_eff in place of θ. A picked pace always wins: its dials apply through `DayScales` as usual, h is set to 0 for those days, and the pace is recorded as that week's known state.
- **Never automatic otherwise.** Friday never changes dials or suggests a pace while inference is off.
- **Research result.** Always-on units cut regret 30–40% for users with real mood swings and raised it 30–60% for everyone else. The gate made them harmless for users without moods but recovered only a quarter of the gain, because with a few comparisons a week the units need many weeks to prove themselves. Single-week readings were wrong 23–42% of the time for users without moods. Hence off by default, and per-user rather than per-week decisions.

### 21.4 Which comparisons to ask (`learn/queries.py`)

- **Candidates** are pairs of plans for the coming days, drawn from fixed-temperature samples (11.13), so both options are realistic.
- **Choice:** query-by-committee. Fit 6 bootstrap copies of the preference model and ask the pair they disagree on most.
- **Budget:** at most `questions_per_day` (3) and `questions_per_week` (15), one tap each. (The first draft had 2 a week; at that rate proposals, which need about 40 answers, took months: PROGRESS decisions 119, 121.) Questions are asked in the evening review, never as notifications.
- **Stop asking** when the committee's disagreement on its own top pair drops below 20%, or when your fitted answer noise is high (above 0.15).
- **Research result.** For consistent users, query-by-committee reached 90% held-out accuracy in 10–12 questions vs 25 for random pairs. For noisy users every strategy first made accuracy worse than the hand-set weights, which is why asking stops.

### 21.5 Missing rules (`learn/proposals.py`)

- **Detection.** From week `proposal_from_week` (6) and once at least `proposal_min_comparisons` (40) answers and drags are in, every `proposal_every_weeks` (2), Friday tests a grammar of candidate rules: `time_preference` templates (11 day sets × 6 time windows × scope any or deep work = 132). For each it measures the 5-fold cross-validated gain in comparison log-likelihood from adding that feature.
- **Proposal.** The best candidate above `proposal_min_gain` (0.114 nats per comparison) is proposed in plain words: *"You seem to prefer no work on Friday and Saturday evenings. Add that as a rule?"*
    - **Yes** adds the rule (its weight is then learned like any other).
    - **No** removes that template from future proposals.
    - Nothing is ever added without your yes.
- **Research result.** The right rule was found for 6 of 6 test users by week 4 and was the top candidate at every later check. Users with nothing missing got false proposals in 33% of week-4 checks, 17% at weeks 6–8 and none from week 10, hence starting at week 6 and always asking. Only time-of-day/day-of-week templates were tested; other template families need their own tests before shipping.

### 21.6 Walls never soften silently

When timer, review or retro progress lands inside a `FORBID` window, Friday asks once, at the first such event: *"You worked during 'no errands after 21:00'. Keep it as a hard rule, or make it a strong preference?"* With questions off, it proposes the softening after 3 such events in 3 different weeks within 6 weeks. It is still a proposal. In research, asking once had by far the lowest regret: softening after one event dropped every one-off user's wall, and never softening was worst.

### 21.7 Durations and the energy map (M9b)

Both learn from what you actually did, never from comparisons, and only from days at the default pace (a sick week
mustn't teach Friday that you're slow). Both are new modules of the learned profile with their own mode
(`learn.durations`, `learn.energy`: off / suggest / auto, default suggest) and their own reset.

**Durations** (`learn/durations.py`, replacing step 1–2 of §6.6's estimator; your typed lengths and the bias
correction stay as they are).

- **Data.** Completions whose actual source is `timer`, `review` or `retro`, in the last `estimate.window_days`,
  each as log(actual minutes), with its area, its preset and its *kind*: the cluster of its type text (titles with
  similarity ≥ `estimate.min_similarity` link into one kind, single linkage; "problem set 3" and "problem set 4"
  are one kind).
- **Model.** log m = μ + a_area + p_preset + k_kind + ε, with a, p, k drawn from N(0, τ²) per level and ε ~ N(0, σ²).
  Fitted nightly by empirical Bayes: σ and the τ's by maximum marginal likelihood (a few hundred rows; scipy,
  milliseconds), the offsets as their posterior means, so a kind seen twenty times stands on its own and one seen
  twice is pulled toward its area and preset, the more so the less kinds differ in your history.
- **Prediction** for a new item: the posterior predictive mean and variance of log m from its area, preset and
  kind (unknown levels contribute 0 and their τ² of variance). **p50** for flexible items, **p80**
  (mean + 0.84 sd) for hard-deadline items, rounded up to whole units. `estimate_detail` keeps the level offsets,
  the rows behind the kind, and the p50–p80 range, so the drawer can say *"~3 h (2.5–4 h): problem sets in CS
  1110 run 3 h; this kind, 4 done"*.
- **Below 5 completions in all**, the §6.6 estimator is used unchanged.
- **Gate.** Each night the model is scored on the last 20 completions it didn't see (rolling), against §6.6's
  estimator; in `suggest` mode the weekly digest offers to switch once its median absolute log error is lower.

**Energy map** (`learn/energy.py`; settings `energy_map` stays yours, the learned part is added to it).

- **Cells**: 7 days × 48 half hours, as `energy_map`.
- **Evidence per cell**: for each planned block of deep or light work that covered the cell, whether it *happened
  as planned* (a timer session started within 15 minutes of the block's start, or the review answered done) and,
  when timed, the speed ratio actual ÷ planned.
- **Estimates.** Happened: the cell's s of n, smoothed with the neighbouring half hours of the same day
  (weight 0.5) and the same half hour on neighbouring days (weight 0.25), shrunk toward your overall rate r (a
  prior worth 4 blocks). Speed: the mean log ratio less your usual one, shrunk to 0 by n / (n + 5).
- **Price.** A cell's learned price for deep work, in points an hour, is 4 × (r − P(happened) − 1.5 standard
  errors, at least 0) plus 2 × the
  shrunk log speed ratio, clipped to [0, 6] (§17.5's poor-hour price is 6), added to your map's price. It is
  relative to your own rate, so work that slips everywhere alike makes no hour look worse (M9b: against a fixed
  0.8, a simulated student who skipped 8% at random got 98 priced cells).
- **Bounded exploration.** A cell with fewer than 4 observations gets no learned price, so early misses don't make
  a cell look bad forever; and once a week the planner may place one deep block in an unobserved cell that your
  own map doesn't price (only when that costs less than 1 point).

### 21.8 The learned profile

- **Contents:** θ, answer noise, the state model and gate status, accepted and refused proposals, and wall decisions.
- **Versioning:** each change creates a new version with its evidence. Plans record the version they used.
- **Control:** modes per module (off / suggest / auto), a weekly digest of what changed and why, and reset per module or all.

---

## 22. Outside world (M10)

Friday reads the outside world into a review inbox, publishes its plan one way to Google Calendar, and opens
itself to assistants through MCP. Principle 7 holds: an LLM only (a) extracts items from documents and mail into
the inbox and (b) turns a quick-add line the grammar can't read into one command you confirm. Principle 12 holds:
nothing outside changes the schedule until you accept it, except calendars and feeds you mark **trusted** (22.2),
which you have reviewed once by choosing them.

**Milestones:** M10a the inbox, ICS feeds, uploads and LLM extraction, and the quick-add fallback; M10b Google
Calendar (read and publish); M10c Gmail; M10d MCP and webhooks. Each ends with its own gate.

### 22.1 Sources, raw inputs and the inbox (`ingest/`)

| Table | Columns | Notes |
| --- | --- | --- |
| `sources` | id, kind (`ics`, `gcal`, `gmail`, `upload`), name, config (JSON), trusted, enabled, last_sync_utc, last_error | One row per feed, calendar, mailbox or upload |
| `raw_inputs` | id, source_id, external_id, received_utc, content_hash, content (text; files under `data_dir/inputs/`), status (`new`, `extracted`, `ignored`, `failed`) | Everything is stored before anything is read from it; UNIQUE (source_id, external_id) |
| `suggestions` | id, raw_input_id, batch_id, command, input (JSON), quotes (JSON: field → verbatim text), confidence, duplicate_of, status (`pending`, `accepted`, `rejected`, `superseded`), decided_utc | One proposed registry command each |

- **Flow:** fetch → store raw → extract (fixed rules for ICS and calendars; the LLM for mail and documents) →
  validate each proposed input against the command's own input model → duplicate check → suggestion.
- **Only what can still be done, as it can be accepted:** an `add` already due (or over) when it is read is
  dropped; a set-time kind with no time (a meeting still to arrange) is proposed as an Errand, and deadline work
  with no due date as soft, so accepting never fails on a missing time.
- **Duplicates:** same identity text (6.6) and a due or start within 24 h of an open item's: the suggestion is
  marked `duplicate_of` and shown folded; accepting it edits the existing item instead of adding one. A set-time
  event at the very minute of one you have, one title's words inside the other's ("MATH Prelim 2", "Prelim 2"),
  is that event too (M16).
- **Updates:** a changed external item (same `external_id`, new content) makes a suggestion that edits the item it
  made, shown as a diff; the older pending suggestion is `superseded`. When one input made several items (an exam
  and its prep), each proposal edits the one of its kind: an exam's prep never edits the exam (M16).
- **Commands:** `source_add`, `source_edit`, `source_remove` (`forget: true` also deletes its raw inputs and
  files), `sync_now`, `suggestion_accept` (with optional edits to the input), `suggestion_reject`, `batch_accept`;
  query `inbox`. Accepting runs the suggested command as you, so it is undoable like anything else.
- **The app:** the To-do pane's **Suggested** section (count, top three), and an Inbox screen: each suggestion as
  the item it would make, its source, and every field's quote highlighted; Accept, Edit, Reject; batches
  (a syllabus) reviewed as one with Accept all.
- **Jobs:** `sync` every `ingest.poll_min` (30) per enabled source; extraction runs in the job loop, never in a
  request.

### 22.2 Calendar feeds (ICS) and Google Calendar reading

- **ICS** (`ingest/ics.py`, `icalendar`): a URL polled with `httpx`. `VEVENT`s become fixed items (event kind
  `class` when the summary or a source rule says so, else `other`); an `RRULE` becomes a series. A `VEVENT` of no
  length, or whose summary matches the source's due pattern (default: `^(due|deadline)[: ]` or Canvas's
  assignment feed), becomes an assignment due at its start. `VTODO`s with `DUE` become assignments.
- **Google Calendar read** (`sync/gcal.py`): the calendars you pick are read, from yesterday to `allocator_weeks`
  ahead (a paper due in five weeks on Canvas is paced from now, M15), every `poll_min` with sync tokens into
  fixed items marked with their calendar; events you decline are left out; all-day events are left out unless the
  calendar is set to include them (as `blocks_time = 0`). A repeating event's rule (yearly, monthly, weekly on
  some days) is read from the event its instances come from, and kept with them for Repeating; when it can't be
  read, the weekdays of its instances stand in.
- **Trusted sources** (a per-source switch, off by default): their fixed events go straight in as fixed items
  (as `actor = "sync:<source>"`, logged and undoable); anything that isn't a fixed event still goes to the inbox.

### 22.3 Publishing to Google Calendar (`sync/gcal_publish.py`)

- One calendar named "Friday" (created on first publish), written only by Friday. Each block of the current plan
  inside the horizon is one event (title, area colour, a link back to the app, the block key in
  `extendedProperties.private.friday`); tentative blocks are marked "maybe".
- After each new plan, debounced to once every `gcal.publish_debounce_s` (60): events are created, moved or
  deleted to match, by block key. Changes made to that calendar in Google are overwritten (it is a view).
  Fixed items that came from Google aren't copied back.

### 22.4 Gmail (`sync/gmail.py`)

- **What is read:** only messages matching your query (setting `gmail.query`, default
  `newer_than:14d -category:promotions -category:social -category:forums`), newest first, at most
  `gmail.max_per_sync` (50), through the history API after the first sync. Headers, the plain-text body (HTML
  stripped) and attachment names are stored; attachments are fetched only when they are PDFs under 5 MB and the
  message passes the pre-filter.
- **Pre-filter** (no LLM): a message goes to extraction only if it matches a sender rule (default: any address at
  a domain you list, e.g. your university's) or a keyword rule (due, deadline, exam, quiz, assignment, submit,
  meeting, invite, reschedule, cancelled, prelim, midterm, homework, problem set, lab report, rsvp, form,
  application; plurals too), or is from a person (not bulk) asking for something by a day ("by Friday", "by
  Nov 1", "by 11/15"), so most mail never leaves the machine. Words and senders are edited in Integrations.
- **Threads:** only the newest message of a thread is read (it quotes the others); earlier ones are logged as
  skipped for that reason. When a thread already gave suggestions, the AI is told their titles and proposes only
  what is new, so a reply and its answer don't make the same task twice in other words.
- Gmail "done" signals (a submission receipt marking an item done) stay deferred.

### 22.5 LLM extraction (`ingest/extract.py`, `anthropic`)

- **One call per raw input** (an email, a document, a syllabus), with one forced tool, `propose_items`, whose
  schema is a list of `add` inputs (title, preset, area, due, start/end, length, repeat) each with `quotes`
  (field → the exact source text it came from) and a confidence. The prompt gives today's date, your timezone,
  your areas and presets, the input, and your **notes** (setting `notes`, Settings → About you: up to 40 lines
  in your own words, such as "PHYS labs are done in the lab session"); no other personal data. Notes are told
  once instead of learned: the model leaves out what they say needs no time and uses the lengths they give. The
  calendar sorter (M13) reads them too and may answer, per entry, `skip` (no suggestion) or `minutes` (the
  length of work due). Rejecting a suggestion offers "why not?", which adds a note (M16).
- **Checks:** every quote must occur verbatim in the input (else that field is dropped); dates must resolve in your
  timezone; each item must pass the `add` input model; low confidence (< 0.5) is shown but unticked.
- **Model and cost:** `llm.model` (default `claude-sonnet-5-5`; `claude-haiku-5-5` is cheaper for mail),
  `llm.daily_calls` (default 50) and `llm.daily_tokens` (default 500k); past the budget, inputs wait for
  tomorrow and a banner says so. Results are cached by content hash, so a message is never sent twice.
- **The key:** `ANTHROPIC_API_KEY` from the environment, or set in Settings, stored in `data_dir/secrets.json`
  (mode 0600), never in settings, exports or logs.

### 22.6 Uploads and syllabi

- Upload a PDF, image or text in the app (Inbox → Add document) or by `friday add-doc FILE`. It becomes a raw input
  of an `upload` source. PDFs and images go to the model as documents (no PDF parsing in Friday).
- A syllabus is recognized by the model (one tool field) and produces **one batch**: an area, the class series,
  dated assignments, and exam-prep items `before:` each exam, reviewed together.

### 22.7 Natural-language quick-add fallback

When the grammar leaves a line with no recognized time or length and you press **Ask** (or Enter twice), one
call with a forced tool returns a single registry command input (usually `add`). It is shown as chips exactly
like a parsed line, and nothing runs until you press Enter. It counts against the daily budget.

### 22.8 MCP server and webhooks (`server/mcp.py`, `mcp`)

- **Tools are generated from the registry**, like the HTTP API and the CLI: every query a read tool, every
  command a write tool with a `preview` argument; descriptions from the commands' docstrings and input models.
- **Transports:** stdio (`fridayd mcp`, for a local assistant) and streamable HTTP at `/mcp` on the same server.
- **Tokens:** `token_add(name, scope)` (scope `read` or `read-write`) returns a token once; requests carry it as a
  bearer token; the actor recorded for its commands is `mcp:<name>`. `token_remove` revokes it. Settings lists
  them with last use.
- **Webhooks:** `webhooks` settings, a list of {url, events}: Friday POSTs `block.started`, `slack.low`,
  `plan.changed` and `item.done` as JSON, signed with an HMAC header, retried 3 times.

### 22.9 The config file

Everything in this section, and any other settings key, can be set in **`friday.toml`** (`~/.config/friday/`, or
the path in `FRIDAY_CONFIG`). It is the same TOML that `friday settings export` writes (§17.3), plus the M10
tables below.

```toml
[llm]
model = "claude-sonnet-5-5"        # or claude-haiku-5-5 for mail
daily_calls = 50
daily_tokens = 500_000

[google]
client_file = "~/.config/friday/google_client.json"   # the OAuth client you made in Google Cloud

[gcal]
read = ["primary", "Classes"]      # calendars to read
trusted = ["Classes"]              # their events skip the inbox
include_all_day = false
publish = true                     # the "Friday" calendar
publish_debounce_s = 60

[gmail]
query = "newer_than:14d -category:promotions -category:social -category:forums"
max_per_sync = 50
sender_domains = ["cornell.edu"]
keywords = ["due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule", "cancelled"]

[ingest]
poll_min = 30

[[sources]]                        # ICS feeds
name = "Canvas"
url = "https://canvas.example.edu/feeds/calendars/user_xxx.ics"
trusted = false
due_pattern = "^(due|deadline)[: ]"
```

- **How it applies.** At start, and within a minute of the file changing, fridayd validates the whole file
  (nothing applies if anything is wrong; the error shows as a red banner and in Settings) and writes each key it
  sets through `settings_set` as actor `config`, so every change is logged and undoable like any other.
- **The file wins for what it sets.** Keys the file sets show in the app as "set in friday.toml", read-only, so
  the app and the file never fight; keys it leaves out stay editable in the app. Sources listed in the file are
  matched by name and created, updated or disabled to match.
- **Secrets stay out of it:** `ANTHROPIC_API_KEY` from the environment or `secrets.toml` beside it (mode 0600),
  Google tokens in `data_dir/secrets.json`. The file only points at the OAuth client JSON.

### 22.10 Secrets, privacy and failure

- Google OAuth uses your own Google Cloud OAuth client (Desktop type, its JSON named in `friday.toml`), the
  loopback redirect flow (`friday google-login` opens the browser once), and the narrowest scopes:
  `calendar.readonly` and `calendar.app.created` (only the Friday calendar) for M10b, `gmail.readonly` for M10c.
  Tokens live in `data_dir/secrets.json`, one per Google account under its address (found from its primary
  calendar, so no extra scope); the single token older versions kept still counts until the sync names it.
- `source_remove(forget: true)` deletes a source's raw inputs and files; extraction results are kept only as the
  suggestions you accepted.
- A source that fails shows its error in Settings and as a red banner after 3 failures in a row; other sources go
  on. Nothing external is ever needed to plan.
- New dependencies, as listed in §4.2: `icalendar`, `anthropic`, `google-auth-oauthlib`,
  `google-api-python-client`, `mcp`.

## 23. Hosted service (outline) and the seams kept now

A hosted Friday that others sign up for is a possible later goal. **Kept now, at almost no cost:**

1. `user_id` on every table. Every query filters by it, through `ctx.user_id`, which is always 1 in the personal build.
2. Settings and presets are data in the database, with no per-user files.
3. No module-level mutable state; the engine is pure; solves are functions of a snapshot.
4. `server/auth.py` has one function that resolves a request to a user. It returns 1 in the personal build.
5. The worker interface takes `(user_id, snapshot)`, so it can become a pool with per-user fairness.
6. Portable SQL in application code: standard types, ISO text timestamps, no SQLite-only functions outside migrations. JSON columns are read and written in Python, not queried with SQL JSON functions.
7. Python plugins sit behind `allow_plugins`.

**Needed later (not designed now):**
- real auth (passkeys or OAuth);
- Postgres;
- a worker pool with plan budgets per user (sampler steps are the main cost, and they are counted, so they are easy to meter);
- rate limits;
- onboarding: setup wizard, calendar import, pairwise weight elicitation;
- data export and deletion;
- Google OAuth app verification (Gmail read scopes are restricted and need a security review; Calendar scopes are sensitive);
- monitoring and billing.

---

## 24. Testing, simulator and benchmark

`uv run pytest -q` and `pnpm --dir web test` run everything. No test touches the network.

### 24.1 Unit tests by layer

- **core:** both grid zones across a DST day; series materialization (counts per window, detach, from-date split); quick-add (a table of at least 40 lines with expected fields and spans); settings validation and TOML round-trip; `pace`: dials → scales, the period covering each day, replace and end semantics; recurrence (every shorthand in 6.3, `UNTIL`, every other week, a weekly series across a DST change staying at the same local time, `describe` words); text normalization (a table of ≥ 30 titles including the traces in 6.6, the Roman-numeral guard, whole-word abbreviations, area removal) and similarity pairs; dates (every form in 9.4).
- **estimate:** synthetic histories that hit each step; `estimate_detail` contents; bias cases that should and shouldn't suggest (too few, inconsistent, inside the threshold); accepted corrections don't change later ratios; `assumed` actuals are never used.
- **engine:**
    - every rule type: zero when untriggered, an exact hand-computed value, avoidance when free, and the zone boundary;
    - **kernel exactness (the most important test in the repo):** on random instances of every size class and both grid zones, apply thousands of random moves of every kind, and after each check that the kernel's stage values equal `evaluate()` and its violation counts equal `check()`; one test per rule type with only that rule switched on;
    - every wall W1–W9: no move that breaks it is ever accepted; a protected item never becomes late;
    - construction: honours every wall; zero late on a brute-force-checked set of tiny instances where zero is possible;
    - the deadline fallback model: its stage value for a given plan equals the evaluator's; constraints C1–C8 each tested;
    - sampler: the same snapshot, seed and step budget give the identical plan with 1, 2 and 8 chains' threads; cancellation stops within 50k steps;
    - `why_not` relocation differences equal the evaluator's difference between the two plans;
    - every dial: its factor reaches the rules it should, and a factor of 0 switches the rule off for that day only;
    - allocator pacing and quotas;
    - executor (24.3).
- **planner:** snapshot → build reproduces the same Problem; lock checks; assemble cuts at pins; change list inputs come from the command log.
- **commands:** every command applies, previews (nothing changes), undoes (rows restored), refuses a stale undo, and is idempotent with a key.
- **server:** generated routes match the registry, SSE events fire, worker cancel and restart, job catch-up.
- **web:** `lib/time.ts` geometry (Vitest). Playwright flows:
    - quick-add → row appears → ghost → block;
    - drag → pin → undo;
    - review submit, with a comparison answered;
    - shove with a must-do.
- **learn:** Bradley–Terry recovers planted multipliers on synthetic comparisons; drags weighted ×3; `suggest` mode never changes weights without approval; the state gate stays closed for users without moods; proposals are never added without a yes; a wall never softens without an answer.

### 24.2 Scenario tests (each with its own small rule set)

| # | Setup | Expected |
| --- | --- | --- |
| 1 | A rest-day `time_preference`; the only free time before a hard deadline is on the rest day | Work goes on the rest day; no late work |
| 2 | More work than fits in the horizon | A plan is returned with overflow reported; never infeasible |
| 3 | A locked pin that makes another item late | The lock check names that pin and the extra late hours |
| 4 | A whole-day shove of today; an item due tomorrow 09:00 with no other time | The shove returns it on the must-do list and changes nothing |
| 5 | Replan with nothing changed | Identical plan; nothing moved |
| 6 | A preferred pin and a slightly cheaper slot elsewhere | The block stays |
| 7 | A one-sitting 2 h item where splitting would be cheaper | One contiguous block; with no 2 h gap, all of it overflows |
| 8 | A target item whose only free slots are expensive | Placed only where the shortfall slope beats the slot price |
| 9 | `batch_by_day` plus a Saturday `time_preference`; three chores | All on Saturday |
| 10 | `late_night`; work that fits before or after 23:00 | Before, unless a deadline needs otherwise |
| 11 | A horizon containing a daylight-saving change | That day has 4 more or fewer fine slots; blocks map to the right UTC times |
| 12 | Any plan the scheduler returns | Every rule total from `explain` equals the evaluator's, and the evaluator's stage values equal the kernel's |
| 13 | B depends on A; both fit only in one order | A before B |
| 14 | B after 50% of A with a 1-day lag | B starts ≥ 1 day after half of A is placed |
| 15 | Split item with a 30-min minimum and scattered 15-min gaps | No isolated 15-min pieces |
| 16 | 3 h item; free day; `chunk_cost` on | One chunk, unless a pin forces two |
| 17 | 5 h of deep work; class at 11:00; `deep_run` 3 h | Runs on either side of the class; nothing deep > 3 h straight |
| 18 | Reserve 2 h weekday evenings; light load | Evenings keep ≥ 2 h free |
| 19 | Lunch routine 11:30–14:30, 20–45 min, with a busy day | Lunch placed inside the window at ≥ 20 min |
| 20 | 30 h project due in 6 weeks; light near-term load | Quota places about a linear share in this week and next |
| 21 | Running timer past its block's end | The block extends and later blocks reflow |
| 22 | Unreviewed past block, `assume_unreviewed = done` | Counted; review "not done" restores the remaining work |
| 23 | Same snapshot planned twice, with different thread counts | Identical plan |
| 24 | Command, then undo | Database rows identical to before |
| 25 | Open item, light week, Normal pace | Fills free time outside reserve; never above its daily ceiling |
| 26 | Same week, Easy pace | Open item not placed; hard work spread so no day exceeds the even share by more than one chunk |
| 27 | Same week, Push pace | Open item also uses reserve evenings; sleep core untouched |
| 28 | Easy pace, hard work that can't fit in light days | All deadlines met; a pace notice names each overloaded day |
| 29 | `pace easy --for 3d`, then the fourth day | Day 4 uses the default dials; `undo` of the switch restores the earlier period |
| 30 | A long dependency chain (30 items) with zero lateness possible | Construction or repair finds a zero-late plan; no fallback needed |
| 31 | Tight one-sitting packing where only one arrangement is on time | The fallback finds it; its use is reported |
| 32 | An item on time in the start plan; a preference that would pull it past its due | It stays on time (W9) |
| 33 | Overload: more hard work than fits | Every plan valid; lateness no worse than the fallback alone, within the polish tolerance (0.1%, 11.8); per-item lateness reported |

### 24.3 Property tests (Hypothesis)

- **Engine:** every returned plan is valid; never an error without contradictory locks; a protected item is never late; with `lexpolish`, the polish phase never raises wellbeing; explain totals equal the evaluator's.
- **Executor:** EDF feasibility agrees with brute force on small random instances (≤ 6 jobs, enumerated orders); a safe swap never turns feasible into infeasible; slack ≥ 0 iff EDF is feasible.
- **Quick-add:** parse → add → format → parse is stable.

### 24.4 The simulator (`sim/`)

- **`generate_term(config, seed)`** builds a semester:
    - 4 courses with class series;
    - weekly assignments (lengths log-normal), readings, two exams with prep items, one 20-hour project;
    - meals, chores, two habits and one weekly goal;
    - random social events (2–4 evenings a week) and occasional sick days.
- **The simulated user** has hidden per-area duration multipliers, an energy curve, start delays, a skip probability, a probability of taking a safe swap, and noisy reviews.
- **For learning** (M9), simulated users also have hidden true weight multipliers (log-normal, σ 0.6) and a mood chain that rescales some weights. They live Friday's plan by departing from it locally under their true energy, drag in about half the weeks, and answer comparisons by Bradley–Terry on their true energy. Five families: consistent, noisy, moody, missing-feature (a true preference no rule expresses) and adversarial (30% of answers flipped).
- **The loop** drives Friday **through the command registry with a fake clock**, so it exercises the real code paths. It works in 15-minute steps, with morning replans, actions, reviews and nightly jobs.
- **Metrics:** hard deadlines missed, late hours, plan churn (hours moved per day), adherence, plan times, notifications; for learning, held-out comparison accuracy, weight recovery (cosine with the true multipliers), regret (true energy of Friday's plan minus that of the plan best for the user's true weights).

M2–M3 use only the generator (static problems). The full loop arrives in M7 and drives M9.

### 24.5 Benchmark (`tests/bench/`)

Generated snapshots: 20, 40, 60 and 150 items; 14 days; about 15 h of fixed items a week; 3 pins; 5 dependencies; the reference rules; seeds 0–9. Plus adversarial families: tight deadlines, overload (1.6–2.2×), fragmented free time, long dependency chains, many one-sitting items, many pins. Cold and warm (warm = the previous plan plus 2 added and 1 removed item). Results are appended to `results.csv`: machine, idle or loaded, sizes, phase times (construct, repair, fallback, anneal), steps, stage values, fallback used.

**Targets, measured on an idle laptop** (the research measured under heavy load, so these should be met with room to spare):
- cold plan at 60 items p90 ≤ 3 s; warm replan p90 ≤ 1 s;
- construction ≤ 50 ms at 150 items;
- kernel ≥ 300k proposals per second per core;
- allocator ≤ 1 s;
- `now()` and provisional placement ≤ 50 ms at 100 items;
- zero avoidable lateness and zero invalid plans on every benchmark and adversarial instance;
- kernel load from the shipped cache ≤ 2 s.

Always-on targets on a Pi 5 or VM: about 3× those.

---

## 25. Deployment

- **Development and first use, on the laptop:** `uv run fridayd` plus `pnpm --dir web dev` (Vite proxies `/api` and `/events`).
- **Everyday use:** `pnpm --dir web build`; `fridayd` then serves `web/dist`.
- **Data** lives in `~/.local/share/friday/`: `friday.db`, `backups/`, `snapshots/` (debug), `secrets/` (VAPID keys, later API keys).
- **Start at login (M11):** a launchd agent (macOS) or a systemd user unit (Linux); templates live in `deploy/`.
- **Phone access** goes over Tailscale: plain HTTP works for the app, and HTTPS through `tailscale serve` is needed for Web Push (M8).
- **Always-on later:** the same steps on a Pi 5 or a small Linux VM on the tailnet. Nothing in the code is machine-specific.
- **Backups:** a nightly SQLite online backup, keeping 14. Off-device copies arrive in M11.
- **Dev note:** keep the repo out of iCloud-synced `~/Documents`, or set `UV_PROJECT_ENVIRONMENT`.

---

## 26. Milestones

Each milestone ends with a gate. Real-use gates are passed by using Friday, not by finishing code.

| # | Milestone | Main tasks | Gate |
| --- | --- | --- | --- |
| M0 | Environment | Repo skeleton (Python and `web/`), `pyproject.toml`, layer test, ruff, Vite + React + TS + Tailwind + shadcn scaffold, `scripts/check.sh`, `CLAUDE.md`, `PROGRESS.md` | `scripts/check.sh` green; OR-Tools and numba import; `pnpm build` works |
| M1 | Core | `time` (both zones), `items` (facets, presets, validation), series materialization (pure), `pace` (dials, scales, periods), `recurrence`, `textnorm`, `dates`, `quickadd`, settings models with TOML export/import, `db` and migration 001 | Unit tests green, including DST, recurrence, text normalization and ≥ 40 quick-add cases; the schema creates |
| M2 | Rules, evaluator, kernel | `pwl`; every rule type (12.2) with dial factors and learned multipliers; the evaluator and checker; `compile`; the numba kernel with incremental energy, walls W1–W9 and all 11 moves; static benchmark and adversarial generators | Kernel-vs-evaluator exactness tests green for every rule type and move; every rule type's four tests; kernel speed target |
| M3 | Scheduler | Construction, repair, the CP-SAT deadline fallback, the sampler (schedule, stage policies, chains, tabu finish, step budgets, cancellation), warm replans, `explain` and `why_not`; scenarios 1–19, 23, 25–28, 30–33 | All engine tests; zero avoidable lateness and zero invalid plans on the benchmark and adversarial sets; determinism across thread counts; benchmark targets **on an idle laptop**, recorded in PROGRESS |
| M4 | Allocator and executor | Allocator, pacing, quotas; executor EDF, slack, swaps, now, provisional | Scenario 20; executor property tests; timing targets |
| M5 | Planner, commands, server, CLI | Snapshot, build, assemble, service; registry with log, undo, preview, idempotency; every command and query in 9.3, including the pace commands; progress model (section 8); shove; triage; explanations; FastAPI from the registry; OpenAPI; SSE; worker supervision; jobs; generated CLI; estimator and bias (6.6) | Scenarios 21, 22, 24, 29; a scripted day through the CLI against a running daemon; cancel and undo work |
| M6 | Web app (usable core) | Everything in section 18 except PWA and push | **Two weeks of real daily use**, with a friction log in PROGRESS and its top items fixed |
| M7 | Projects and horizon UI; full simulator | Project tree, templates, dependency UI, triage dialog, weekly load view; simulator loop and metrics | This semester's projects and exams planned to their end dates; simulator runs a full term |
| M8 | Notifications and reviews | PWA, Web Push, ntfy, the notify job, actionable notifications, brief, weekly review | One week with no per-block confirming, and the review done on ≥ 5 of 7 days |
| M9 | Learning | Learned weights, comparisons and query choice, missing-rule proposals, wall questions, the learned profile and digest (21.1–21.6, 21.8); state inference behind its setting (21.3); simulated learning users | On simulated users: held-out accuracy and weight recovery at least as good as section 21 reports; no rule added without a yes; the state gate closed for users without moods. In real use: manual moves trending down |
| M9b | Durations and energy map | **Spec first** (21.7) | Per the spec |
| M10 | Outside world | **Spec first.** Feeds and syllabus, Google, MCP, NL fallback | Per feature, as specified then |
| M11 | Always-on and hardening | Pi 5 or VM, start-at-login units, off-device backups, restore drill | A week unattended |
| M12 | Hosted service | **Spec first** (§23) | — |

---

## 27. Decision log

| Decision | Choice |
| --- | --- |
| Engine shape | Allocator (days, months, CP-SAT) + scheduler (energy sampler with walls, two weeks) + executor (EDF, now) |
| Scheduler | Slot-ownership state, exact compiled energy, walls for every hard rule, earliest-deadline construction, repair, CP-SAT deadline fallback, simulated annealing with 11 chunk moves on parallel chains. Chosen over staged CP-SAT (2–9× too slow, nondeterministic with workers) and over Boltzmann-machine/penalty encodings (never kept the deadline guarantee) |
| Determinism | Seeded chains and step budgets, not time budgets |
| Resolution | 15 min for days 0–6, 30 min after; exact minutes for fixed items |
| Stages | deadlines → wellbeing → preferences; the default `lexpolish` policy searches a 10⁶ : 1000 : 1 weighted energy, then polishes preferences without raising wellbeing. The strictness of "wellbeing first" is a setting, because it is a product choice, not a technical one |
| Item model | One item, eight facets, presets as data; areas and tags instead of a required category |
| Dependencies | Whole or partial, with lag; cycles rejected; enforced in the scheduler and allocator |
| Block shape | Per-chunk cost and minimum chunk restored; consecutive deep work limited; classes and meals act as breaks |
| Sleep | Setting-based core and margin, plus sleep debt from past nights |
| Meals | Elastic routines with windows (no max-gap constraint) |
| Spontaneity | Reserve rules and retroactive logging |
| Far deadlines | Allocator quotas and pacing lines |
| Execution | Plan as budget; safe swaps by EDF; slack escalation; evening review instead of per-block confirmation |
| Pins | Belong to items, not plans; preferred or locked |
| Commands | One registry generating HTTP, CLI and MCP; preview, undo, actor, idempotency |
| No agent inside | LLM only for extraction and a confirmed one-command quick-add fallback |
| Higher-level control | Four dials (capacity, rest, spread, growth) scaling settings per day; saved paces (Normal default, Easy, Push, your own) are just named dial settings; the current dials needn't match a saved pace; switch for a set time or until changed, then back to the default; no LLM and no suggestions from Friday |
| Fluid side work | `open` amount: fills leftover time with diminishing value per day, scaled by the growth dial; never late, never overflows |
| Settings | Database rows with versions; TOML export; Python plugins for the personal build |
| Frontend | React + TypeScript + Vite + TanStack Query + Tailwind/shadcn; custom calendar grid |
| Live updates | SSE; scheduler in a worker process with chains as threads; 3 s debounce; cooperative cancellation |
| Hosting | Laptop first; Pi 5 or VM later; nothing machine-specific |
| Published form | Personal build first; hosted service is the eventual target; seams kept now (§23) |
| Learning | Bradley–Terry multipliers from comparisons and drags (drags ×3), prior at the hand-set weights, suggest by default; query-by-committee questions in the review; missing rules proposed, never auto-added; walls never soften silently; inferred state off by default and gated per user. Versioned profile; plans record its version |
| Code style | Readable without many comments; plain, sparse comments about why |

