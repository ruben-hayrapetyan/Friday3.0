# Friday v2 engine reference

An extract of the frozen Friday v2 design: only what defines the scheduling problem and v2's CP-SAT engine. App, UI, storage, commands and deployment are left out on purpose. Treat this as the definition of the problem any engine must solve and the baseline it must be compared against. Numbers marked as defaults are starting values, not facts.

## 1. Principles that bind any engine

1. **Deterministic planning.** The same input with the same settings gives the same plan. No LLM decides the plan.
2. **Deadlines first.** Stages are solved in order (deadlines, then wellbeing, then preferences) and a later stage never makes an earlier one worse.
3. **Never infeasible.** Work that does not fit goes to overflow and is priced. Overload is a triage decision, never an error.
4. **Exact explanations.** Every cost the engine optimizes can be recomputed from a solution, to the integer.
5. **Convex penalties only.** Every rule is a slot price, a ban, or a linear quantity with a hinge curve whose slopes are non-negative.
6. **The plan is a budget, not a script.** What must hold is that deadlines stay feasible; everything else bends around what actually happens.
7. **Mechanism in code, policy in settings.** No personal preference is hard-coded.

## 2. Glossary

| Term | Meaning |
| --- | --- |
| Item | Anything Friday knows about: a class, a problem set, a project, a meal, a store run. Its behaviour comes from its facets (section 4) |
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
| Pin | Your instruction that an item happens at a given time: **preferred** (resists moving, may move) or **locked** (cannot move). Pins belong to items, not to plans |
| Stage | `deadlines`, `wellbeing` or `preferences`, solved in that order |
| Rule | A configured use of a rule type, with a name, weight, stage, scope and parameters |
| Points | The unit of every penalty. Anchor: 1 point = moving 1 hour of already-planned work |
| Overflow | Work that does not fit in the horizon; priced, reported, never an error |
| Quota | The allocator's minimum for an item in one week of the horizon |
| Pacing line | The progress an item should have made by a given date (linear by default) |
| Slack | How long an item with a hard deadline can wait before deadlines become infeasible: its latest start minus now |
| Safe swap | Something you could do now instead of the planned item without making any hard deadline infeasible |
| Reserve | Free time the plan deliberately leaves open (e.g. 2 h on weekday evenings) for spontaneous things |
| Open item | An item with no fixed amount that fills free time, with each extra hour in a day worth less than the one before (a book, a side project) |
| Dial | One of four numbers that scale your settings for a day: capacity, rest, spread, growth (section 10) |
| Pace | A saved set of dial values with a name: Normal (the default), Easy, Push, or your own. Switching pace can last a set time, after which Friday returns to the default. Unrelated to pacing lines |
| Shove | Clearing time for yourself: a fixed item of kind `shove` |
| Tentative | An item placed in a gap without committing to a time ("store run sometime this weekend"). It never anchors the plan |
| Progress | Recorded work on an item: from the timer, the evening review, a slider, a retroactive log, or an assumption |
| Block | One run of consecutive slots of one item in a plan |
| Plan | All blocks from one solve |

## 3. Time model

- **Units.** A unit is 15 minutes. Flexible durations are whole units, with input rounded up (`40m` → 3 units). Fixed items are exact to the minute.
- **Planning day and week.** Day from `day_start` (default 04:00) to the next 04:00; week from `day_start` on `week_start` (default Monday). A slot belongs to the planning day containing its start, so a daylight-saving change at 02:00 falls in the previous date's planning day.
- **The scheduler grid.** It starts at now, rounded up to the next unit boundary, and covers planning days 0 … H−1 (`horizon_days`, default 14).
  - Days 0 … F−1 (`fine_days`, default 7) use 15-minute slots.
  - Days F … H−1 use 30-minute slots; the zone boundary is at `day_start`.
  - Slots are stepped in UTC, and every slot has `index`, `start_utc`, `end_utc`, `units` (1 or 2), `day`, `weekday`, `local_minute` and `week`. Index S is the overflow slot.
  - A daylight-saving day has 4 more or 4 fewer fine slots. A zone whose offset is not a multiple of 15 minutes is rejected.
- **The allocator grid** is one bucket per planning day, from day 0 to `allocator_weeks` × 7 (default 12 weeks).

`fine_days`, the slot lengths and `horizon_days` are settings, still to be decided by benchmark.

## 4. Items

### 4.1 Facets

Every item has all eight facets. Most have defaults, so a typical item sets two or three.

