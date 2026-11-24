#!/usr/bin/env node
// Looks for text or boxes painting past the box they sit in, on Friday's pages at a laptop's width and a phone's
// (14 Nov: the Google card's last lines ran under the next card, and the calendars table's last column past its panel).
// It serves Alex's lived-in sample (`fridayd demo --case alex --ready`, about a minute and a half to build) or uses one
// already running (--url), drives headless Chrome over its DevTools protocol (Node's own WebSocket: nothing to
// install), visits each page and its panels and dialogs, runs overflow-detect.js on each (text or a box past the box
// it's in, a line cut part way, a scrolling column free to squeeze its rows, one control over another, a control the
// Now dock covers at its tallest), and exits 1 if
// anything spills or a page couldn't be reached. About four minutes in all.
//
//   node web/scripts/overflow-check.mjs [--url http://127.0.0.1:8791] [--shots folder] [--only text] [--widths 1440,390]
//
// Chrome: CHROME, else Google Chrome's usual place on a Mac, else `google-chrome` on the PATH. The sample serves
// web/dist (build it first), or FRIDAY_WEB_DIST; OVERFLOW_PROGRESS=1 says each page and its time as it goes.

import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { CLICK, SETTLE, evaluate, go, load, openChrome, press, serveSample, until, wait } from "./browser.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DETECT = readFileSync(path.join(HERE, "overflow-detect.js"), "utf8")
const SIZES = { 1440: [1440, 900], 390: [390, 844] }

const args = process.argv.slice(2)
const option = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
const only = option("--only")
const shots = option("--shots")
const widths = (option("--widths") ?? "1440,390").split(",").map(Number)

// What to look at: a page (or, given the server's address, a function finding one), and what to press there first.
// `open` presses every folded row's button (in the page's column, or in the one a selector names); `each` opens every
// match of a selector in turn (pressing Escape between, or its own button again with `keep`), pressing `after` in each; `keys` are pressed as a person would; `click` is a button's name (its words or aria-label), and one
// ending in "?" is pressed only if it's there.
/** Friday working out a new plan, held: the server's status with a plan one generation behind. */
const replanningNow = async (base) => {
  const status = await (await fetch(`${base}/api/q/status`)).json()
  return { status: { ...status, plan_generation: status.generation - 1 } }
}
/** Work that will be late and work slipping: the lateness note, with its count, in the Plan header (20 Nov: on phones
 * the To-do button ran past the edge beside it, which a week with no late work never showed). */
