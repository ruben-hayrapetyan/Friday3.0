#!/usr/bin/env node
// The web layer (TESTING.md): each feature with a page has web/e2e/<feature>.e2e.mjs, which drives it in a real Chrome,
// headless, as a person would (opens the page, clicks, types) and checks what the page then shows against what the
// server has. This serves one sample (Alex's lived-in one unless --case), opens Chrome once and runs each file's
// tests in turn, each on a fresh page load.
//
//   node web/e2e/run.mjs [--only items,rules] [--case alex] [--url http://127.0.0.1:8791 [--folder DIR]] [--shots DIR]
//
// A test file: `export default [{ name, run }]`, run({ page, base, folder, open, click, type, text, has, gone, until,
// q, c, request, planned, day, expect, evaluate, answer, stub }) → throws on what's wrong. click(name, { within })
// presses only inside that part of the page; `gone(words)` waits for words to leave the page; `request(method, path,
// body, headers)` is a raw call to the server, for refusals ({ status, body }). `base` is the sample's address; `folder`
// its own data and config folder (its friday.toml and secrets.toml), or undefined with --url (give --folder).
// `answer({ name: json, "c/name": json })` (also called `stub`) answers the page's queries and commands so named
// itself (a state the sample hasn't got, an AI's answer), until the test ends.
// Exit 0: all passed; 1: some failed (listed); 2: it couldn't run. Build web/dist first.