| Facet | Field(s) | Options | Notes |
| --- | --- | --- | --- |
| When | `when` | `fixed` · `window` · `anytime` | `fixed`: `start_utc`, `end_utc` exact. `window`: `release_utc` (null = now) and `due_utc` (null = no deadline). `anytime`: neither |
| Amount | `amount` | `fixed` · `elastic` · `target` · `open` | `fixed`: `duration_units`. `elastic`: `min_units`, `ideal_units`, `max_units`. `target`: `target_units` and `cap_units` (default ⌈1.5 × target⌉) inside the window. `open`: no amount; `daily_ceiling_units` (default 12 = 3 h) caps it per day. Open items fill free time, never overflow and are never late (`open_value`, 7.2) |
| Shape | `shape`, `min_chunk_units`, `max_chunk_units`, `chunk_cost`, `spread` | `one_sitting` · `split`; spread `none` · `spread` · `cluster` | `split` items may have a minimum chunk (default 2 units = 30 min) and a maximum. `chunk_cost` (0 … 1, default from the preset) is the size-proportional cost of each extra chunk: with 0.1, each extra chunk of a 4-hour item costs 0.4 × the `chunk_cost` rule's weight in points. `spread` spreads work across days; `cluster` keeps it to few days |
| Firmness | `firmness`, `importance` | `hard` · `soft` · `none`; importance 1–5 | `hard` deadlines are settled in the deadlines stage and protected by the executor. `soft` lateness is a preference. `none` means the due date is only a pacing target |
| Value | `neglect_carry` | 0 … 1 | Targets only: the share of last window's shortfall added to this window's target (default 0.5) |
| Relations | `parent_id`; `dependencies` table | — | Projects are trees. A dependency says B may only start once a fraction of A is done, after a lag (4.3) |
| Context | `energy`, `location` | energy `deep` · `light` · `physical` · `social` · null; location text | Energy drives deep-run limits and energy prices. Location is stored but not used by the engine yet |
| Certainty | `certainty` | `planned` · `tentative` | `tentative`: placed in a real gap inside its window, never anchors the plan, never counted as moved |

Fixed items also have `event_kind` (class, meeting, shove, other → buffers from settings) and `blocks_time` (0 = shown but schedulable over).

### 4.2 Presets

Presets are named facet defaults:

| Preset | When | Amount | Shape | Firmness | Energy | Other |
| --- | --- | --- | --- | --- | --- | --- |
| Assignment | window | fixed | split, min 30 min | hard | deep | importance 3 |
| Project | window | fixed | split, min 60 min, cluster | hard | deep | pacing linear; may have children |
| Reading | window | fixed | split, min 30 min | soft | light | |
| Exam prep | window | fixed | split, spread | hard | deep | usually `before:` an exam |
| Class | fixed | — | — | — | — | event_kind class; usually a series |
| Commitment | fixed | — | — | — | — | event_kind other |
| Errand | window | fixed | one sitting | none | physical | |
| Chore | window | fixed | one sitting | none | physical | |
| Routine | window | elastic | one sitting | none | light | e.g. meals: lunch 11:30–14:30, 20–45 min |
| Habit | window | fixed | one sitting, spread | none | null | usually a series with a count per window |
| Goal | window | target | split, min 30 min | none | deep | weekly series; neglect carry 0.5 |
| Side project | anytime | open | split, min 45 min | none | deep | a book, a personal project; fills free time; daily ceiling 3 h |
| Maybe | window | fixed | one sitting | none | null | certainty tentative |

### 4.3 Relations

`dependencies(item_id, depends_on_id, fraction, lag_min)`: the item may not start until `fraction` (default 1.0) of `depends_on` is done, plus `lag_min`.

- Cycles are rejected when the dependency is added.
- If `depends_on` is fixed, the planner turns the dependency into a release time (item after an event) or a due time (`before:`, which stores the reverse dependency).
- An item whose dependency cannot be met inside the horizon overflows. It is reported as "blocked by <title>", not as late work of its own.

Projects: an item with children has no amount of its own. Its due date is the latest-finish date for its children; a child with no due date inherits it. Its progress is the sum of its children's.

## 5. Progress

`remaining(item)` = amount − recorded progress inside its window. Progress comes from a timer, the evening review (done / partial / not done), a "half done" slider, retroactive logs, or an assumption at day end (unreviewed past blocks count as done by default). Only timer, review and retro progress is learned from. A running timer locks its item from the current slot for min(remaining, 30 min); overrunning extends the block. A block never started simply wasn't recorded, so the next replan places the work later. Open items have no remaining amount; their progress feeds today's daily ceiling.

## 6. v2 engine overview

The engine is three pure parts that share the rule types and the `Lin` machinery:

| Part | Horizon | Resolution | Answers | Runs |
| --- | --- | --- | --- | --- |
| Allocator (8) | `allocator_weeks` (12) | one bucket per day | How many hours of each item go on which day; weekly quotas; pacing | Before the scheduler |
| Scheduler (6A, 7) | `horizon_days` (14) | 15 min (days 0–6), 30 min after | Exactly when, under every rule | After the allocator |
| Executor (9) | Until the latest hard deadline | Exact minutes | What now; is this deviation safe; slack; instant provisional placement | Milliseconds |

The engine is pure: frozen inputs in, a solution out; no database, clock or network.

Sections 6A and 7 specify the **grid** model, v2's baseline. An **interval** CP-SAT model (6A.9) was planned as an alternative but never benchmarked.

## 6A. Scheduler (grid baseline)

### 6A.1 Inputs

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
| `shape`, `min_chunk`, `max_chunk`, `chunk_cost`, `spread` | As in 4.1 (chunks in units) |
| `size_hours` | Full amount in hours (for size-proportional costs) |
| `tentative` | Excluded from `minimize_changes` and from change lists |
| `allowed` | Sorted slot indices it may use, after pruning |
| `locked`, `preferred` | Slots from its pins |
| `current` | Slots it holds in the current plan |
| `depends_on` | List of (key, fraction, lag_units) for dependencies on flexible items |
| `quotas` | Week key → units, from the allocator |

**Problem** = the grid, the items, the fixed occurrences in the horizon (title, kind, tags, start, end, buffers), one `Night` per planning day (bedtime, wake, margin, debt multiplier), the day caps in units, the rules, the energy map, and one `DayScales` per planning day: the factors the day's dials produce (section 10). Rules read dial effects only through `problem.scales[day]`.

