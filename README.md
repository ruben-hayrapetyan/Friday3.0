<p align="center">
  <img src="UI/docs/icon.png" width="128" height="128" alt="Friday's icon: a white F inside a ring that is most of the way closed">
</p>

# Friday

A calendar and to-do list that decides when things get done. You put in what you have to do, roughly how long it takes
and when it's due; Friday reads your calendars and plans the work into the time around your events. It replans when
something changes, learns how long things really take you and what you prefer, and tells you plainly when more is due
than fits.

Friday is **a website served by `fridayd` on your Mac, and a Mac app around the same website**. The Mac app adds what a
browser can't: global shortcuts, the live Dock icon (with the count of decisions waiting in the Inbox), the menus, the
timer in the menu bar and the Mac's calendars. Open the same address in a browser and you have Friday there too.

**This is the `personal` branch: the copy of Friday in daily use.** It is two earlier Fridays combined: `friday-m16`'s
engine, server, learning and pages, and `personal`'s calendar, to-do notebook and look. Each of the 71 decisions that
went into the combination is in [`COMBINED.md`](COMBINED.md), and what was built and how it was tested is in
[`PROGRESS.md`](PROGRESS.md). `main` is empty, kept for a fresh start.

## Getting it running

You need macOS 14 or later, the Xcode Command Line Tools, [uv](https://docs.astral.sh/uv/) (it brings Python) and
Node (for building the website once).

```bash
uv sync                                       # the server and its tests
npx pnpm@10 --dir web install && npx pnpm@10 --dir web build   # the website, into web/dist
uv tool install --editable .                  # fridayd and friday in ~/.local/bin
fridayd init                                  # your time zone (detected) and sleep times: 23:30 to 07:30
```

Then **either** build the Mac app:

```bash
Mac/build.sh             # Mac/build/Friday.app, beside the Swift app
Mac/build.sh --install   # replace /Applications/Friday.app with it, and open it (the switch)
```

It starts `fridayd` itself when nothing is answering, and stops it when you quit. The checkout lives under
~/Downloads, so the first time, macOS asks whether Friday may open files there: allow it, or `fridayd` can't start.

To see Friday as a brand-new user without touching yours:

```bash
Mac/build.sh --test --open   # Friday Test (Mac/build/Friday Test.app): the Mac app, start to finish
scripts/fresh_user.sh        # the website alone, in your browser (stop, list, --no-claude, --no-init, --built)
```

Each starts a new user in its own folder under ~/.local/share/friday-fresh, on its own port, with no keys, no Google
and no setup answers. Neither ever changes a real calendar: signed in to your Google or reading this Mac's calendars,
they only read. Friday Test has a TEST band on its icon, leaves the global shortcuts to your Friday, and its Test User
menu starts over as another new user (with or without the `claude` command).

Or run Friday in a browser:

```bash
fridayd serve            # http://127.0.0.1:8765
```

**Google Calendar and Gmail** are read by the server. In Settings → Integrations (or setup's last step), choose your
Desktop OAuth client's .json file from Google Cloud once, then press Connect: Google's page opens in your browser, and
your calendars list there once you allow Friday. Add another Google account the same way (your school's beside your
own): each account's calendars are listed under its address, and each is read and changed through its own account.
Gmail has its own switch beside it and reads every account that allows it. (`fridayd google-login` does the same from a
terminal, once per account, with the file at `google.client_file` in [`friday.example.toml`](friday.example.toml).)
**The Mac's calendars** come through the Mac app: allow it to read them, and choose the ones Friday reads under This
Mac's calendars. One that is also read from Google starts off, so nothing comes in twice.

**The AI.** Ask Claude, rules in your own words, judging which events you could skip and sorting new calendar events
go through the AI chosen in Settings → Integrations → AI, and through its command line tool whenever it is installed on
this Mac, signed in as you, so no API key is needed: Claude Code's `claude` (PDFs and photos included, which it may only
read, in a folder of their own), OpenAI's `codex` (signed in with ChatGPT), or Google's `agy` (or the older `gemini`).
An API key in `secrets.toml` beside `friday.toml` (`[anthropic]`, `[openai]`, `[gemini]`… `api_key`, or
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) is used where there's no command, and behind one when it
fails; `codex` and `agy` can't be handed photos or scanned PDFs, which need the key. Grok, Meta's Muse and other
services have no command: a key. Without any, Friday still plans, and events are judged by their titles alone.

### Try it on someone else's term

```bash
fridayd demo --case jordan --ready    # http://127.0.0.1:8799
```

A Cornell student three weeks into using Friday, with stand-in Google, Gmail and AI, in its own data folder. The
cases run from very light to overloaded (`fridayd demo --help`).

## The Mac app

| | |
| --- | --- |
| ⌃⌥Space | Friday, from any app, with the to-do drawer open; again to put it away |
| ⌥Space | A new event |
| ⌃Space | Ask Claude |
| ⌘N, ⇧⌘N | A new event, a new to-do |
| ⌘1, ⌘2, ⌘3 | Day, week, month |
| ⌘T | Today (`[` and `]` step back and forward, as in the browser) |
| ⌥⌘1 … ⌥⌘6 | Plan, To-do, Projects, Inbox (how your day went is there too), Insights, Rules |
| ⌘J | Ask Claude |

The **Plan** menu has Other Ways, What Gives, Shove, Pace and the morning brief. The **menu bar** shows what you're
timing and for how long, with Pause and Done. Friday sends no notifications: everything that needs you waits in the
Inbox, a message each (what only you can decide first, then how much of your planned work you did, then what came in
from mail and calendars), counted on the sidebar, in the title row and in the window's title; the Dock icon counts
what only you can decide.
Friday → Settings… has the shortcuts, the menu-bar timer, the Mac's calendars,
opening at login and where `fridayd` is. The rest of the settings are on the website's Settings page.

The menus and shortcuts don't do anything themselves: each sends a `friday:host` event that the website handles
([`web/src/shell/host.ts`](web/src/shell/host.ts)), so the Mac app and the browser share one implementation.

## What's where

| | |
| --- | --- |
| [`src/friday`](src/friday) | `fridayd` and `friday`: the engine (the allocator, the scheduler and the rules), the planner, learning, the commands (each one an HTTP endpoint, a CLI verb and an MCP tool), Google and the Mac's calendars, the server |
| [`web`](web) | The website: React, Vite and TypeScript |
| [`Mac`](Mac) | The Mac app around the website, in Swift, with no Xcode project. It reuses the Swift app's hotkeys and Dock icon from `UI/` |
| [`tests`](tests) | The server's tests, from single rules to whole terms, plus the HTTP flows |
| [`UI`](UI) | The Swift app Friday was before the combination ([its README](UI/README.md)). Kept and buildable until the switch |
| [`BackendGuidelines`](BackendGuidelines) | The Swift app's planning engine and the research behind it |
| [`DESIGN.md`](DESIGN.md) | `friday-m16`'s design: the engine, the server and every page |

## Tests

```bash
scripts/check.sh   # ruff, pytest, the website's typecheck and tests, and the Mac app's (about 25 minutes)
Mac/test.sh        # the Mac app's alone: what each menu sends, the timer's label, the calendar payload
```

Tests never call the real AI: `tests/conftest.py` switches off the `claude`, `codex`, `agy` and `gemini` commands and
the API keys.

## Where it comes from

| | What Friday takes from it |
| --- | --- |
| `friday-m16` | The engine, the server, learning (how long things take you, what you prefer), the Inbox, the pages in the sidebar, the website |
| `personal` (the Swift app, [`UI/`](UI)) | The calendar and the to-do drawer, deadline lanes, lengths in plain language, exam focus and the other rules from using it on a real term, the paper-and-ink look, the hotkeys and the Dock icon |
| [Chroma](https://github.com/ruben-hayrapetyan/chroma) and [Todo List](https://github.com/ruben-hayrapetyan/ToDo) | Through `personal`: event colours and categories, and the notebook of short- and long-term tasks |

## Licence and terms

Friday's code is under the [PolyForm Noncommercial License 1.0.0](LICENSE): you may read it, change it and share it
for any noncommercial purpose, but you may not sell Friday, or anything built from its code, or otherwise make money
from it, without a licence from Ruben Hayrapetyan. The code comes as is, with no warranty and no responsibility taken
for it or for anything built from it. Using the app is covered by its [terms](TERMS.md), which everyone accepts when
Friday first opens.
