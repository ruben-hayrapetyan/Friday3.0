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

import { spawn } from "node:child_process"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { createServer } from "node:net"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, "../..")
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
const SETTINGS = ["appearance", "calendars", "tags", "schedule", "repeating", "integrations", "phone", "tokens", "shortcuts", "updates", "advanced"]
const STATES = [
  { name: "plan day", path: "/", keys: ["d"] },
  { name: "plan 3 days", path: "/", keys: ["3"] },
  { name: "plan week", path: "/", keys: ["w"] },
  { name: "plan month", path: "/", keys: ["m"] },
  { name: "plan block card", path: "/", keys: ["w"], each: "[data-block-key]", most: 3 },
  // 16 Nov (IMG 4240): an event's Category list ran across the whole window, its left edge cut off
  { name: "event category menu", path: "/", keys: ["w"], each: '[data-block-key^="F"]', most: 2, after: "Category of" },
  { name: "plan to-do drawer", path: "/", click: ["To-do list"] },
  { name: "plan menu", path: "/", click: ["Plan…"] },
  { name: "what if", path: "/", click: ["Plan…", "What if"] },
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

function freePort() {
  return new Promise((done, fail) => {
    const probe = createServer()
    probe.once("error", fail)
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address()
      probe.close(() => done(port))
    })
  })
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/** Alex's sample, served from a folder of its own, terms accepted and Setup answered, as the screen tests do. */
async function serveSample() {
  const folder = mkdtempSync(path.join(tmpdir(), "friday-overflow-"))
  const port = await freePort()
  const keys = { MICROSOFT_CLIENT_ID: "test-microsoft-id", SLACK_CLIENT_ID: "test-slack-id", SLACK_CLIENT_SECRET: "test-slack-secret", TICKTICK_CLIENT_ID: "test-ticktick-id", TICKTICK_CLIENT_SECRET: "test-ticktick-secret", TRELLO_CLIENT_ID: "test-trello-id" }
  const env = { ...process.env, FRIDAY_CHAINS: "3", FRIDAY_FIXED_EFFORT: "1", FRIDAY_WEB_DIST: process.env.FRIDAY_WEB_DIST ?? path.join(REPO, "web/dist"), ...Object.fromEntries(Object.entries(keys).map(([k, v]) => [`FRIDAY_${k}`, v])) }
  delete env.VIRTUAL_ENV
  // in a process group of its own, ended whole: uv runs Python, which runs solver workers, and a signal to uv alone
  // can leave them serving
  const child = spawn("uv", ["run", "--quiet", "fridayd", "--data-dir", folder, "demo", "--case", "alex", "--ready", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "ignore", "pipe"], detached: true })
  const end = () => ended(child)
  process.on("exit", end) // however this ends, the sample's server ends with it
  let said = ""
  child.stderr.on("data", (d) => (said = (said + d).slice(-4000)))
  const base = `http://127.0.0.1:${port}`
  for (let until = Date.now() + 300_000; ; await wait(500)) {
    if (child.exitCode !== null) throw new Error(`fridayd demo stopped:\n${said}`)
    if (Date.now() > until) throw new Error(`fridayd demo didn't answer:\n${said}`)
    if (await fetch(`${base}/api/q/status`).then((r) => r.ok, () => false)) break
  }
  const post = (name, body) => fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  const terms = await (await fetch(`${base}/api/q/terms`)).json()
  if (terms.needed) await post("terms_accept", { version: terms.version })
  const setup = await (await fetch(`${base}/api/q/setup`)).json()
  if (!setup.done) await post("setup_save", { ...setup.answers, brief: false })
  await post("tour_offered", {})
  return { base, stop: () => (end(), rmSync(folder, { recursive: true, force: true, maxRetries: 5 })) }
}

/** Ends a process started `detached` and everything it started. */
function ended(child) {
  try {
    process.kill(-child.pid, "SIGKILL")
  } catch {
    // already gone
  }
}

function chromePath() {
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  return process.env.CHROME || (existsSync(mac) ? mac : "google-chrome")
}

/** Headless Chrome and a page in it, spoken to over the DevTools protocol. */
async function openChrome() {
  const profile = mkdtempSync(path.join(tmpdir(), "friday-overflow-chrome-"))
  const chrome = spawn(chromePath(), ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--force-color-profile=srgb", "--disable-features=BackForwardCache", "about:blank"], { stdio: ["ignore", "ignore", "pipe"], detached: true })
  process.on("exit", () => ended(chrome))
  const url = await new Promise((done, fail) => {
    let said = ""
    chrome.stderr.on("data", (d) => {
      said += d
      const found = said.match(/DevTools listening on (ws:\S+)/)
      if (found) done(found[1])
    })
    chrome.once("exit", () => fail(new Error(`Chrome stopped:\n${said}`)))
  })
  const socket = new WebSocket(url)
  await new Promise((done, fail) => ((socket.onopen = done), (socket.onerror = fail)))
  let next = 0
  const pending = new Map()
  const listeners = new Set()
  socket.onmessage = (m) => {
    const msg = JSON.parse(m.data)
    if (msg.id && pending.has(msg.id)) {
      const [done, fail] = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? fail(new Error(msg.error.message)) : done(msg.result)
    } else for (const l of listeners) l(msg)
  }
  const send = (method, params = {}, sessionId) =>
    new Promise((done, fail) => {
      const id = ++next
      pending.set(id, [done, fail])
      socket.send(JSON.stringify({ id, method, params, sessionId }))
    })
  const { targetId } = await send("Target.createTarget", { url: "about:blank" })
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true })
  const page = (method, params) => send(method, params, sessionId)
  await page("Page.enable")
  await page("Runtime.enable")
  // The app's service worker would keep fetching what a page left behind, and Chrome lets six requests at a time go
  // to one server: a few pages on, a page load waited a minute behind them. The page talks to the server directly.
  await page("Network.enable")
  await page("Network.setBypassServiceWorker", { bypass: true })
  // A state's made-up answers (`answer`): the page's questions to /api/q/<name> answered here, the rest let through.
  let answers = {}
  // a page asking before it's left (What if's changes not kept) would hold everything: it's answered yes
  listeners.add((msg) => msg.method === "Page.javascriptDialogOpening" && msg.sessionId === sessionId && page("Page.handleJavaScriptDialog", { accept: true }).catch(() => {}))
  listeners.add((msg) => {
    if (msg.method !== "Fetch.requestPaused" || msg.sessionId !== sessionId) return
    const { requestId, request } = msg.params
    const name = new URL(request.url).pathname.replace(/^\/api\/q\//, "")
    if (name in answers) {
      const body = Buffer.from(JSON.stringify(answers[name])).toString("base64")
      page("Fetch.fulfillRequest", { requestId, responseCode: 200, responseHeaders: [{ name: "content-type", value: "application/json" }], body }).catch(() => {})
    } else page("Fetch.continueRequest", { requestId }).catch(() => {})
  })
  const answer = async (given) => {
    answers = given ?? {}
    if (given) await page("Fetch.enable", { patterns: [{ urlPattern: "*/api/q/*" }] })
    else await page("Fetch.disable")
  }
  const close = () => {
    socket.close()
    ended(chrome)
    rmSync(profile, { recursive: true, force: true, maxRetries: 5 })
  }
  return { page, close, answer }
}