### 6A.2 Pruning (before any variable exists)

Slot s is removed from item i if:

1. it starts before i's release;
2. `window_is_hard` and it starts at or after i's due;
3. it overlaps a fixed item that blocks time, buffers included;
4. it lies in a protected sleep core;
5. it is locked to another item;
6. an applicable rule's `forbids(i, s)` is true.

Locked slots are always kept. Removed slots get no variable, which is the main performance lever.

### 6A.3 Variables

- `x[i,s]` ∈ {0,1}: item i occupies slot s.
- `over[i]` ∈ [0, need]: fixed-amount items only.
- `start[i,s]` ∈ {0,1}: a chunk of i begins at s. It is created only on request through `ctx.start(i)` — for one-sitting items, for split items with `min_chunk` > 1 slot, and for `chunk_cost` > 0. It is defined exactly, so explanations can count chunks from the solution: `start ≥ x[s] − x[p]`, `start ≤ x[s]`, `start ≤ 1 − x[p]`, where p is the previous slot if it is allowed for i and contiguous in time. Otherwise `start = x[s]`.
- `cum[i,s]`: units of i placed before s. Integer helpers, created only for items that others depend on: `cum[i,s] = cum[i,prev] + units(prev)·x[i,prev]`.
- Helpers made by rules, only through `pwl.py`.

`placed(i)` = Σ_s units(s)·x[i,s].

### 6A.4 Constraints

```latex
\text{C1 one thing at a time:}\quad \sum_i x_{i,s} \le 1 \quad \forall s
```

```latex
\text{C2 amounts:}\quad
\text{fixed: } \mathrm{need}_i \le \mathrm{placed}_i + \mathrm{over}_i,\ \ \mathrm{placed}_i \le \mathrm{need}_i + 1
\qquad \text{elastic: } \mathrm{placed}_i \le \max_i
\qquad \text{target: } \mathrm{placed}_i \le \mathrm{cap}_i
\qquad \text{open: } \mathrm{placed}_{i,d} \le \mathrm{ceiling}_{i,d}\ \ \forall d
```

The `+ 1` lets a 30-minute coarse slot hold a 15-minute remainder. Over-placing costs prices, so the solver uses it only when needed. Elastic, target and open items have no overflow variable: falling short is priced by their shortfall and value rules.

```latex
\text{C3 chunk starts: defined exactly, as above, only where requested}
```

```latex
\text{C4 locks:}\quad x_{i,s} = 1 \ \ \forall s \in \mathrm{locked}_i
\qquad \text{C5 daily cap:}\quad \sum_{s \in d} \mathrm{units}(s) \sum_i x_{i,s} \le \mathrm{cap}_d
```

```latex
\text{C6 one sitting:}\quad \sum_s \mathrm{start}_{i,s} \le 1,\quad \mathrm{over}_i \in \{0,\ \mathrm{need}_i\}
```

C6 is all or nothing: a one-sitting item is placed whole or goes entirely to overflow, never split.

```latex
\text{C7 minimum chunk:}\quad x_{i,s+j} \ge \mathrm{start}_{i,s} \quad \text{for } j = 1 \dots L_s - 1
```

L_s is the number of slots starting at s needed to cover `min_chunk` units. If those slots are not all allowed and contiguous, `start[i,s] = 0`, so a chunk can't begin there. This tightens the model a lot, because it forbids isolated single slots.

The maximum chunk is enforced the same way: any `max_chunk + 1` consecutive allowed units of i sum to at most `max_chunk`.

```latex
\text{C8 dependencies (B after fraction } \varphi \text{ of A, lag } \ell\text{):}\quad
(N_A - P_A)\, x_{B,s} \le \mathrm{cum}_{A,\,s-\ell}
```

Here `N_A = ⌈φ × total_A⌉`, and `P_A` is A's progress. The constraint is skipped if `P_A ≥ N_A`. `cum` is read at the slot ℓ units before s, and is 0 before the grid starts. If A cannot reach `N_A` inside the horizon, B's work overflows. The planner reports this as "blocked by A".

Overflow keeps C2, C6 and C8 from ever making the model infeasible. Only locks can contradict each other, and they are repaired before solving (section 8.1). An `INFEASIBLE` status is a bug and raises.

### 6A.5 Objective

Each stage k minimizes

```latex
\mathrm{Obj}_k = \sum_i \sum_s C^k_{i,s}\, x_{i,s} \;+\; \sum_i C^k_{i,S}\, \mathrm{over}_i \;+\; \sum_{m \in M_k} w_m\, \varphi_m\big(g_m(x)\big)
```

- **Price table:** for each stage-k rule r that applies to i, `C^k[i,s]` gets `round(weight_r × price_r(i,s) × hours(s) × scale)`, where `hours(s)` is 0.25 or 0.5. On the overflow slot it gets `round(weight_r × price_r(i, S) × 0.25 × scale)` per unit.
- **Measures:** linear quantities with convex hinge curves (section 7), added by `add_curve_penalty`.
- `scale` = 100.
- Each rule's share is kept as its own `Lin`, so explanations can split totals by rule.

### 6A.6 Staged solve

