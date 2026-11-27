// Friday in headless Chrome, for the checks in this folder: a sample served from a folder of its own
// (`fridayd demo`), Chrome spoken to over its DevTools protocol (Node's own WebSocket: nothing to install), and the
// steps a check takes on a page (load, settle, press, click, wait for an answer). Used by overflow-check.mjs (the
// layout) and agreement-check.mjs (what the pages say against the plan).

import { spawn } from "node:child_process"
import { cpSync, existsSync, mkdtempSync, rmSync } from "node:fs"
import { createServer } from "node:net"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")

export function freePort() {
  return new Promise((done, fail) => {
    const probe = createServer()
    probe.once("error", fail)
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address()
      probe.close(() => done(port))
    })
  })
}

export const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/** A sample (Alex's lived-in one unless said), served from a folder of its own, terms accepted and Setup answered, as the screen tests do. */
export async function serveSample({ case: who = "alex", ready = true, prefix = "friday-check-", shiftMinutes = 0, from = null } = {}) {
  const folder = mkdtempSync(path.join(tmpdir(), prefix))
  if (from) cpSync(from, folder, { recursive: true }) // a sample built already: served as it is, not lived again
  const port = await freePort()
  const keys = { MICROSOFT_CLIENT_ID: "test-microsoft-id", SLACK_CLIENT_ID: "test-slack-id", SLACK_CLIENT_SECRET: "test-slack-secret", TICKTICK_CLIENT_ID: "test-ticktick-id", TICKTICK_CLIENT_SECRET: "test-ticktick-secret", TRELLO_CLIENT_ID: "test-trello-id" }
  const env = { ...process.env, FRIDAY_CHAINS: "3", FRIDAY_FIXED_EFFORT: "1", FRIDAY_WEB_DIST: process.env.FRIDAY_WEB_DIST ?? path.join(REPO, "web/dist"), ...Object.fromEntries(Object.entries(keys).map(([k, v]) => [`FRIDAY_${k}`, v])) }
  delete env.VIRTUAL_ENV
  // in a process group of its own, ended whole: uv runs Python, which runs solver workers, and a signal to uv alone
  // can leave them serving
  const child = spawn("uv", ["run", "--quiet", "fridayd", "--data-dir", folder, "demo", "--case", who, ...(ready ? ["--ready"] : []), "--port", String(port), ...(shiftMinutes ? ["--shift-minutes", String(shiftMinutes)] : [])], { cwd: REPO, env, stdio: ["ignore", "ignore", "pipe"], detached: true })
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
  return { base, folder, halt: end, stop: () => (end(), rmSync(folder, { recursive: true, force: true, maxRetries: 5 })) }
}

/** Ends a process started `detached` and everything it started. */
export function ended(child) {
  try {
    process.kill(-child.pid, "SIGKILL")
  } catch {
    // already gone
  }
}

export function chromePath() {
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  return process.env.CHROME || (existsSync(mac) ? mac : "google-chrome")
}

