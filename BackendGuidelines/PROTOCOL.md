# Friday app <-> engine protocol (version 1)

How the Friday macOS app (`../UI`) talks to the v3 engine. Code: `src/fr/product/serve.py` (transport),
`service.py` (operations), `adapter.py` (app data -> engine), `constraints.py` (typed constraints), `parse.py` (Claude).

## Transport

The app launches one long-lived child process, the way it already launches the `claude` CLI:

```
<repo>/BackendGuidelines/.venv/bin/fr-serve [--data DIR] [--steps N]
```

- stdin / stdout carry **JSON lines**: one request per line, one reply per line, in order.
- The first line the engine writes is `{"ready": true, "protocol": 1, "warmup_s": ...}` after compiled code is warm
  (a few seconds with the numba cache; about a minute on a cold first run). Send nothing before it.
- Request: `{"id": 7, "method": "plan", "params": {...}}`. Reply: `{"id": 7, "result": ...}` or
  `{"id": 7, "error": {"type": "KeyError", "message": "..."}}`. The process keeps serving after an error.
- Diagnostics go to stderr only. Close stdin to stop the process.
- State lives in `DIR/engine.json` (default `~/Library/Application Support/Friday/engine/`), written atomically. Nothing
  is ever written to `todos.json` (Todo List drops keys it does not know).
- Times: the app may send ISO 8601 in UTC (`"2026-10-20T03:59:00Z"`, as Todo List writes `dueDate`) or local wall time
  without an offset. The engine plans in local wall time and replies in local wall time without an offset
  (`"2026-10-20T14:30"`).

## Shared shapes

- **todo**: an entry of `todos.json` as Todo List writes it: `id` (UUID string), `title`, `horizon`, `bucket`
  (`assignments` | `readings` | `emails` | `other`), `isDone`, `dueDate` (optional), `progress` (0-3 quarters). Optional
  extra key `course` overrides the course found in the title (a code like `CS 2110`).
- **event**: `{"title", "start", "end", "isAllDay"}` from EventKit. All-day events never block time. Titles with a course
  code or "lecture / section / discussion / recitation / seminar" count as classes (class buffers apply).
- **now**: optional on every call that plans or predicts; default the engine's clock.

## Methods

| method | params | result |
| --- | --- | --- |
| `hello` | - | `{protocol, data_dir}` |
| `set_estimate` | `task_id`, `minutes` | `{ok}`: the user's preliminary estimate for one task |
| `record_actual` | `task` (a todo), `minutes` | `{ok, recorded}`: how long a finished task really took (from a timer or the user) |
| `predict` | `todos`, `now?` | per open task id: `p50`, `p80` (minutes), `plan_minutes` (what the plan reserves: the p50 for flexible tasks, the p80 for hard deadlines, times the share not yet done), `estimate`, `similar_recorded`, `kind`, `course`, `spread` |
| `questions` | `todos`, `now?` | `{estimates: [{task_id, title, guess_minutes}], actuals: [{task_id, title}]}`: at most two estimates Friday wants (unsure, hard deadline first) and at most three finished tasks nobody timed. After asking, call `mark_asked` so it is not asked again. |
| `mark_asked` | `task_id` | `{ok}` |
| `parse_constraints` | `text`, `todos?`, `events?`, `now?` | `{ok, pending_id, constraints: [{index, kind, paraphrase, hard}], questions, unsupported: [{source, reason}]}`. Calls Claude (Sonnet 5.5 via the `claude` CLI, no tools, ~3 s). **Nothing applies yet.** Show each paraphrase with a checkbox; show `questions` and `unsupported` as they are. |
| `confirm_constraints` | `pending_id`, `accept` (list of indexes) | `{ok, added: [ids]}`: only accepted constraints are stored |
| `list_constraints` | - | `[{id, paraphrase, kind, text}]` |
| `remove_constraint` | `id` | `{ok}` |
| `plan` | `todos`, `events`, `now?`, `method?` | `{plan_id, options: [3 x {option, label, summary, blocks: [{task_id, start, end}], late_tasks, unplaced_tasks, valid}], notes, minutes}`. Option 0 is the recommended plan. `summary` says how an option differs ("Less late-night work, more busy weekends."). Blocks cover the next 14 days. |
| `pick` | `plan_id`, `option` | `{ok, picks, weights}`: the user chose this option; Friday learns from it |

## What the app needs to add (frontend, not built here)

1. **Estimates**: when a task is added (or from a "how long?" field), call `set_estimate`. Show `predict`'s `p50` next
   to tasks once there is history ("Friday thinks 3 h 20 m, you said 2 h").
2. **Recording**: a start / stop timer or a "took me ..." prompt when a task is ticked, then `record_actual`. Ticking
   without a time is fine; `questions.actuals` will ask later for a few.
3. **Asking**: at most once a day, show `questions` (two estimates, three lengths); then `mark_asked`.
4. **Three schedules**: a "Plan my week" action calls `plan`; show the three options side by side on the calendar
   (blocks as tentative events), with `label` and `summary`; on choosing, call `pick` and write that option's blocks.
5. **Constraints**: a text box ("Tell Friday about your week"), `parse_constraints`, a confirmation sheet, then
   `confirm_constraints`; a list with delete (`list_constraints`, `remove_constraint`).

## Guarantees

- Every option keeps the hard rules: nothing on top of a timed event or inside the sleep core, confirmed hard
  constraints are never broken, and no option is later on a hard deadline than it has to be.
- `plan` is deterministic for the same stored state and snapshot (fixed step budgets).
- Claude is only called by `parse_constraints`, and its output is stored only after `confirm_constraints`.
