## 15. Program 2 specification: the engine behind the Friday app

Additions to section 12, all implemented in `src/fr/product/` and exposed to the app by `fr-serve` (`PROTOCOL.md`).

### 15.1 Contract with the app

- **Process**: the app starts `fr-serve` once and keeps it running (as it already runs the `claude` CLI): JSON lines over
  stdin / stdout, one reply per request, a `ready` line after warm-up. No port, no HTTP stack, no network.
- **Inputs**: Todo List's own task records (`todos.json` entries: id, title, bucket, due date, progress in quarters, done)
  and EventKit events (title, start, end, all-day). Course from a course code in the title; task kind from the bucket and
  title words (problem set, reading, essay, lab, exam prep, project, email, other).
- **State**: one JSON file in `~/Library/Application Support/Friday/engine/` (estimates, recorded lengths, confirmed and
  pending constraints, picks, the last plans). Never `todos.json`: Todo List drops keys it does not know.
- **Methods**: `set_estimate`, `record_actual`, `predict`, `questions` / `mark_asked`, `parse_constraints` /
  `confirm_constraints` / `list_constraints` / `remove_constraint`, `plan`, `pick` (table in `PROTOCOL.md`).
- **Determinism**: everything but `parse_constraints` is a function of the stored state and the snapshot (fixed step
  budgets, seeded chains).

### 15.2 Durations

SPEC_DURATIONS_PLACEHOLDER

### 15.3 Three schedules and learning from the pick

SPEC_OPTIONS_PLACEHOLDER

### 15.4 Constraints from text

- Claude Sonnet 5.5 via `claude -p --model claude-sonnet-5-5 --tools "" --strict-mcp-config --no-session-persistence
  --system-prompt <guide v2> --json-schema <Parse schema>`; one retry with the validation error if a reply does not
  validate (never needed in E019).
- Twelve constraint kinds + questions + unsupported (section 14.1). The user confirms each paraphrase; only then is it
  stored. Stored constraints compile on every plan: hard -> walls, soft -> weighted rules (mild 1, medium 3, strong 8
  points per hour or weight multiplier).
- Constraints are the user's own rules: they are never learned or softened by Friday (section 8's wall policy applies:
  if one makes the week impossible, ask once).

### 15.5 What the app must build (frontend)

A field or timer to record how long a task took (`record_actual`), a "how long?" field when adding a task
(`set_estimate`), a once-a-day question card (`questions`), a "plan my week" view showing three options side by side with
their labels and summaries (`plan`, `pick`), and a "tell Friday about your week" box with a confirmation sheet
(`parse_constraints`, `confirm_constraints`). `fr-demo` prints the whole flow on sample data.