/** Headless Chrome and a page in it, spoken to over the DevTools protocol. */
export async function openChrome() {
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
  // Chrome gone (its DevTools socket closed): what still waits on it fails, rather than waiting forever (24 Nov: a
  // browser test run hung an hour and a half on one)
  let closed = null
  socket.onclose = () => {
    closed = new Error("Chrome's DevTools connection closed")
    for (const [, fail] of pending.values()) fail(closed)
    pending.clear()
  }
  const send = (method, params = {}, sessionId) =>
    new Promise((done, fail) => {
      if (closed) return fail(closed)
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
  // A state's made-up answers (`answer`): the page's questions to /api/q/<name> (and, keyed "c/<name>", its commands
  // to /api/c/<name>) answered here, the rest let through.
  let answers = {}
  // a page asking before it's left (What if's changes not kept) would hold everything: it's answered yes
  listeners.add((msg) => msg.method === "Page.javascriptDialogOpening" && msg.sessionId === sessionId && page("Page.handleJavaScriptDialog", { accept: true }).catch(() => {}))
  listeners.add((msg) => {
    if (msg.method !== "Fetch.requestPaused" || msg.sessionId !== sessionId) return
    const { requestId, request } = msg.params
    // a query by its name; a command as "c/<name>"
    const name = new URL(request.url).pathname.replace(/^\/api\/q\//, "").replace(/^\/api\/c\//, "c/")
    if (name in answers) {
      const body = Buffer.from(JSON.stringify(answers[name])).toString("base64")
      page("Fetch.fulfillRequest", { requestId, responseCode: 200, responseHeaders: [{ name: "content-type", value: "application/json" }], body }).catch(() => {})
    } else page("Fetch.continueRequest", { requestId }).catch(() => {})
  })
  const answer = async (given) => {
    answers = given ?? {}
    const commands = Object.keys(answers).some((k) => k.startsWith("c/")) ? [{ urlPattern: "*/api/c/*" }] : []
    if (given) await page("Fetch.enable", { patterns: [{ urlPattern: "*/api/q/*" }, ...commands] })
    else await page("Fetch.disable")
  }
  const close = () => {
    socket.close()
    ended(chrome)
    rmSync(profile, { recursive: true, force: true, maxRetries: 5 })
  }
  return { page, close, answer }
}

export async function evaluate(page, expression) {
  let timer
  const late = new Promise((_, fail) => (timer = setTimeout(() => fail(new Error("the page didn't answer in 30s")), 30_000)))
  const { result, exceptionDetails } = await Promise.race([page("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }), late]).finally(() => clearTimeout(timer))
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text)
  return result.value
}

// In the page: wait until nothing has changed for a moment (data in, animations done), up to two and a half seconds
// (a clock or a spinner never stops changing).
export const SETTLE = `new Promise((done) => {
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
export const CLICK = (said, within = null) => `(() => {
  const root = ${within ? `document.querySelector(${JSON.stringify(within)})` : "document"}
  if (!root) return false
  const menu = ${JSON.stringify(said)}.endsWith("…")
  const name = ${JSON.stringify(said)}.replace(/…$/, "")
  const named = (el) => (el.getAttribute("aria-label") || el.textContent || "").replace(/\\s+/g, " ").trim()
  const all = [...root.querySelectorAll("button, a, [role=button], [role=menuitem], [role=tab], [role=option]")]
  const showing = all.filter((el) => el.getBoundingClientRect().width > 0 && (!menu || el.hasAttribute("aria-expanded")))
  const names = name.split("|")
  const el = showing.find((el) => names.includes(named(el))) || showing.find((el) => names.some((n) => named(el).startsWith(n)))
  if (!el) return false
  el.click()
  return true
})()`

export async function press(page, combo) {
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
export async function go(page, base, route) {
  await load(page, "about:blank") // the last page's questions to the server stop here, not left running
  await page("Storage.clearDataForOrigin", { origin: base, storageTypes: "local_storage,session_storage" })
  await load(page, `${base}/?look=${++loads}#${route}`)
  await evaluate(page, SETTLE)
}

/** Navigates and waits for the new page (the old one is marked, so its own "complete" isn't taken for the new one's;
 * the address can't tell them apart, as the app may rewrite it). */
export async function load(page, url) {
  await evaluate(page, "window.__leaving = true").catch(() => {})
  await page("Page.navigate", { url })
  for (let until = Date.now() + 20_000; Date.now() < until; await wait(100)) {
    const ready = await evaluate(page, `!window.__leaving && document.readyState === "complete"`).catch(() => false)
    if (ready) return
  }
  throw new Error(`${url} didn't load`)
}

/** `expression`'s answer once it has one (a button or a list can wait on the server's answer), within ten seconds. */
export async function until(page, expression) {
  for (let tries = 0; ; tries++) {
    const answer = await evaluate(page, expression)
    if (answer || tries >= 40) return answer
    await wait(250)
  }
}

/** Before a click, what's on the page: LAYOUT then knows what the click opened, whatever it's made of. */
export const SEEN = `(window.__seen = new WeakSet(document.querySelectorAll("body *")), window.__chooser = false,
  document.addEventListener("click", (e) => {
    // read as it's pressed, before the page changes: a value's caret points down; a "show more" toggle's points right
    // until it's open, and what it shows is a section, not a dropdown
    const button = e.target.closest?.("button, [role=button]")
    window.__chooser = !!button && (button.matches("[aria-haspopup]") || !!button.querySelector(".ph-caret-down"))
  }, { capture: true, once: true }), true)`

/** What's wrong with how the page's open parts sit, as words (none: []). Run after every click in web/e2e (25 Nov,
 * the user: "the dropdown for take a break when i select it is huge ... see why the web test that clicks every button
 * and tries every feature on a real ui didn't catch this": the tests checked what happened, never how it looked).
 * A dropdown: every menu's list, and what a button offering choices (a caret, or aria-haspopup)
 * opened inside a dialog already open, whatever it's made of (new since SEEN). 1. At most 440px wide; never off the
 * window unless it scrolls. 2. Within its dialog's sides. 3. A dialog fits the window, or scrolls, so its buttons can
 * be reached. */
export const LAYOUT = `(() => {
  const out = [], vh = innerHeight, seen = window.__seen
  const name = (el) => (el.getAttribute("aria-label") || el.innerText || el.className || "").trim().split("\\n")[0].slice(0, 40)
  // a box: its own background or a border all round (a row's divider line under it isn't one)
  const boxed = (el) => {
    const c = getComputedStyle(el)
    const all = ["Top", "Right", "Bottom", "Left"].every((side) => parseFloat(c["border" + side + "Width"]) > 0)
    return c.backgroundColor !== "rgba(0, 0, 0, 0)" || all
  }
  // what offers choices: a button with a caret (a value you change), or one that says it opens a menu; a section
  // shown, a row added or a question asked isn't a dropdown
  const chooser = window.__chooser
  const opened = [...document.querySelectorAll("[role=listbox], [role=menu]")]
  if (seen && chooser) for (const el of document.querySelectorAll("[role=dialog] *")) {
    // new since the click, a box, in a dialog that was open before it (a dialog the click opened is a dialog)
    if (seen.has(el) || !el.children.length || !boxed(el) || !seen.has(el.closest("[role=dialog]"))) continue
    if (el.matches("button, input, textarea, [role=option], [role=dialog]")) continue
    opened.push(el)
  }
  for (const el of opened) {
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) continue
    const scrolls = el.scrollHeight > el.clientHeight + 1 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)
    if (r.width > 440) out.push("a dropdown " + Math.round(r.width) + "px wide (at most 440): " + name(el))
    if ((r.bottom > vh + 1 || r.top < -1) && !scrolls) out.push("a dropdown running off the window that doesn't scroll: " + name(el))
    const dialog = el.closest("[role=dialog]")
    if (dialog) {
      const d = dialog.getBoundingClientRect()
      if (r.left < d.left - 1 || r.right > d.right + 1) out.push("a dropdown out of its dialog's sides: " + name(el))
    }
  }
  for (const dialog of document.querySelectorAll("[role=dialog]")) {
    const d = dialog.getBoundingClientRect()
    if (!d.height) continue
    let scroller = dialog
    while (scroller && !(scroller.scrollHeight > scroller.clientHeight + 1 && /(auto|scroll)/.test(getComputedStyle(scroller).overflowY))) scroller = scroller.parentElement
    if (d.bottom > vh + 1 && !scroller) out.push("a dialog runs " + Math.round(d.bottom - vh) + "px past the window's foot with no scroll: " + name(dialog))
  }
  return [...new Set(out)]
})()`
