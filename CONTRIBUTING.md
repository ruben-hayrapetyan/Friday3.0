# Contributing to Friday

Thanks for wanting to help. Friday is a calendar and to-do app that decides when things get done, running entirely on
your own computer.

- **Start from an issue.** Say what you'd change and why before writing much code, so we agree on the direction.
- **Work on a fork, open a pull request.** Nobody pushes to `main`: every change arrives as a pull request, passes the
  checks (`.github/workflows/checks.yml`) and is reviewed by the owner before it's merged.
- **Run the checks yourself first:** `scripts/check.sh` (setting up Python, `uv` and `pnpm` is in the README's
  "Building it yourself").
- **Tests come with every change**: tests written from what it should do, tests of how it works inside, and, where it
  crosses the server, a test through the whole system.
- **After a change to how something looks**, look at it at a laptop's width and a phone's, and run the layout check:
  `cd web && npx vite build && node scripts/overflow-check.mjs` (add `--shots <folder>` for a picture of each page it
  finds something on). It serves the lived-in sample, opens every page, panel and dialog in headless Chrome at 1440 and
  390 wide, and lists text or boxes that run past the box they sit in (`scripts/overflow-detect.js`), exiting 1 if
  any do. It needs Google Chrome (or `CHROME=/path/to/chrome`) and takes a few minutes, so it isn't part of
  `scripts/check.sh`.
- **Style** is in `DESIGN.md` §4.4: names that explain the code, short functions, comments that say why.

Anyone can contribute, with nothing to sign. Friday's code is under the PolyForm Noncommercial License 1.0.0
(`LICENSE`), so nobody may build on it and make money from it. **By opening a pull request you agree that your
contribution is licensed under those terms, and that Ruben Hayrapetyan may also use, license and sell it commercially
as part of Friday.**