const lateNow = async (base) => {
  const status = await (await fetch(`${base}/api/q/status`)).json()
  const due = new Date(Date.now() + 86400000).toISOString().slice(0, 16)
  return {
    status: {
      ...status,
      late_items: [{ item_id: 1, title: "Problem set 7", due, hours: 2 }],
      slipping: [{ item_id: 2, title: "Reading response", due, hours: 1, planned: false }],
    },
  }
}
const SETTINGS = ["appearance", "calendars", "tags", "schedule", "repeating", "breaks", "integrations", "phone", "tokens", "shortcuts", "updates", "advanced"]
const STATES = [
  { name: "plan day", path: "/", keys: ["d"] },
  { name: "plan 3 days", path: "/", keys: ["3"] },
  { name: "plan week", path: "/", keys: ["w"] },
  { name: "plan month", path: "/", keys: ["m"] },
  { name: "plan block card", path: "/", keys: ["w"], each: "[data-block-key]", most: 3 },
  // 16 Nov (IMG 4240): an event's Category list ran across the whole window, its left edge cut off
  { name: "event category menu", path: (base) => withEvent(base), keys: ["w"], each: '[data-block-key^="F"]', most: 2, after: "Category of" },
  { name: "plan to-do drawer", path: "/", click: ["To-do list"] },
  { name: "plan menu", path: "/", click: ["Plan…"] },
  // 19 Nov: the Breaks button where the Inbox tray was, and its panel; the header at every width (`--widths`)
  { name: "plan breaks panel", path: "/", click: ["Breaks|Plan…"] }, // the narrowest: Breaks is the Plan menu's first row
  { name: "what if", path: "/", click: ["Plan…", "What if"] },
  // 20 Nov, the user's screenshot: with What if on and a lateness note, "Replanning…" was drawn over Day and 3 days
  { name: "what if, replanning", path: "/", answer: replanningNow, click: ["Plan…", "What if"] },
  { name: "what if tried, replanning", path: "/", answer: replanningNow, click: ["Plan…", "What if", "Show the changes?", "dinner with Sam", "Try"] },
  { name: "plan week, replanning", path: "/", answer: replanningNow, keys: ["w"] },
  { name: "plan week, late work", path: "/", answer: lateNow, keys: ["w"] },
  { name: "what if, late work", path: "/", answer: lateNow, click: ["Plan…", "What if"] },
  { name: "search", path: "/", keys: ["Meta+k"] },
  { name: "what's on this page", path: "/", click: ["Menu?", "What's on this page"] },
  { name: "tour", path: "/", click: ["Menu?", "What's on this page", "Take the tour"], then: ["Next", "Next", "Next"] },
  { name: "to-do", path: "/todo" },
  { name: "to-do details", path: "/todo", each: ".fr-todo-line", most: 2 },
  { name: "projects & exams", path: "/projects" },
  { name: "new exam", path: "/projects", click: ["New exam"] },
  { name: "new project", path: "/projects", click: ["New project"] },
  { name: "deadline rows", path: "/projects", each: 'section[aria-label="With a deadline"] [role="button"]', most: 3 },
  { name: "new ongoing project", path: "/projects", click: ["New ongoing project|New ongoing"] },
  // 17 Nov: a project, an exam and an ongoing project open in a popup in the middle of the screen; each looked at
  // as it opens, with its rows open, and with its dropdowns open over it
  { name: "project popup", path: (base) => opened(base, "project") },
  { name: "project popup rows", path: (base) => opened(base, "project"), open: "[role=dialog]" },
  { name: "project popup step length", path: (base) => opened(base, "project"), click: ["Length of Research"] },
  { name: "project popup project menu", path: (base) => opened(base, "project"), click: ["Project"] },
  { name: "project popup tag menu", path: (base) => opened(base, "project"), click: ["Tag for Rocketry design review"] },
  { name: "project popup any time", path: (base) => opened(base, "project"), click: ["Rehearse waits|Rehearse doesn't wait"] }, // the 1440 run made it any time: either way
  { name: "exam popup", path: (base) => opened(base, "exam") },
  { name: "exam popup rows", path: (base) => opened(base, "exam"), open: "[role=dialog]", click: ["Add prep"] },
  { name: "exam popup prep due", path: (base) => opened(base, "exam"), each: '[role=dialog] [role=listitem] [aria-label^="When "]', most: 1 },
  { name: "exam popup prep length", path: (base) => opened(base, "exam"), each: '[role=dialog] [role=listitem] [aria-label^="Length of "]', most: 1 },
  { name: "ongoing popup", path: (base) => opened(base, "ongoing") },
  { name: "ongoing popup rows", path: (base) => opened(base, "ongoing"), each: '[role=dialog] [aria-expanded="false"]:not([aria-haspopup])', most: 6, keep: true },
  { name: "inbox", path: "/inbox" },
  { name: "inbox messages", path: "/inbox", each: '[aria-label="Waiting for you"] [role="listitem"], [aria-label="Waiting for you"] > button', most: 12 },
  { name: "insights", path: "/insights" },
  { name: "sleep & meals", path: "/body" },
  { name: "rules", path: "/rules" },
  { name: "rules why", path: "/rules", click: ["Why?"] },
  { name: "rule box", path: "/rules", click: ["New rule|Add a rule|Add rule"] },
  { name: "brief", path: "/", click: ["Plan…", "Morning brief"] },
  // Breaks (breaks/): a break this week with a long name, its band, its days' lines, a day's list, its popup and the
  // chooser of what pauses; Take a break from Pace; and a suggested one in the Inbox.
  { name: "plan break week", path: (base) => onBreak(base), keys: ["3"] },
  { name: "break day list", path: (base) => onBreak(base), keys: ["3"], each: ".fr-break-line", most: 2 },
  { name: "break popup", path: (base) => onBreak(base), keys: ["3"], each: ".fr-break-band", most: 1 },
  { name: "break popup pauses", path: (base) => onBreak(base), keys: ["3"], each: ".fr-break-band", most: 1, after: "Every repeating event" },
  { name: "take a break", path: "/", click: ["Plan…", "Pace", "Take a break"] },
  { name: "inbox suggested break", path: async (base) => (await onBreak(base), "/inbox") },
  { name: "what changed", path: "/", click: ["Plan…", "What changed"] },
  { name: "other ways", path: "/", click: ["Plan…", "Other ways"] },
  { name: "shove", path: "/", click: ["Plan…", "Shove"] },
  { name: "pace", path: "/", click: ["Plan…", "Pace"] },
  { name: "ask", path: "/", click: ["Plan…", "Ask "] },
  { name: "triage", path: "/?triage" },
  { name: "update popup", path: "/settings/updates", answer: () => ({ update_status: UPDATE }), click: ["See what's new"] },
  // 18 Nov: test users (H224): the code box, a long name the site knows the code by, a code it doesn't know, and the
  // popup offering a version for test users
  { name: "updates test user box", path: "/settings/updates", answer: () => ({ update_status: UPDATE }) },
  { name: "updates test user", path: "/settings/updates", answer: () => ({ update_status: TESTER({ name: "Alexandria Montgomery-Okonkwo", known: true }) }) },
  { name: "updates test code unknown", path: "/settings/updates", answer: () => ({ update_status: TESTER({ name: null, known: false }) }) },
  { name: "update popup test users", path: "/settings/updates", answer: () => ({ update_status: TESTER({ name: "Ana", known: true }) }), click: ["See what's new"] },
  { name: "terms changed", path: "/", answer: async (base) => ({ terms: { ...(await (await fetch(`${base}/api/q/terms`)).json()), accepted: "2026-01-01", needed: true, changes: ["Section 3 says plainly what Friday's code comes with", "The section on which law applies is gone"] } }) },
  { name: "setup walk", path: "/settings/integrations", click: ["Change a Setup answer", "All of Setup"], then: Array(16).fill("Start walking|Next stop|Continue") },
  ...SETTINGS.map((s) => ({ name: `settings ${s}`, path: `/settings/${s}`, open: true })),
  { name: "integrations boxes", path: "/settings/integrations", each: "[data-integration]", open: true },
]