1. Build the model once.
2. Hint every `x[i,s]` from the current plan.
3. For each stage in `engine.stages` (default `deadlines`, `wellbeing`, `preferences`):
    1. Set its objective.
    2. Solve with `max_deterministic_time = det_time[k]`, plus a wall-clock safety limit `time_limit_s × share[k]`. A deterministic limit makes results independent of machine load.
    3. Read `v_k` (OPTIMAL or FEASIBLE).
    4. Add `Obj_k ≤ v_k + slack_k × scale`.
    5. Re-hint from this stage's solution.
4. If a stage finds no solution, retry it once with double the limits. If it fails again, raise `SolveTimeout`.

Parameters: `num_workers = engine.workers` and `random_seed = 0`. With one worker, also set `linearization_level = 2`, and compare against the default in the benchmark. Tests use one worker.

`stages=["deadlines"]` runs only the first stage; `what_if` (8.2) uses this.

### 6A.7 Solution

- `slots`: item key → sorted slot indices.
- `over`: item key → units, recomputed as `max(0, need − placed)` so explanations never depend on an arbitrary solver value.
- `stage_values` in points, `status` per stage, wall time, deterministic time, and best bounds.

`Solution.value(var_key)` recomputes every variable kind (`x`, `over`, `start`, `cum`, `any`) from the slots alone. That is what makes every explanation exact.

### 6A.8 Variable-resolution notes

- Prices are per hour, so a 30-minute slot simply weighs twice a 15-minute one.
- Measures count units, not slots.
- "Consecutive" means consecutive in time: the last fine slot of day F−1 is followed by the first coarse slot of day F.
- Every rule must be tested on a grid that crosses the zone boundary.

### 6A.9 The interval alternative (unbenchmarked)

Each split item gets K optional chunks (K = `min(⌈need/min_chunk⌉, max_chunks)`, default `max_chunks` 4). A one-sitting item gets one. Each chunk has:

- an integer `start` in units, restricted to free units by its domain;
- a `size` in [min_chunk, max_chunk], or 0 when the presence literal is false;
- an `end`.

The encoding:

- **No overlap.** One `NoOverlap` over all chunk intervals, plus fixed intervals for fixed items, sleep cores and other items' locks.
- **Ordering.** `start_k ≤ start_{k+1}` breaks symmetry between an item's chunks.
- **Amounts.** Σ size + over = need.
- **No day crossing.** `end ≤ day_end[start]`, via an element constraint on a per-unit table of day ends.
- **Position costs** are exact through prefix sums. With `P_r[u]` = cumulative price of rule r up to unit u, a chunk costs `P_r[end] − P_r[start]`, using two element constraints. Late work, time preferences, night prices and energy all work this way.
- **Chunk count** = Σ presence literals. `chunk_cost` is then exact and tight.
- **Daily caps** need each chunk's day: a boolean per (chunk, day) linked to start, and an enforced size per day. The spike tries this and a cumulative-per-day encoding.
- **Consecutive deep work.** Two deep chunks are adjacent if the gap between them is under `break_min`. The spike tests a simple encoding over ordered chunks.
- **Exact explanations.** The spike must show they still hold: every cost must remain a linear expression over decision variables, so element constraints are fine.

## 7. Rules and rule types

### 7.1 The rule interface

```python
class Rule:
    type: ClassVar[str]                     # registry key, set by @rule_type("...")
    default_stage: ClassVar[str] = "preferences"
    applies_to: ClassVar[set[str]]          # amount kinds it can ever apply to
    class Params(BaseModel): ...

    def __init__(self, name, *, weight=1.0, stage=None, scope=None, reason=None, **params): ...
    def prepare(self, problem) -> None: ...                  # once per build
    def price(self, item, slot) -> float: ...                # points per hour; also called on the overflow slot
    def forbids(self, item, slot) -> bool: ...
    def measures(self, ctx) -> Iterable[Measure]: ...
```

- `reason` is a plain sentence used in explanations ("Mondays are rest days"). It defaults to the rule's name.
- Parameters are validated by pydantic when the rule is built from settings.
- Weights and slopes must be ≥ 0.

**Scope** has these fields: `area`, `tags` (any of), `preset`, `energy`, `firmness`, `amount`, `title` (compared after normalizing case and punctuation) and `title_regex`. Each is a value or a list, and they combine with AND. **EventScope** has `event_kind`, `title` and `tags`.

**Building blocks (`engine/pwl.py`).**

- **Lin** is a linear expression: a dict of variable → integer coefficient, plus a constant. It turns into a CP-SAT expression for the model **and** evaluates against a `Solution` in plain Python. Rules build every measure from `Lin`, which is what makes explanations exact.
- **Measure** = `name` (unique, e.g. `deep_run@142`), `expr` (a `Lin`), `unit` (`units` or `count`), `curve`.
- **Curve** = a list of hinges, each with a direction (`above` or `below`), a threshold θ and a slope ≥ 0:

```latex
\varphi(g) = \sum_{\text{above}} \mathrm{slope}_i \max(0,\, g - \theta_i) + \sum_{\text{below}} \mathrm{slope}_i \max(0,\, \theta_i - g)
```

  Non-negative slopes make every curve convex, so each hinge is exact with one integer helper and no booleans. Thresholds are made whole: floor for `above`, ceil for `below`.