import { mkdirSync, readdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { CLICK, LAYOUT, SEEN, SETTLE, evaluate, go, openChrome, press, serveSample, wait } from "../scripts/browser.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const option = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
const only = option("--only")?.split(",")
const shots = option("--shots")

export class Failed extends Error {}

const TEST_LIMIT_S = Number(process.env.E2E_TEST_LIMIT_S ?? 180) // per test; a loaded Mac may need more

/** What a test is given: the page, the server, and the steps a person takes. */
function tools(page, base, folder, answer = async () => {}) {
  const q = async (name, params = {}) => {
    const r = await fetch(`${base}/api/q/${name}?${new URLSearchParams(params)}`)
    if (!r.ok) throw new Error(`${name}: ${r.status} ${(await r.text()).slice(0, 200)}`)
    return r.json()
  }
  const c = async (name, body = {}) => {
    const r = await fetch(`${base}/api/c/${name}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
    const said = await r.json()
    if (!r.ok || said.ok === false) throw new Error(`${name}: ${r.status} ${JSON.stringify(said).slice(0, 300)}`)
    return said
  }
  const planned = async () => {
    for (let until = Date.now() + 180_000; Date.now() < until; await wait(300)) {
      const s = await q("status")
      if (s.plan_generation !== null && s.plan_generation >= s.generation) return
    }
    throw new Failed("the plan didn't catch up within three minutes")
  }
  const expect = (ok, said) => {
    if (!ok) throw new Failed(said)
  }
  /** `expression`'s answer once it's truthy, within `ms`. */
  const until = async (expression, ms = 10_000, said = expression) => {
    for (let end = Date.now() + ms; ; await wait(150)) {
      const answer = await evaluate(page, expression).catch(() => null)
      if (answer) return answer
      if (Date.now() > end) throw new Failed(`waited ${ms / 1000}s for: ${said}`)
    }
  }
  const text = (selector = "body") => evaluate(page, `(document.querySelector(${JSON.stringify(selector)})?.innerText ?? "").replace(/\\s+/g, " ")`)
  /** Whether the page (or `selector`) shows `words`, waiting for it a while. */
  const has = (words, selector = "body", ms = 10_000) =>
    until(`(document.querySelector(${JSON.stringify(selector)})?.innerText ?? "").replace(/\\s+/g, " ").includes(${JSON.stringify(words)})`, ms, `"${words}" on the page`)
  /** Waits until the page (or `selector`) no longer shows `words`. */
  const gone = (words, selector = "body", ms = 10_000) =>
    until(`!(document.querySelector(${JSON.stringify(selector)})?.innerText ?? "").replace(/\\s+/g, " ").includes(${JSON.stringify(words)})`, ms, `"${words}" gone from the page`)
  /** A raw request to the server: its status and its JSON (a refusal's message), nothing thrown. */
  const request = async (method, route, body, headers = {}) => {
    const r = await fetch(`${base}${route}`, { method, headers: { "content-type": "application/json", ...headers }, body: body === undefined ? undefined : JSON.stringify(body) })
    return { status: r.status, body: await r.json().catch(() => null) }
  }
  /** Presses the button named `name` (its words or aria-label), the first showing, inside `within` if given: a row's
   * circle and the detail panel's button can share a name ("Mark done"). */
  const click = async (name, { within = null } = {}) => {
    await evaluate(page, SEEN).catch(() => {})
    await until(CLICK(name, within), 10_000, `a button "${name}"${within ? ` in ${within}` : ""}`)
    await evaluate(page, SETTLE).catch(() => {}) // a button that reloads the page leaves nothing to settle
    await laidOut(`after pressing "${name}"`)
  }
  /** What opened sits right: sized, inside its dialog, reachable (browser.mjs LAYOUT; 25 Nov, the user: the tests
   * pressed every button and never saw a dropdown the width of its dialog). After every click, and `evaluate`. */
  const laidOut = async (when) => {
    // a page that's gone (a button that reloads) has nothing to check; the check itself failing is a failure
    const wrong = await evaluate(page, LAYOUT).catch((e) => (/SyntaxError|ReferenceError|TypeError/.test(String(e)) ? [`the layout check broke: ${e}`] : []))
    if (wrong?.length) throw new Failed(`${when}: ${wrong.join("; ")}`)
  }
  /** Types into the field labeled `label` (its aria-label, placeholder or label text), as keys, then Enter if asked. */
  const type = async (label, words, { enter = false } = {}) => {
    const found = await until(`(() => {
      const want = ${JSON.stringify(label)}
      const fields = [...document.querySelectorAll("input, textarea, [contenteditable=true]")]
      const el = fields.find((f) => f.getAttribute("aria-label") === want || f.getAttribute("placeholder")?.startsWith(want) || f.labels?.[0]?.innerText.trim() === want)
      if (!el) return false
      el.focus()
      if ("value" in el) { const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set; set.call(el, ""); el.dispatchEvent(new Event("input", { bubbles: true })) }
      return true
    })()`, 10_000, `a field "${label}"`)
    if (found) await page("Input.insertText", { text: words })
    if (enter) await press(page, "Enter")
    await evaluate(page, SETTLE)
  }
  const open = (route) => go(page, base, route)
  const day = (n) => {
    const d = new Date(Date.now() + n * 86_400_000)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  }
  let answering = false
  const answered = async (given) => {
    answering = !!given
    await answer(given)
  }
  const done = async () => answering && (await answered(null))
  return { page, base, folder, open, click, type, text, has, gone, until, q, c, request, planned, day, expect, wait,
           answer: answered, stub: answered, done, press: (k) => press(page, k), laidOut,
           evaluate: async (expression) => {
             if (/\.click\(\)/.test(expression)) await evaluate(page, SEEN).catch(() => {})
             const out = await evaluate(page, expression)
             if (/\.click\(\)/.test(expression)) await evaluate(page, SETTLE).then(() => laidOut("after a click")).catch((e) => { if (e instanceof Failed) throw e })
             return out
           } }
}

/** Minutes from now to `hour` o'clock of today in this process's zone (TZ). */
function shiftToHour(hour) {
  const now = new Date()
  return Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate(), hour, 0).getTime() - now.getTime()) / 60_000)
}

/** Node's clock, `minutes` on: what the tests read as now is the sample's now. */
function shiftClock(minutes) {
  const Real = Date
  const ms = minutes * 60_000
  globalThis.Date = class extends Real {
    constructor(...given) {
      if (given.length) super(...given)
      else super(Real.now() + ms)
    }
    static now() {
      return Real.now() + ms
    }
  }
}

async function main() {
  const files = readdirSync(HERE).filter((f) => f.endsWith(".e2e.mjs")).sort()
  const chosen = files.filter((f) => !only || only.includes(f.replace(".e2e.mjs", "")))
  const given = option("--url")
  // Each file on a sample of its own (24 Nov: run all together on one, what one file made, late work say, changed what
  // the next saw, and tests that passed alone failed); --url: all on that one Friday, as before.
  // 26 Nov: at one hour of the day, 2pm unless FRIDAY_TEST_HOUR says, as the server and screen tests are. Run past
  // midnight, Friday's day was still yesterday's until 4am and the tests' "yesterday" (day(-1), "3 days back") one day
  // off: a nap logged yesterday was looked for the day after, meals days back weren't found, a token "last used today"
  // read yesterday. The sample runs at that hour of today (--shift-minutes), Node's clock with it, and the page follows
  // Friday's clock (hooks/useClock.ts). Alex lives in New York (sim/sample.py); --url: the Friday given, as it is.
  const shift = given ? 0 : (process.env.TZ = process.env.TZ ?? "America/New_York", shiftToHour(Number(process.env.FRIDAY_TEST_HOUR ?? 14)))
  if (shift) shiftClock(shift)
  const sampleFor = async () =>
    given ? { base: given.replace(/\/$/, ""), folder: option("--folder"), stop: () => {} } : await serveSample({ case: option("--case") ?? "alex", prefix: "friday-e2e-", shiftMinutes: shift })
  const { page, close, answer } = await openChrome()
  const failed = []
  let passed = 0
  const started = Date.now()
  let sample = null
  try {
    await page("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
    for (const file of chosen) {
      sample?.stop()
      sample = await sampleFor()
      const t = tools(page, sample.base, sample.folder, answer)
      // 25 Nov: the tests' own clock reads Friday's zone. They write Friday's local times from Node's Date ("20 minutes
      // ago", day(-1), a Mac event's offset), and on a Mac an hour west of Alex's New York those were an hour off: a
      // snack ate 80 minutes, a nap 65, a 6pm repeat read 7pm. Chrome keeps the Mac's zone: the page follows Friday's
      // clock itself (hooks/useClock.ts), and should go on doing so wherever the browser is.
      const zone = (await t.q("settings")).time?.timezone
      if (zone) process.env.TZ = zone
      await t.planned()
      const tests = (await import(pathToFileURL(path.join(HERE, file)).href)).default
      for (const test of tests) {
        const label = `${file.replace(".e2e.mjs", "")}: ${test.name}`
        const began = Date.now()
        try {
          // one stuck test fails, rather than holding the run (24 Nov: a run hung an hour and a half)
          let timer
          const limit = new Promise((_, fail) => (timer = setTimeout(() => fail(new Failed(`took over ${TEST_LIMIT_S}s`)), TEST_LIMIT_S * 1000)))
          await Promise.race([test.run(t), limit]).finally(() => clearTimeout(timer))
          passed++
          console.log(`  ✓ ${label} (${((Date.now() - began) / 1000).toFixed(1)}s)`)
        } catch (error) {
          failed.push({ label, error })
          console.log(`  ✗ ${label}\n      ${error instanceof Failed ? error.message : error.stack ?? error}`)
          if (shots) {
            mkdirSync(shots, { recursive: true })
            const { data } = await page("Page.captureScreenshot", { format: "png" })
            writeFileSync(path.join(shots, `${label.replace(/[^a-z0-9]+/gi, "-")}.png`), Buffer.from(data, "base64"))
          }
        } finally {
          await t.done() // a test's made-up answers (`answer`, `stub`) end with it
        }
      }
    }
  } finally {
    close()
    sample?.stop()
  }
  console.log(`${passed} passed, ${failed.length} failed, in ${Math.round((Date.now() - started) / 1000)}s`)
  process.exit(failed.length ? 1 : 0)
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(130))
main().catch((error) => {
  console.error(error)
  process.exit(2)
})