// A newer Friday to update to, as Settings → Updates would show one (a Friday run from its code never looks).
const NOTES = (v) => ({ version: v, released: "2026-11-10", summary: `Friday ${v} plans around your shifts and reads your school's calendar feeds.`, new: ["Shifts from When I Work, Deputy and Homebase, planned around like classes"], changed: ["Settings open where you left them"], fixed: ["Sync now after the Mac wakes from sleep"] })
const UPDATE = { checks: true, have: "0.3.3", last_checked: new Date().toISOString(), state: "idle", progress: 0, message: null, versions: [NOTES("0.4.0"), NOTES("0.3.4")], popup: false, whats_new: [], restart: "now", staged: null }
const TESTER = (said) => ({ ...UPDATE, versions: [{ ...NOTES("0.4.1"), test: true }, NOTES("0.4.0")], test_user: { code: "K7QF-29XM", ...said } })

// What the popups show: Alex's sample has exams but no projects or ongoing projects, so one of each is made once,
// with long names and a step of every kind, and its address given.
const made = {}
async function opened(base, kind) {
  const q = async (name) => (await fetch(`${base}/api/q/${name}`)).json()
  const c = async (name, body) => (await fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json()
  if (kind === "exam") return `/projects?exam=${(await q("exams"))[0].item.id}`
  if (!made[kind]) {
    if (kind === "project") {
      const due = new Date(Date.now() + 20 * 86_400_000).toISOString().slice(0, 10)
      const id = (await c("add", { title: "Rocketry design review", preset: "Project", due: `${due}T17:00`, duration_min: 600, area: "Rocketry" })).result.item.id
      for (const [title, minutes] of [["Research", 120], ["Draft the slides on the recovery system and the parachute deployment altitude", 240], ["Rehearse", 60], ["Print handouts", 30]]) await c("add", { title, parent_id: id, duration_min: minutes })
      await c("add", { title: "Lab notebook cleanup", preset: "Project", duration_min: 240 }) // another, for its Project menu
      made[kind] = `/projects?id=${id}`
    } else made[kind] = `/projects?ongoing=${(await c("ongoing_add", { title: "Guitar practice", hours_per_week: 4, area: null })).result.id}`
    await wait(1500) // planned
  }
  return made[kind]
}

// A break from today for five days with a long name, and an all-day "Spring break" a few weeks on that the Inbox
// suggests as one; made once a width, and the break deleted when the width is done (offBreak): 21 Nov, made at
// 1440px it stayed for 390px, whose week was then all Off break with no block to open.
let breakMade = null
let spring = false
async function onBreak(base) {
  if (!breakMade) {
    const c = async (name, body) => (await fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json()
    // local dates: in the evening, UTC's is already tomorrow, and the break fell past the 3-day view
    const day = (n) => {
      const d = new Date(Date.now() + n * 86_400_000)
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    }
    const made = await c("vacation_add", { name: "Thanksgiving break at my grandparents' house in Vermont", start: day(0), end: day(4) })
    if (!spring) await c("add", { title: "Spring break", when: "fixed", start: `${day(20)}T00:00`, end: `${day(27)}T00:00` })
    spring = true
    breakMade = made.result.vacation.id
    await wait(1500) // planned
  }
  return "/"
}

// An event an hour from now, made once: on a weekend Alex's sample has none where a phone's week starts (21 Nov,
// Saturday: the event category menu had no event to open at 390px).
let eventMade = false
async function withEvent(base) {
  if (!eventMade) {
    const at = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:00`
    const start = new Date(Date.now() + 3_600_000)
    const body = { title: "Study group", when: "fixed", start: at(start), end: at(new Date(start.getTime() + 3_600_000)) }
    await fetch(`${base}/api/c/add`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
    eventMade = true
    await wait(1500) // planned
  }
  return "/"
}

async function offBreak(base) {
  if (!breakMade) return
  await fetch(`${base}/api/c/vacation_delete`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: breakMade }) })
  breakMade = null
  await wait(1500) // planned again
}


// In the page: the Now dock as tall as it gets with a sleep row, a meal row and another timer's row up (about 110px
// more than the sample shows at most hours), so the room a page leaves for it is checked at its tallest.
const TALL_DOCK = `new Promise((done) => {
  const dock = document.querySelector("[data-tour=now]")
  if (dock && !dock.querySelector("[data-tall-dock]")) {
    const rows = document.createElement("div")
    rows.setAttribute("data-tall-dock", "")
    rows.style.height = "110px"
    dock.prepend(rows)
  }
  requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 50)))
})`

async function look(page, label, findings, width) {
  await evaluate(page, TALL_DOCK)
  const found = await evaluate(page, DETECT)
  for (const f of found) findings.push({ state: label, width, ...f })
  if (process.env.OVERFLOW_PROGRESS) console.error(`${width}px ${label}: ${found.length}`)
  if (found.length && shots) {
    mkdirSync(shots, { recursive: true })
    const { data } = await page("Page.captureScreenshot", { format: "png" })
    writeFileSync(path.join(shots, `${width}-${label.replace(/[^a-z0-9]+/gi, "-")}.png`), Buffer.from(data, "base64"))
  }
  return found.length
}


async function visit(page, base, state, width, findings) {
  const steps = async () => {
    for (const k of state.keys ?? []) await press(page, k), await evaluate(page, SETTLE)
    for (const name of state.click ?? []) {
      if (name.endsWith("?") && !name.endsWith("Why?")) {
        await evaluate(page, CLICK(name.slice(0, -1))) // only where there is one (the menu of a narrow window)
        await evaluate(page, SETTLE)
        continue
      }
      if (!(await until(page, CLICK(name)))) throw new Error(`no "${name}" to press`)
      await evaluate(page, SETTLE)
    }
  }
  await go(page, base, typeof state.path === "function" ? await state.path(base) : state.path)
  const scope = typeof state.open === "string" ? state.open : ".fr-gutter"
  if (state.open) await evaluate(page, `document.querySelectorAll(${JSON.stringify(`${scope} [aria-expanded="false"]:not([aria-haspopup])`)}).forEach((b) => b.click())`).then(() => evaluate(page, SETTLE))
  await steps()
  if (!state.each) {
    await look(page, state.name, findings, width)
    for (const [step, name] of (state.then ?? []).entries()) {
      if (!(await evaluate(page, CLICK(name)))) break
      await evaluate(page, SETTLE)
      await look(page, `${state.name}, step ${step + 2}`, findings, width)
    }
    return
  }
  const count = Math.min(await until(page, `document.querySelectorAll(${JSON.stringify(state.each)}).length`), state.most ?? 99)
  if (!count) throw new Error(`nothing matches ${state.each}`)
  for (let i = 0; i < count; i++) {
    const label = await evaluate(page, `(() => { const el = document.querySelectorAll(${JSON.stringify(state.each)})[${i}]; if (!el) return null; el.scrollIntoView({ block: "center" }); el.click(); return (el.getAttribute("data-integration") || el.getAttribute("aria-label") || el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 40) })()`)
    if (label === null) break
    await evaluate(page, SETTLE)
    if (state.open) await evaluate(page, `document.querySelectorAll('[role=dialog] [aria-expanded="false"]:not([aria-haspopup])').forEach((b) => b.click())`).then(() => evaluate(page, SETTLE))
    if (state.after) {
      if (!(await until(page, CLICK(state.after)))) throw new Error(`no "${state.after}" to press in ${label}`)
      await evaluate(page, SETTLE)
    }
    await look(page, `${state.name}: ${label}`, findings, width)
    if (state.keep) {
      // a row of a popup: closed again by its own button, the popup staying open
      await evaluate(page, `(() => { const el = document.querySelectorAll('[aria-expanded="true"]:not([aria-haspopup])'); el.forEach((b) => b.click()) })()`)
      await evaluate(page, SETTLE)
      continue
    }
    if (state.after) await press(page, "Escape") // the open list first, then the card
    await press(page, "Escape")
    await evaluate(page, SETTLE)
  }
}

async function main() {
  const started = Date.now()
  const given = option("--url")
  const sample = given ? { base: given.replace(/\/$/, ""), stop: () => {} } : await serveSample({ prefix: "friday-overflow-" })
  const { page, close, answer } = await openChrome()
  const findings = []
  const problems = []
  try {
    for (const width of widths) {
      const [w, h] = SIZES[width] ?? [width, 900]
      await page("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false })
      for (const state of STATES) {
        if (only && !state.name.includes(only)) continue
        const began = Date.now()
        try {
          await answer(state.answer && (await state.answer(sample.base)))
          await visit(page, sample.base, state, width, findings)
        } catch (error) {
          problems.push(`${width}px ${state.name}: ${error.message}`)
        }
        if (process.env.OVERFLOW_PROGRESS) console.error(`  ${width}px ${state.name} took ${((Date.now() - began) / 1000).toFixed(1)}s`)
      }
      await offBreak(sample.base)
    }
  } finally {
    close()
    sample.stop()
  }
  for (const f of findings) console.log(`${f.width}px  ${f.state}\n  ${f.kind} ${f.by}\n  at ${f.where}\n  "${f.text}"`)
  for (const p of problems) console.log(`couldn't look: ${p}`)
  const seconds = Math.round((Date.now() - started) / 1000)
  console.log(`${findings.length} overflow${findings.length === 1 ? "" : "s"} found, ${problems.length} page${problems.length === 1 ? "" : "s"} not reached, in ${seconds}s`)
  process.exit(findings.length || problems.length ? 1 : 0)
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(130))

main().catch((error) => {
  console.error(error)
  process.exit(2)
})