- **Units in settings:** a value with `h` or `m` (`"3h"`) is a duration and becomes units; a bare number is a count. For `units` measures, slopes are points per hour; for `count` measures, points per count.
- **`add_curve_penalty(ctx, measure, weight)`** is the only function that creates hinge variables. Per hinge it makes an integer z in [0, the largest value the hinge can take], adds `z ≥ g − θ` (or `θ − g`), and adds `round(weight × slope × scale) × z` to the rule's stage objective (per hour: × 0.25 per unit). A positive coefficient that would round to 0 becomes 1, with a logged warning.
- **BuildContext** gives rules the model, `x`, `over`, `ctx.start(i)`, `ctx.cum(i)`, `busy(s)` as a `Lin`, days and weeks with their slots, `items_in(scope)`, and the Problem.

### 7.2 Built-in rule types

Notation: `end(s)` and `start(s)` are slot times; `imp` is importance; w is weight. Prices are points per hour. Measures use hinge curves (slopes per hour for unit measures, per count for count measures).

| Type | Stage | Hook | Applies to | Charge (before × weight) |
| --- | --- | --- | --- | --- |
| `late_work` | deadlines | price | hard, fixed amount | `imp × max(0, hours(end(s) − due))`. Overflow: if due ≤ horizon end, `imp × (hours late at horizon end + overflow_extra_hours)`, else 0 |
| `quota` | deadlines | measure | items with quotas | Per week in the horizon: progress this week + placed this week, below the quota; slope 1/h |
| `late_night` | wellbeing | price | all | `a × max(0, min(τ, B) − G) + b × m × max(0, τ − B)`: τ = slot end in local hours, G = `gradient_start`, B = that night's bedtime, m = the night's sleep-debt multiplier (7.3). Gentle before bedtime, steep in the margin |
| `deep_run` | wellbeing | measure | scope (default energy deep) | For every window of K+1 consecutive units with enough allowed in-scope slots: in-scope units placed, above K; slope 1/h |
| `reserve` | wellbeing | measure | all | Per matching day: units busy inside the window, above (free units in the window − `free`); slope 1/h |
| `daily_load` | wellbeing | measure | scope | Per day: in-scope units, above `threshold`; slope 1/h (a soft cap below the hard cap) |
| `even_load` | wellbeing | measure | scope (default firmness hard) | Per day: in-scope units, above E = ⌈H / n⌉, where H is the remaining in-scope work due inside the horizon and n the days before its latest due that have free time; slope 1/h. Its weight comes from the spread dial |
| `time_preference` | preferences | price, forbids | scope | A slot matches if its weekday is in `days` (or not in `days_except`; default every day) and, when `start`/`end` are given, its local start is in [start, end), which may wrap midnight. A matching slot costs `price`, or is removed if `price = FORBID`. Covers rest days, preferred days and disliked hours |
| `energy` | preferences | price | scope (default energy deep) | `energy_map[weekday][local time bucket]` (points/h) |
| `soft_late` | preferences | price | soft, fixed amount | As `late_work`, for soft deadlines |
| `finish_early` | preferences | price | scope | Finish L = `days` before due: `min(L, max(0, days(end(s) − (due − L))))`. The overflow slot uses the same formula at the horizon end |
| `unscheduled` | preferences | price (overflow only) | fixed amount, not hard-due inside the horizon | `base × imp` per overflow hour. Without it, work with no deadline would never be placed |
| `after_event` | preferences | price | scope | Pulls items to start right after matching fixed items (`events`: an EventScope). Reference time E per day: the end (with buffer) of the day's last match (`measure_from = last`), or of the most recent match before the slot (`any`). A slot at or after E costs `min(cap, slope × hours(start(s) − E))`; before E it costs `cap`. Days with no match: `on_days_without = ignore` (free) or `cap` |
| `chunk_cost` | preferences | measure | split, chunk_cost > 0 | Σ starts, above 1; slope `chunk_cost × size_hours` per extra chunk |
| `spread` | preferences | measure | spread items | Per day: units placed, above ⌈remaining / available days⌉; slope 1/h |
| `cluster` | preferences | measure | cluster items | Days used (`any_of` per day), above 1; slope `per_day` per extra day |
| `batch_by_day` | preferences | measure | scope, grouped `by` area or preset | Per group and day, a helper `y[g,d] ≥ x[i,s]` for every in-scope item of the group and slot of the day. Measure = Σ_d y[g,d]: each extra day a group spreads across costs the weight |
| `target_shortfall` | preferences | measure | target | h = progress + placed in the window. `curve` lists below-hinges at fractions of T′ (target + carry; scaled by the share of the window inside the horizon when the window runs past it), slopes per hour. Decreasing slopes make the first hours count most. Hours above T′ are free |
| `elastic_shortfall` | preferences | measure | elastic | Placed + progress: below `min` slope `steep`, below `ideal` slope `gentle` |
| `open_value` | preferences | measure | open | Per item and day: placed + that day's progress, below-hinges at fractions of the daily ceiling (default curve `[[0.5, 1], [1.0, 0.5]]`). So the first hours of a day are worth the most and later ones less. Slopes × the growth dial |
| `minimize_changes` | preferences | measure | non-tentative, non-open | Units of the current plan given up: Σ over current ∩ allowed of (1 − x). Slope 1 point per hour; preferred-pin units use `preferred_multiplier`. Past or removed slots are ignored. A trade, not a guarantee |

**Dials.** Where a dial affects a rule (section 10), the rule multiplies its weight or threshold by the day's factor from `problem.scales[day]`. Measures that span several days use each day's own factor for that day's part. A factor of 0 switches the rule off for that day.

