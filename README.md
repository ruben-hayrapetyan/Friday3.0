<p align="center">
  <img src="UI/docs/icon.png" width="128" height="128" alt="Friday's icon: a white F inside a ring that is most of the way closed">
</p>

# Friday

[Chroma](https://github.com/ruben-hayrapetyan/chroma) and
[Todo List](https://github.com/ruben-hayrapetyan/ToDo) as one Mac app, with
a planner that fits your tasks around your week. The calendar has the window
to itself, your tasks live in a drawer that slides out over its right side,
and the Planner turns the page to three schedules for the next two weeks.
Everything each app did on its own still works here; what's new is what
happens between them.

**This is the `personal` branch: the copy of Friday in daily use.** It is
the general app ([`v1.0.0`](https://github.com/ruben-hayrapetyan/Friday/tree/v1.0.0)),
plus the Planner and the engine behind it ([`BackendGuidelines/`](BackendGuidelines)),
plus two buttons for one person's calendars: TA & advising hours and Library
Rooms. `main` is empty, kept for a fresh start.

![Friday's week view: the sidebar, and the calendar with task deadlines written in each day's margin lane](UI/docs/week-light.png)

![The same week with the tasks drawer open over the calendar's right side](UI/docs/week-tasks-light.png)

*Rendered from the real views by `UI/tools/snapshot.sh` with invented sample data — not a real calendar or task list.*

## Getting it running

The app lives in [`UI/`](UI). Build it and install it into Applications:

```bash
cd UI
./build.sh --install
```

The Planner needs its engine, a Python program in
[`BackendGuidelines/`](BackendGuidelines). Set it up once — it needs
[uv](https://docs.astral.sh/uv/), which brings Python 3.12:

```bash
cd BackendGuidelines && uv sync
ln -s "$PWD/.venv/bin/fr-serve" ~/.local/bin/fr-serve   # or choose it in Settings › Planner
```

Rules typed in plain language, and judging which events you could skip, use
Claude through Claude Code's `claude` command — the same one Ask Claude uses.
Without it the Planner still plans; rules can't be added, and events are
judged by their titles alone.

Or make the zip to hand to someone else — `./build.sh --release` builds for
Apple silicon and Intel and packs the app with
[`QUICKSTART.txt`](UI/QUICKSTART.txt) (as `Quick Start.txt`), which walks
through opening an app that isn't notarized, the calendar and Documents
prompts, and the first few minutes. Needs macOS 14 or later.

## Where it comes from

| App | Repository | What Friday takes from it |
| --- | --- | --- |
| **Chroma** | [github.com/ruben-hayrapetyan/chroma](https://github.com/ruben-hayrapetyan/chroma) | The calendar: EventKit, per-event colour, category rules, day/week/month/year, Ask Claude |
| **Todo List** | [github.com/ruben-hayrapetyan/ToDo](https://github.com/ruben-hayrapetyan/ToDo) | The tasks: short and long term, the Due page, due dates and countdowns, progress in quarters |

Built from the general versions of both, not from anyone's personal
branch: **Todo List 1.0.2** (`main`, cd3ecd8), and **Chroma 1.0.1**
(`main`, 758bab8) with the fixes from Chroma's whole-app review (`main`,
4b5d995). Chroma's Google Calendar source isn't part of Friday; it reads
calendars through macOS. Friday works on the same files as both apps (see
[Your data](#your-data)), so either can be used alongside it, one at a time.

The Planner and its engine are Friday's own. The engine came out of the
research in `BackendGuidelines/` — how it was chosen is in
[`REPORT.md`](BackendGuidelines/REPORT.md), and every change since, most of
them from using it on a real week, is in
[`RESEARCH_LOG.md`](BackendGuidelines/RESEARCH_LOG.md) (decisions 36–45).

## Build, test, look

```bash
cd UI
./build.sh             # build/Friday.app for this Mac
./build.sh --install   # replace /Applications/Friday.app and launch it
./build.sh --release   # Apple silicon + Intel, zipped with QUICKSTART.txt into build/
./test.sh              # task model, store, lengths and stopwatch tests — no window, no real data
./tools/snapshot.sh    # renders the window with sample data into build/snapshots

cd ../BackendGuidelines
uv run pytest          # the engine's tests
```

The app needs macOS 14 and the Xcode Command Line Tools — no Xcode project,
no dependencies.

## The tasks drawer

**Tasks** in the calendar's title row — or `⌃⌘T`, or `⌃⌥Space` from any app —
slides the notebook out over the right side of the calendar, and the same
button puts it away. It hangs below the title row, so the button that opened
it is always in reach. **Drag its left edge** to make it wider or narrower;
Friday keeps the width for next time. The sidebar folds away too, from the
button at the start of the title row (`⌃⌘S`).

The drawer holds whatever you are working on: the notebook, or the event you
just opened or are drafting. Closing the event brings the notebook back if it
was out.

## How the two halves meet

**Each day carries its own to-do list.** In day and week view, a day with
something due gives part of its column to a lane down the right — a strip a
shade darker than the page, like a ruled margin — holding that day's tasks
as one list: every task due that day, in the order they fall due. The list
is pinned to the top of the window and moves with you as you scroll, so
nothing due that day is ever out of sight; a list longer than the window
runs on below and comes to rest at the end of the day. Its rows are the
notebook's own: ticking one off fills the box and lets it ease down to the
bottom, exactly as in the notebook, and the countdown, progress, star, date,
double-click to rename, right-click menu and keys all work the same. In
week view's narrow lanes a row keeps to its checkbox and title, and the
pointer shows the whole title. Events lay out in the rest of the column, so
a task never sits on an event, and a day with nothing due keeps its whole
width. Opening the tasks drawer swaps the day lists for the full list: they
step aside while it is out, and come back when it is put away. In month view a day's deadlines follow its events, always with a line
kept for them.

**Drag a task onto the calendar to give it a date.** Drop it on a day in
month view, the mini month, the all-day row or the agenda, and it keeps the time
it had (or takes 11:59 PM, which is what a bare date means everywhere else).
Drop it into the hour grid and it's due at the quarter hour it landed on.
One ⌘Z undoes it.

**One agenda for the day.** The sidebar lists the selected day's events and
deadlines in a single timeline, by the clock.

**One "now".** The red line across today's grid, the red line that splits
today's agenda into done and to come, the red line that separates overdue
tasks from upcoming ones on the Due page, and the red of an overdue countdown
are the same hue and the same mark. It is the only colour in the chrome.

**One search.** ⌘F looks through tasks and events together.

**One drawer.** Opening or drafting an event opens it in the drawer;
clicking any deadline turns the drawer to that task.

<p align="center">
  <img src="UI/docs/draft-light.png" width="720" alt="A new event being drafted: a dashed block in the week grid and the form in the drawer">
  <br><sub>Drafting an event: the dashed block on the calendar and the form in the drawer are the same draft</sub>
</p>

**Tasks never wait on the calendar.** While macOS is still asking for
calendar access, or before a main calendar is chosen, the Tasks button and
the drawer already work.

## The Planner

**Planner** in the calendar's title row — or `⌃⌘P` — turns the page from the
calendar to the Planner, and **Calendar** in its title row turns it back. The
sidebar stays where it is. It has three sections — **plan**, **lengths** and
**rules** — and the plan you pick comes back to the calendar.

![The Planner's plan page: three schedules side by side, why two tasks are late, and three events Friday asks whether you could skip](UI/docs/planner-light.png)

### plan

**Plan my week** makes three schedules for the next two weeks from your open
tasks, your calendar, how long things take you and your rules. Each is a
card: the hours of work it plans and in how many sessions, how many tasks
are late or don't fit, the next seven days at a glance, and its shape
in a line ("latest 5 PM · after 9 PM none · weekend free"). The first is the
one Friday expects you to pick; the other two differ in ways it isn't sure
you'd like ("Freer weekday evenings and less late-night work; busier
weekends"). **Preview** lays an option over the calendar, and below the
cards the recommended one runs day by day, your events in grey between the
work. **Pick this** puts it on the calendar, and the next recommendation
leans toward what you picked.

**Planning around** says what Friday treats as busy. Not everything on a
calendar is a commitment: it leaves out the TA and advising hours your
filter matches, room bookings, events marked free, invitations you declined,
and reminders that only say something is due. Each thing left out is a chip;
click it to plan around it after all.

**When more is due than fits**, a panel under the cards says so in numbers
("9 tasks due by Thu 22 Oct 23:59 need 31 h … your rules and calendar leave
26 h before then"), then lists each late task with when it would be done and
how late, or that it doesn't fit in the two weeks at all. Then it asks
**Could you skip any of these?** — the events before then that matter
least, least important first, with the time each would free. Claude rates
each event title once (required, likely or optional); classes, labs, exams,
shifts and appointments are never offered. A **Going | Skip** switch answers
each one. A skipped event stays on your calendar and only stops blocking
time in the plan; *Going* means Friday stops asking about it. Three show at
a time, the rest under **Show more**, and your answers fold into one line
you can open to change them. Two more ways out sit at the bottom: lower an
estimate, or allow longer days.

### On the calendar

The picked plan is drawn in the day and week grids as work blocks, laid out
with your events so nothing overlaps; a daily break from your rules (lunch)
shows as its own block. **Click a block** for large **Start**, **Pause** and
**Done** buttons. The running stopwatch sits in the calendar's title row, so
you never need the Planner open while you work. Picking again replaces the
plan still ahead and keeps any block already begun. The blocks are Friday's
own and never written to your calendars; right-click one to remove it, or to
clear Friday's plan from the calendar.

### lengths

<p align="center">
  <img src="UI/docs/lengths-light.png" width="720" alt="The lengths section: two questions from Friday, then each task with its due date, your estimate, what Friday expects and a Start button">
  <br><sub>Each task with your estimate, what Friday expects and plans, and its stopwatch; ⏳ marks work that is pointless once late</sub>
</p>

Every open task, with your estimate, what Friday expects, and a stopwatch.
**Estimates are typed the way due dates are**, with a live reading as you
type: "90 min", "1h30", "an hour and a half", "a couple of hours",
"2–3 hours", "maybe 3h?". **The stopwatch** starts with **Start**, pauses for
a task done in several sittings, and **End** records the time and ticks the
task off. It survives quitting Friday, only one runs at a time, and one left
going for hours asks whether the time is real. Now and then *Friday would
like to know* asks for an estimate it is unsure of, or how long a finished
task took — at most two at a time, and at most two finished tasks a week.

Until you've timed three tasks of a kind (the same course, the same sort of
work), Friday plans by your estimate with a small cushion: at most a quarter
more, or half more than its own guess when you gave none. After that it
plans from how long those tasks really took you, never more than twice your
estimate.

The task list's right-click menu has the same: **Estimate Length…**, the
stopwatch, and **Pointless If Late**.

### rules

Tell Friday about your week in your own words ("No work after 11pm. Gym MWF
7–8:30am. I can't focus for more than 90 minutes"), or start from a chip:
sleep, no work, commitment, focus limit, best hours. `⇧↩` sends it to Claude
(Sonnet 5.5), which translates it into rules; each comes back as one
sentence with a checkbox, and only the ones you tick are kept. What the
rules can't express, Claude says so rather than guessing. Rules can say:

- when you sleep, when you never work, and when you'd rather not;
- fixed commitments, buffers around classes, and a limit on a day's work;
- how long you can focus, and your best hours;
- doing things in one sitting — and which work to split first if not;
- a daily break that moves within a window, such as lunch with time to get there;
- concentrating on an exam's course in the days before it, leaving the rest for after;
- what comes first ("Prioritize assignments over readings");
- work that is pointless once its deadline has passed.

Claude never plans; the engine does.

### How Friday plans

- **Every due date is a deadline**, and lateness costs more the later it is:
  an hour late costs little, a day late a great deal, and each late task
  counts on its own. Urgent work comes first.
- **Far-off work waits.** A task isn't planned until about a week before its
  due, a day earlier for every two hours of work in it.
- **Parts of a set go in order.** Tasks of the same course and kind due
  together — the two halves of a problem set — are done one after the
  other, not alternating.
- **Some work is pointless late.** Exam and quiz prep — study guides, review
  sheets, practice exams — is due when that course's exam or quiz starts,
  and is never planned after it. Mark anything else **Pointless If Late**;
  ⏳ shows beside it in the task list, the day lists and lengths. When not
  all of it fits, the late panel says how much does.
- **It learns from what you pick**, and from how long things take you.

### The engine

The planning is the Friday engine, `fr-serve`, from
[`BackendGuidelines/`](BackendGuidelines). Friday starts it the first time the
Planner needs it and keeps it running, talking JSON lines over its standard
input and output ([`PROTOCOL.md`](BackendGuidelines/PROTOCOL.md)). Its first
start compiles the scheduler (about a minute); later starts take a few
seconds and a plan about three. If the engine lives under `~/Downloads`,
macOS asks once whether Friday may open files there.

## Two buttons for one calendar

This branch's own additions to the calendar's title row, carried over from
Chroma's personal branch:

- **TA & advising hours** (`⇧⌘O`) shows or hides the office hours and drop-ins
  that the filter in `categories.json` matches. The button only appears while
  that filter exists.
- **Library Rooms** (`⇧⌘L`) shows or hides the shared study-room bookings
  calendar, connecting it in violet the first time. Until that calendar has
  reached this Mac the button says so, and the menu item is greyed out.

## The icon counts down to Friday

<p align="center">
  <img src="UI/docs/icon-week.png" width="840" alt="Seven icons, Saturday to Friday: a white F inside a ring that sweeps round clockwise, closing in gold on Friday">
</p>

One mark on a deep navy square, the way Apple draws its own icons: a white
**F**, and a ring around it that sweeps clockwise from twelve o'clock as the
week comes round. An open ring reads at any size as *on its way* — the
promise Activity's rings make — so even at a glance the icon says it isn't a
still picture. It starts as Saturday begins, is all but closed by Thursday
night, and on Friday closes in gold, the colour a starred task wears. The F
is SF Rounded, so its ends match the ring's caps. Below 64 pixels the
drawing simplifies, as Apple's do — heavier ring, bigger letter, no shadow —
so it stays an F in a ring rather than a smudge.

The Dock shows it live while Friday runs, redrawn as the day changes and
every half hour between. The icon in the app bundle — the one Finder shows —
is fixed at about Thursday, still open.

## The design

The two apps already agreed on paper and ink, a serif for headings and a
monospace for data. Where they disagreed was in the details, and those are
settled once, in `UI/Sources/Design/`:

| | Chroma | Todo List | Friday |
|---|---|---|---|
| Ground | warm cream `#F7F5F1` with white panels | cool `#F4F5F2` with lifted bands | the desk, `#ECEEE9` — cool and faintly green, like an engineering pad — with pages of `#FBFBF8` |
| Small labels | wide sans-serif capitals | mono capitals (`READ` `ASGN`) | mono capitals everywhere: day names, section codes, column labels |
| Tabs | sans-serif, ink underline | lower-case mono, navy underline | one component for both: lower-case mono, underlined in the page's ink |
| Buttons | sans-serif, filled or outlined | mono text links | mono labels with a hairline edge |
| Red | `#C7332A` for the now line | `#C0392B` for overdue | one red, `#C7332A`, for both — and nothing else |
| Checkbox | — | ruled box, ink fill by quarters | the same box wherever a task appears |

The rule behind the type, the same everywhere: **New York** for headings
(what you are looking at), **SF Pro** for what people wrote (task and event
titles, notes, places), **SF Mono** for what Friday prints (times, dates,
counts, codes, tabs, buttons, hints).

The calendar's title row and the notebook's header are built the same way —
serif title on the left, ruled tabs on the right — so the drawer reads as
part of the same planner rather than a second app. The Planner's page is
built the same way again.

<p align="center">
  <img src="UI/docs/month-dark.png" width="720" alt="Month view in dark mode, deadlines in navy ink at the top of each day">
  <br><sub>Month view, dark — each day's deadlines written above its events</sub>
</p>

## Keyboard

| Shortcut | Does |
| --- | --- |
| `⌃⌥Space` | Bring Friday up with the notebook open, from any app — or tuck it away |
| `⌥Space` | New event, from any app |
| `⌃Space` | Ask Claude, from any app |
| `⌘1` `⌘2` `⌘3` `⌘4` | Day / Week / Month / Year |
| `⌃⌘1`–`⌃⌘4`, `⌃⌘L` | New reading, assignment, email, other, long-term task |
| `⌘N` | New event |
| `⌘F` | Search events and tasks |
| `⌘T`, `⌘←` `⌘→` | Today, previous, next |
| `⌃⌘S`, `⌃⌘T` | Show or hide the sidebar, the tasks drawer |
| `⌃⌘P` | Calendar ↔ Planner |
| `⇧↩` | In the Planner's rules: send what you wrote to Claude |
| `⇧⌘O`, `⇧⌘L` | TA & advising hours, Library Rooms |
| `⌥⌘1`–`⌥⌘9`, `⇧⌘K` | Other connected calendars, assign categories |

**Changed from Todo List:** its add-task shortcuts move from `⌘1`–`⌘4` and
`⌘L` to `⌃⌘1`–`⌃⌘4` and `⌃⌘L`, because `⌘1`–`⌘4` pick the calendar's view, as
they do in Calendar.app. The list's own keys (arrows, space, `s`, `d`, `1`–`3`,
`0`, return, delete) act only while a task is selected or the pointer is over
the notebook, so they never take a key press meant for the calendar.

## Your data

Friday works on the same files as Todo List and Chroma, so nothing moves:

- Tasks: `~/Documents/Todo List/todos.json`
- Event colours and category rules: `~/Library/Application Support/Chroma/`
- Events: the calendars macOS already syncs, through EventKit

The Planner keeps its own, and never writes to either:

- Estimates, recorded lengths, rules, picks, skipped events and how much
  each event matters: `~/Library/Application Support/Friday/engine/engine.json`
  (Settings › Planner › Show in Finder). Never in `todos.json`, which Todo
  List would strip.
- The picked plan and any running stopwatch: Friday's own preferences
  (`com.rubenhayrapetyan.friday`). Never written to your calendars.

The first time it runs, Friday copies over the main calendar, connected
calendars and filter setting chosen in Chroma, and the tab last used in Todo
List.

Neither Todo List nor Chroma watches those files, so whichever app writes
last wins. While either one is running, Friday shows a banner offering to
quit it. They also hold the same global shortcuts.

## Layout

| Path | Holds |
| --- | --- |
| `UI/Sources/App/` | Entry point, menus, global hotkeys, login item; the Todo List / Chroma banner and settings import; the icon and its countdown |
| `UI/Sources/Design/` | The tokens (`Theme.swift`) and the shared components: page, tabs, buttons, checkbox, now line |
| `UI/Sources/Shell/` | The window and its drawer, the calendar page, the sidebar and agenda, and `Deadlines.swift` — tasks on the calendar |
| `UI/Sources/Calendar/` | Chroma: EventKit store, categories and colours, the grids, inspector, Ask Claude, Settings; `Personal.swift`, the two buttons above |
| `UI/Sources/Tasks/` | Todo List: the model, the store, selection, keyboard, the notebook page |
| `UI/Sources/Planner/` | The Planner page and its model; the options and the late panel (`OptionViews.swift`); lengths, the length parser and the stopwatch; the plan on the calendar (`Schedule.swift`, `StopwatchViews.swift`); what counts as busy (`Busy.swift`); the client that runs `fr-serve` |
| `UI/Tests/main.swift` | Store, file-format, calendar-bridge, length and stopwatch tests, run by `test.sh` |
| `UI/tools/` | The icon renderer (`MakeIcon/`, also `--week` for the strip above), and the snapshot renderer used for the images here |
| `BackendGuidelines/src/fr/product/` | The engine as the app uses it: `serve.py` (the protocol), `service.py` (plans, lengths, skips), `adapter.py` (tasks and events in), `constraints.py` and `parse.py` (rules from text, with Claude), `events.py` (which events matter) |
| `BackendGuidelines/src/fr/` | The rest of the engine — the scheduling core, samplers, learning — and the research's other engines |
| `BackendGuidelines/tests/`, `experiments/` | The engine's tests; the experiments (E001–E025) behind `REPORT.md` |

## What has been checked

The engine's 211 tests pass. The app's tests pass except one check of the
due-date parser, `'mon 12' parses`, which depends on today's date and fails
on the general app too. The snapshots render: light and dark, day, week and
month, drawer open and closed, the notebook's three pages, the new-event
form, the Planner's three sections, the picked plan on the calendar and a
preview, at the smallest window size and on a large display.

The Planner has been in use on a real calendar since 18 October 2026, and
most of what it does now came from that use. Not covered by the tests or
the snapshots: the three global shortcuts, dragging a task onto the
calendar, resizing the drawer by its edge, the Dock icon through the week,
and the popover on a work block (snapshots can't draw popovers).
