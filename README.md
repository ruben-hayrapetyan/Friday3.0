<p align="center">
  <img src="UI/docs/icon.png" width="128" height="128" alt="Friday's icon: a white F inside a ring that is most of the way closed">
</p>

# Friday

[Chroma](https://github.com/ruben-hayrapetyan/chroma) and
[Todo List](https://github.com/ruben-hayrapetyan/ToDo) as one Mac app. The calendar has the window to itself,
and your tasks live in a drawer that slides out over its right side when you
want them. Everything each app did on its own still works here; what's new
is what happens between the two.

![Friday's week view: the sidebar, and the calendar with task deadlines written in each day's margin lane](UI/docs/week-light.png)

![The same week with the tasks drawer open over the calendar's right side](UI/docs/week-tasks-light.png)

*Rendered from the real views by `UI/tools/snapshot.sh` with invented sample data — not a real calendar or task list.*

## Getting it running

The app lives in [`UI/`](UI). Build it and install it into Applications:

```bash
cd UI
./build.sh --install
```

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

Built from the general releases of both — **Chroma 1.0.1** (`main`,
758bab8) and **Todo List 1.0.1** (`main`, c8f4caf) — not from anyone's
personal branch. Friday works on the same files as both apps (see
[Your data](#your-data)), so either can be used alongside it, one at a time.

## Build, test, look

```bash
cd UI
./build.sh             # build/Friday.app for this Mac
./build.sh --install   # replace /Applications/Friday.app and launch it
./build.sh --release   # Apple silicon + Intel, zipped with QUICKSTART.txt into build/
./test.sh              # task model and store tests — no window, no real data
./tools/snapshot.sh    # renders the window with sample data into build/snapshots
```

Needs macOS 14 and the Xcode Command Line Tools. No Xcode project, no
dependencies.

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
part of the same planner rather than a second app.

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
| `⇧⌘O`, `⌥⌘1`–`⌥⌘9`, `⇧⌘K` | Filtered events, connected calendars, assign categories |

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
| `UI/Sources/Calendar/` | Chroma: EventKit store, categories and colours, the grids, inspector, Ask Claude, Settings |
| `UI/Sources/Tasks/` | Todo List: the model, the store, selection, keyboard, the notebook page |
| `UI/Tests/main.swift` | Store, file-format and calendar-bridge tests, run by `test.sh` |
| `UI/tools/` | The icon renderer (`MakeIcon/`, also `--week` for the strip above), and the snapshot renderer used for the images here |

## What hasn't been checked yet

The build, the 29 tests, and the rendered snapshots (light and dark, day,
week and month, drawer open and closed, the notebook's three pages, the
new-event form, at the smallest window size and on a large display) all
pass. What a snapshot can't show hasn't been exercised
in a running copy yet: the three global shortcuts, dragging a task onto the
calendar, resizing the drawer by its edge, and the Dock icon updating
through the week.