**How open items find their place.** An open item's first hour in a day is worth 1.5 points at the default growth (1 + 0.5 from the curve), and later hours 0.5. Keeping reserve free is worth 2 points an hour. So at Normal pace a side project fills free time outside the reserve. At Push pace (growth 2, rest 0.5) its first hours are worth 3, more than the reserve's 1, so it starts using evenings. At Easy pace (growth 0) it isn't placed at all. These numbers are starting values to tune in real use.

### 7.3 Sleep

Sleep is a setting, not an item: per-weekday bedtime, wake and margin, plus day overrides. The protected core (bedtime + margin → wake) is pruned for every item, and `late_night` prices the evening gradient and the margin.

**Sleep debt.** For night n, D_n is the hours of recorded progress inside the margins of the previous three nights. The night's multiplier is m_n = 1 + `debt_factor` × D_n (default `debt_factor` 0.5). D_n only uses past nights, so m_n is a constant when the model is built, and prices stay linear. Short sleep last night makes working into the margin tonight more expensive.

### 7.4 Reference rules (defaults)

```toml
rules = [
  { type = "late_work",         name = "late_work",         weight = 10,  params = { overflow_extra_hours = 48 } },
  { type = "quota",             name = "quota",             weight = 3 },
  { type = "late_night",        name = "late_night",                      params = { gradient_start = "22:00", a = 2, b = 20, debt_factor = 0.5 } },
  { type = "deep_run",          name = "deep_run",          weight = 4,   params = { threshold = "3h" } },
  { type = "reserve",           name = "weekday_evenings",  weight = 2,   params = { days_except = ["sat", "sun"], start = "18:00", end = "23:00", free = "2h" } },
  { type = "reserve",           name = "weekends",          weight = 2,   params = { days = ["sat", "sun"], start = "10:00", end = "23:00", free = "4h" } },
  { type = "daily_load",        name = "daily_load",        weight = 5,   params = { threshold = "8h" } },
  { type = "even_load",         name = "even_load",         weight = 1 },
  { type = "energy",            name = "energy",            weight = 1 },
  { type = "soft_late",         name = "soft_late",         weight = 3 },
  { type = "unscheduled",       name = "unscheduled",       weight = 0.5, params = { base = 1 } },
  { type = "chunk_cost",        name = "chunk_cost",        weight = 10 },
  { type = "spread",            name = "spread",            weight = 3 },
  { type = "cluster",           name = "cluster",           weight = 3,   params = { per_day = 2 } },
  { type = "target_shortfall",  name = "target_shortfall",                params = { curve = [[0.4, 8], [1.0, 3]] } },
  { type = "elastic_shortfall", name = "elastic_shortfall",               params = { steep = 20, gentle = 2 } },
  { type = "open_value",        name = "open_value",                      params = { curve = [[0.5, 1], [1.0, 0.5]] } },
  { type = "minimize_changes",  name = "minimize_changes",  weight = 1,   params = { preferred_multiplier = 10 } },
]
```

Personal rules (a rest day via `time_preference`, area days, `after_event` habits) are added on top.

## 8. Allocator, lock checks and what_if

The allocator decides, at day resolution, how much of each item happens on which day over the next `allocator_weeks`. It then hands the scheduler weekly quotas for the items that would otherwise get no pressure.

### Allocator inputs

- **Days 0 … A−1**, each with a capacity in units: `floor(utilization × free_units_d)`, capped at the day cap.
    - `free_units_d` is the day's units minus blocking fixed items (known from materialized occurrences), the sleep core, and the free hours that reserve rules keep.
    - `utilization` defaults to 0.8 and is multiplied by the day's capacity factor (10), capped at 0.95.
    - Elastic items' ideal amounts are subtracted from their days' capacity.
    - Target items reserve their weekly target (× the growth factor) spread evenly over the window's days.
    - Open items reserve nothing. They only use time left over, which is the point.
    - Days beyond the current pace period use the default pace's dials.
- **Items:** every todo flexible item with a fixed amount and remaining > 0. Each has remaining units, release day, due day (if any), firmness, importance, pacing curve (from the preset; default `linear` for Project, `none` otherwise), and dependencies.

### Allocator model

- `y[i,d]` ≥ 0 integer units, for days from release onward. Hard-due items may run past due (late days are priced).
- `over_i` ≥ 0.
- Σ_i y[i,d] ≤ cap_d.
- Σ_d y[i,d] + over_i = remaining_i.
- **Dependencies at day level.** A boolean `ok[A,d]` means "enough of A is done before day d". It is defined by `(N_A − P_A) × ok[A,d] ≤ Σ_{d' < d − lag_days} y[A,d']`, and `y[B,d] ≤ remaining_B × ok[A,d]`.
- **Stage 1 (lateness):** Σ_i imp × (units on days after due × days late) + overflow priced as `late_work` if due ≤ day A−1.
- **Stage 2 (pacing and shape):**
    - Pacing hinges at every week boundary b: `deficit = p_i(b) × total_i − (P_i + Σ_{d<b} y[i,d])`, below 0 free, slope `pacing_weight` per hour.
    - Whole-day prices from rules that expose `day_price(item, date)`. `time_preference` with no time window implements it as price × hours.
    - A tiny earliness price ε × d makes ties deterministic and earlier.
- Each stage is solved with CP-SAT and a deterministic limit of about 1 s. The problem is small: items × days.

