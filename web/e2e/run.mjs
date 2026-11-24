#!/usr/bin/env node
// The web layer (TESTING.md): each feature with a page has web/e2e/<feature>.e2e.mjs, which drives it in a real Chrome,
// headless, as a person would (opens the page, clicks, types) and checks what the page then shows against what the
// server has. This serves one sample (Alex's lived-in one unless --case), opens Chrome once and runs each file's
// tests in turn, each on a fresh page load.
//
//   node web/e2e/run.mjs [--only items,rules] [--case alex] [--url http://127.0.0.1:8791] [--shots DIR]
//
// A test file: `export default [{ name, run }]`, run({ page, open, click, type, text, has, until, q, c, planned, day,
// expect, answer, gone, request }) → throws on what's wrong. `answer({ name: json })` makes the page's questions to
// /api/q/<name> get that answer (a state the sample hasn't got), until the test ends; `gone(words)` waits for words to
// leave the page; `request(method, path, body, headers)` is a raw call to the server, for refusals ({ status, body }).
// Exit 0: all passed; 1: some failed (listed); 2: it couldn't run. Build web/dist first.

import { mkdirSync, readdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { CLICK, SETTLE, evaluate, go, openChrome, press, serveSample, wait } from "../scripts/browser.mjs"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const option = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
const only = option("--only")?.split(",")
const shots = option("--shots")

export class Failed extends Error {}

/** What a test is given: the page, the server, and the steps a person takes. */
function tools(page, base, answer = async () => {}) {
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
  const click = async (name) => {
    await until(CLICK(name), 10_000, `a button "${name}"`)
    await evaluate(page, SETTLE).catch(() => {}) // a button that reloads the page leaves nothing to settle
  }
  /** Types into the field labelled `label` (its aria-label, placeholder or label text), as keys, then Enter if asked. */
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
  return { page, open, click, type, text, has, gone, until, q, c, request, planned, day, expect, wait, answer: answered, done, press: (k) => press(page, k) }
}

async function main() {
  const files = readdirSync(HERE).filter((f) => f.endsWith(".e2e.mjs")).sort()
  const chosen = files.filter((f) => !only || only.includes(f.replace(".e2e.mjs", "")))
  const given = option("--url")
  const sample = given ? { base: given.replace(/\/$/, ""), stop: () => {} } : await serveSample({ case: option("--case") ?? "alex", prefix: "friday-e2e-" })
  const { page, close, answer } = await openChrome()
  const failed = []
  let passed = 0
  const started = Date.now()
  try {
    await page("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
    const t = tools(page, sample.base, answer)
    await t.planned()
    for (const file of chosen) {
      const tests = (await import(pathToFileURL(path.join(HERE, file)).href)).default
      for (const test of tests) {
        const label = `${file.replace(".e2e.mjs", "")}: ${test.name}`
        const began = Date.now()
        try {
          await test.run(t)
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
          await t.done() // a test's made-up answers end with it
        }
      }
    }
  } finally {
    close()
    sample.stop()
  }
  console.log(`${passed} passed, ${failed.length} failed, in ${Math.round((Date.now() - started) / 1000)}s`)
  process.exit(failed.length ? 1 : 0)
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(130))
main().catch((error) => {
  console.error(error)
  process.exit(2)
})