async function evaluate(page, expression) {
  let timer
  const late = new Promise((_, fail) => (timer = setTimeout(() => fail(new Error("the page didn't answer in 30s")), 30_000)))
  const { result, exceptionDetails } = await Promise.race([page("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }), late]).finally(() => clearTimeout(timer))
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text)
  return result.value
}

// In the page: wait until nothing has changed for a moment (data in, animations done), up to two and a half seconds
// (a clock or a spinner never stops changing).
const SETTLE = `new Promise((done) => {
  let last = performance.now()
  const seen = new MutationObserver(() => (last = performance.now()))
  seen.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true })
  const started = performance.now()
  const check = () => {
    const now = performance.now()
    if ((now - last > 250 && document.fonts.status === "loaded") || now - started > 2500) return seen.disconnect(), done(true)
    setTimeout(check, 60)
  }
  setTimeout(check, 120)
})`

// In the page: press the button (or link, switch, menu item) named `name`, the first one showing; "Plan…" is the one
// that opens a menu (aria-expanded), not the page of that name; "a|b" is whichever of them shows.
const CLICK = (said) => `(() => {
  const menu = ${JSON.stringify(said)}.endsWith("…")
  const name = ${JSON.stringify(said)}.replace(/…$/, "")
  const named = (el) => (el.getAttribute("aria-label") || el.textContent || "").replace(/\\s+/g, " ").trim()
  const all = [...document.querySelectorAll("button, a, [role=button], [role=menuitem], [role=tab], [role=option]")]
  const showing = all.filter((el) => el.getBoundingClientRect().width > 0 && (!menu || el.hasAttribute("aria-expanded")))
  const names = name.split("|")
  const el = showing.find((el) => names.includes(named(el))) || showing.find((el) => names.some((n) => named(el).startsWith(n)))
  if (!el) return false
  el.click()
  return true
})()`

async function press(page, combo) {
  const parts = combo.split("+")
  const key = parts.pop()
  const modifiers = (parts.includes("Alt") ? 1 : 0) | (parts.includes("Control") ? 2 : 0) | (parts.includes("Meta") ? 4 : 0) | (parts.includes("Shift") ? 8 : 0)
  const special = { Escape: ["Escape", 27], Enter: ["Enter", 13], ArrowRight: ["ArrowRight", 39] }[key]
  const code = special ? special[1] : key.toUpperCase().charCodeAt(0)
  const text = special || modifiers & 6 ? undefined : key
  await page("Input.dispatchKeyEvent", { type: "keyDown", key, code: special ? key : `Key${key.toUpperCase()}`, windowsVirtualKeyCode: code, modifiers, text })
  await page("Input.dispatchKeyEvent", { type: "keyUp", key, code: special ? key : `Key${key.toUpperCase()}`, windowsVirtualKeyCode: code, modifiers })
}

let loads = 0

/** A fresh load of `route`, with nothing kept from the last state (a hash alone wouldn't reload the page). */
async function go(page, base, route) {
  await load(page, "about:blank") // the last page's questions to the server stop here, not left running
  await page("Storage.clearDataForOrigin", { origin: base, storageTypes: "local_storage,session_storage" })
  await load(page, `${base}/?look=${++loads}#${route}`)
  await evaluate(page, SETTLE)
}

/** Navigates and waits for the new page (the old one is marked, so its own "complete" isn't taken for the new one's;
 * the address can't tell them apart, as the app may rewrite it). */
async function load(page, url) {
  await evaluate(page, "window.__leaving = true").catch(() => {})
  await page("Page.navigate", { url })
  for (let until = Date.now() + 20_000; Date.now() < until; await wait(100)) {
    const ready = await evaluate(page, `!window.__leaving && document.readyState === "complete"`).catch(() => false)
    if (ready) return
  }
  throw new Error(`${url} didn't load`)
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

/** `expression`'s answer once it has one (a button or a list can wait on the server's answer), within ten seconds. */
async function until(page, expression) {
  for (let tries = 0; ; tries++) {
    const answer = await evaluate(page, expression)
    if (answer || tries >= 40) return answer
    await wait(250)
  }
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
  const sample = given ? { base: given.replace(/\/$/, ""), stop: () => {} } : await serveSample()
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