**Pacing curve:** `p(τ) = ((τ − r) / (D − r))^k`, with k = 1 (`linear`), 0.7 (`front`) or 1.5 (`back`). r is the release (or the item's creation if none), D is the due date, and the result is clipped to [0, 1]. "Half a four-week project in the first two weeks" is the linear line.

### Allocator output

`Allocation`: `y` per item and day, plus `quota[i][week]` = Σ y[i,d] over the days of that week that lie inside the scheduler horizon. Quotas are only passed for items whose due is beyond the horizon end, or that have no due but have pacing. Items due inside the horizon are already handled by `late_work`.

The allocator's day totals are shown in the weekly view as "planned load" for weeks 3–12.

### 8.1 Lock checks (before any solve)

- Overlapping locks: the more recently created one stays locked; the older becomes a preferred pin.
- A lock over a fixed item becomes preferred.
- Locks exceeding an item's remaining work raise its remaining work.
- Locks exceeding a day cap raise that day's cap.
- A one-sitting lock that can't grow to the item's full length becomes preferred.

After these checks the problem cannot be contradictory.

### 8.2 what_if and lock conflicts

`what_if(problem, change)` returns `{item: extra late hours}` by solving the deadlines stage before and after a change in memory. **Lock conflicts:** if locked pins exist and the deadlines value is > 0, run `what_if` with every lock turned into a preferred pin; if lateness drops by more than 1 point, find the responsible pins with one `what_if` per locked pin (at most 10) and report them ("Locked Gym Thu 18:00 makes PS4 1.5 h late").

## 9. Executor (exact feasibility, milliseconds)

Pure functions over a light input: now, the free-time intervals, and the hard-deadline jobs. No solver is involved.

### 9.1 Inputs

- **Free time:** the intervals from now until the latest hard due. It excludes blocking fixed items with buffers, sleep cores, and other items' locked pins.
- **Daily caps are ignored here**, so the check is slightly optimistic. The scheduler still enforces caps.
- **Jobs:** every todo item with `firmness = hard`, a due time and remaining minutes > 0, plus its release. Minimum chunks are ignored, since splitting is assumed free. This is noted wherever slack is shown.

### 9.2 Feasibility: earliest-deadline-first

The jobs are simulated over free time. At each moment, the released, unfinished job with the earliest due runs. Ties go to higher importance, then lower id.

For one worker, splittable jobs and release times, this order is optimal for maximum lateness. So it is an **exact** feasibility test, not a heuristic. Output: each job's finish time, and `L_max` = the largest finish − due (≤ 0 means feasible).

### 9.3 Latest starts and slack

The same simulation runs **backwards** from the latest due. In reversed time, due dates act as release times and the job with the latest original release runs first. This gives an as-late-as-possible schedule.

- An item's **latest start** `L_i` is the start of its earliest piece in that schedule.
- **Slack** = `L_i − now`, in wall time. It is also reported as free minutes between now and `L_i`.
- If the jobs are infeasible, slack is negative for the jobs that cause it.

This latest start is conservative: it assumes every other job is also left as late as possible. That is the safe direction for warnings.

### 9.4 Safe swaps

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

## 10. Dials and paces

Your settings say how Friday plans a normal day. The **dials** say how hard to push right now. They scale a few settings up or down per day, and nothing else. The engine, the stages and the deadline guarantee don't change: a dial can make the days around a hard deadline lighter or fuller, but it can never make the deadline itself give way.

**The four dials:**

| Dial | Range | Normal | What it scales, per day |
| --- | --- | --- | --- |
| `capacity` | 0.3–1.5 | 1.0 | `daily_load` threshold × c; `deep_run` threshold × c (never below 1 h); allocator utilization × c (at most 0.95) |
| `rest` | 0.5–3 | 1.0 | `reserve` free hours × r; `late_night` weight × r; sleep `debt_factor` × r |
| `spread` | 0–5 | 1.0 | `even_load` weight × s (how evenly hard work is spread across days) |
| `growth` | 0–3 | 1.0 | `open_value` slopes × g; `target_shortfall` weight and target amounts × g |

`scales(dials) -> DayScales` turns dials into these named factors. The sleep core, the hard daily cap and every forbid rule are not dials: no pace can touch them.

**Paces** are saved dial settings. The shipped ones (editable):

| Pace | capacity | rest | spread | growth | For |
| --- | --- | --- | --- | --- | --- |
| Normal (default) | 1.0 | 1.0 | 1.0 | 1.0 | Most weeks |
| Easy | 0.6 | 2.0 | 3.0 | 0 | Sick or worn out: light, even days, nothing optional |
| Push | 1.2 | 0.5 | 1.0 | 2.0 | Motivated: side projects and goals fill free time and evenings |

**Pace periods.** A pace applies to whole planning days for a set duration or until changed; days outside a period use the default pace. The first replan after a switch multiplies `minimize_changes` by 0.2 so the plan can actually change.

**When a pace can't be honoured.** The deadlines stage still comes first. If hard work due soon doesn't fit the lighter days, Friday plans it anyway and reports which days the pace couldn't protect.

**Learning.** Every plan records each day's dials, so the dials of any past day can be looked up. Learning (section 11) must condition on them, or a sick week will teach Friday that you're slow.

## 11. Learning (v2 outline, never built)

The goal is to learn durations, energy and preferences from what you do, without being wishy-washy or slow. The answer to the learning-rate problem is to model uncertainty explicitly: consistent evidence moves an estimate quickly, and one odd day barely moves it. The approach:

- **Data:** every pin and manual move (a revealed preference), progress records (when and how long), completions.
- **Durations:** a hierarchical log-normal model (item type → area → all), with partial pooling. Scheduling uses quantiles: p50 for flexible items, p80 for hard-deadline items. A bias multiplier comes with its uncertainty.
- **Energy:** a Beta–Binomial "block happened as planned" estimate and a speed ratio (actual ÷ estimate) per hour-of-week cell, smoothed across neighbouring cells, plus optional one-tap check-ins. Bounded exploration avoids self-fulfilling estimates. The output is `energy_map`.
- **Weights:** inverse optimization. The objective is linear in the weights, so each manual move gives the inequality w · (φ(yours) − φ(Friday's)) ≤ 0. Fit with a max-margin method regularized toward the current weights, with a step cap.
- **The learned layer:** a versioned `learned_profile`, separate from your settings, with per-module modes **off / suggest / auto within bounds**, a weekly digest of changes with their evidence, and reset. Plans record the profile version, so determinism holds.
- **Dials are context, not evidence about you.** Every observation is tagged with its day's dials. Durations and energy are learned from default-pace days, or with the dials as a covariate. Weights are never learned from moves made in the replan right after a pace switch.
- **Evaluated on the simulator first** (section 12.3), against users with known hidden preferences.

## 12. Tests and benchmark

### 12.1 Scenario tests (each with its own small rule set)

| # | Setup | Expected |
| --- | --- | --- |
| 1 | A rest-day `time_preference`; the only free time before a hard deadline is on the rest day | Work goes on the rest day; no late work |
| 2 | More work than fits in the horizon | A plan is returned with overflow reported; never infeasible |
| 3 | A locked pin that makes another item late | The lock check names that pin and the extra late hours |
| 4 | Replan with nothing changed | Identical plan; nothing moved |
| 5 | A preferred pin and a slightly cheaper slot elsewhere | The block stays |
| 6 | A one-sitting 2 h item where splitting would be cheaper | One contiguous block; with no 2 h gap, all of it overflows |
| 7 | A target item whose only free slots are expensive | Placed only where the shortfall slope beats the slot price |
| 8 | `batch_by_day` plus a Saturday `time_preference`; three chores | All on Saturday |
| 9 | `late_night`; work that fits before or after 23:00 | Before, unless a deadline needs otherwise |
| 10 | A horizon containing a daylight-saving change | That day has 4 more or fewer fine slots; blocks map to the right UTC times |
| 11 | Any solved plan | Every rule total from `explain` equals the solver's objective for its stage |
| 12 | B depends on A; both fit only in one order | A before B |
| 13 | B after 50% of A with a 1-day lag | B starts ≥ 1 day after half of A is placed |
| 14 | Split item with a 30-min minimum and scattered 15-min gaps | No isolated 15-min pieces |
| 15 | 3 h item; free day; `chunk_cost` on | One chunk, unless a pin forces two |
| 16 | 5 h of deep work; class at 11:00; `deep_run` 3 h | Runs on either side of the class; nothing deep > 3 h straight |
| 17 | Reserve 2 h weekday evenings; light load | Evenings keep ≥ 2 h free |
| 18 | Lunch routine 11:30–14:30, 20–45 min, with a busy day | Lunch placed inside the window at ≥ 20 min |
| 19 | 30 h project due in 6 weeks; light near-term load | Quota places about a linear share in this week and next |
| 20 | Same snapshot solved twice (one worker) | Identical plan |
| 21 | Open item, light week, Normal pace | Fills free time outside reserve; never above its daily ceiling |
| 22 | Same week, Easy pace | Open item not placed; hard work spread so no day exceeds the even share by more than one chunk |
| 23 | Same week, Push pace | Open item also uses reserve evenings; sleep core untouched |
| 24 | Easy pace, hard work that can't fit in light days | All deadlines met; a pace notice names each overloaded day |

### 12.2 Properties

- No slot holds two items; never infeasible without contradictory locks; a later stage never raises an earlier stage's value; explanation totals equal stage objectives.
- EDF feasibility agrees with brute force on small instances (≤ 6 jobs); a safe swap never turns feasible into infeasible; slack ≥ 0 iff EDF is feasible.

### 12.3 The v2 simulator design

- **`generate_term(config, seed)`** builds a semester: 4 courses with class series; weekly assignments (lengths log-normal), readings, two exams with prep items, one 20-hour project; meals, chores, two habits and one weekly goal; random social events (2–4 evenings a week) and occasional sick days.
- **The simulated user** has hidden per-area duration multipliers, an energy curve, start delays, a skip probability, a probability of taking a safe swap, and noisy reviews.
- **Metrics:** hard deadlines missed, late hours, plan churn (hours moved per day), adherence, solve times.

### 12.4 Benchmark

Generated snapshots: 20, 40 and 60 items; 14 days; about 15 h of fixed items a week; 3 pins; 5 dependencies; the reference rules; seeds 0–9. Cold and warm (warm = the previous plan plus 2 added and 1 removed item). Record machine, sizes, stage times, status, objective and bound.

**Targets on the laptop:**
- warm replan p90 ≤ 3 s;
- cold p90 ≤ 10 s;
- deadlines stage ≤ 3 s;
- allocator ≤ 1 s;
- executor answers ≤ 50 ms at 100 items.
