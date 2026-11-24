// Updates (tests/features.toml: updates): Settings → Updates and the update popup, as a person uses them. First on the
// run's own sample, a copy that doesn't look for updates (Friday Test, run from code): it says so, and when an update
// would go in is still yours to choose. Then on a second sample started as a downloaded Friday 0.2.0 is (its version
// and a feed), with a stand-in for Friday's site on this machine: the popup with the new version's notes, Later, Check
// now finding what was published since, a test user's code joined and left, and Update failing on a download that
// isn't the file published (nothing is ever installed). Each step checked on the page and on that server.

import { createServer } from "node:http"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { freePort, go, serveSample } from "../scripts/browser.mjs"

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const CODE = "K7QF-29XM"

/** Friday's site, as the admin hub writes it: everyone's feed, the test users' for Ana's code, and downloads that are
 * never the file the feed published (so an update fails its checksum, and nothing is installed). */
async function standInSite() {
  const port = await freePort()
  const address = `http://127.0.0.1:${port}`
  const site = { address, everyone: ["0.2.1"], asked: [] }
  const entry = (version, test = false) => ({
    version,
    released: "2026-11-20",
    url: `${address}/dl/${version}.dmg`,
    sha256: "0".repeat(64),
    bytes: 1000,
    minimum_macos: "14.0",
    notes: { summary: `Friday ${version} for the e2e.`, new: [`New in ${version}.`], changed: [], fixed: [`Fixed in ${version}.`] },
    ...(test ? { test: true } : {}),
  })
  const server = createServer((req, res) => {
    const code = req.headers["x-friday-test-user"] ?? null
    site.asked.push({ path: req.url, code })
    const send = (status, body) => {
      const data = typeof body === "string" ? body : JSON.stringify(body)
      res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(data) })
      res.end(data)
    }
    if (req.url === "/updates.json") {
      const ana = code !== null && code.replace("-", "").toUpperCase() === CODE.replace("-", "")
      const versions = site.everyone.map((v) => entry(v))
      const feed = { current: site.everyone.at(-1), versions, ...(code !== null ? { test_user: ana ? "Ana" : null } : {}) }
      if (ana) Object.assign(feed, { current: "0.3.0", versions: [entry("0.3.0", true), ...versions] })
      return send(200, feed)
    }
    if (req.url.startsWith("/dl/")) return send(200, "not the published disk image")
    return send(404, { state: "none" })
  })
  await new Promise((done) => server.listen(port, "127.0.0.1", done))
  return { site, close: () => server.close() }
}

/** A second sample, started as a downloaded Friday 0.2.0 that reads `feed`. */
async function downloadedFriday(feed, staging) {
  const env = { FRIDAY_APP_VERSION: "0.2.0", FRIDAY_UPDATE_FEED: feed, FRIDAY_UPDATE_DIR: staging }
  const was = Object.fromEntries(Object.keys(env).map((k) => [k, process.env[k]]))
  Object.assign(process.env, env)
  try {
    return await serveSample({ case: "maya", prefix: "friday-e2e-updates-" })
  } finally {
    for (const [k, v] of Object.entries(was)) v === undefined ? delete process.env[k] : (process.env[k] = v)
  }
}

const dialog = `[aria-label="Update Friday"]`

export default [
  {
    name: "a copy that doesn't look says so, and when an update goes in is saved as picked",
    async run({ open, click, has, until, q, wait, expect }) {
      const status = await q("update_status")
      expect(status.checks === false, "the run's sample looks for updates")
      await open("/settings/updates")
      await has("This Friday doesn't look for updates")
      await has("This copy doesn't check for updates")
      await until(`![...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Check now")`, 2_000, "no Check now")
      await until(`!document.querySelector('[aria-label="Test user invite"]')`, 2_000, "no test user's box")
      await click("When I quit Friday")
      await eventually(async () => (await q("update_status")).restart === "quit", 10_000, "updates going in when you quit, on the server", wait)
      expect((await q("settings")).updates.restart === "quit", "the setting isn't saved")
      await click("Right away")
      await eventually(async () => (await q("update_status")).restart === "now", 10_000, "updates going in right away", wait)
    },
  },
  {
    name: "a downloaded Friday: the popup's notes, Later, Check now, a test user's code, and a download that fails",
    async run({ page, click, type, has, until, text, wait, expect }) {
      const { site, close } = await standInSite()
      const staging = mkdtempSync(path.join(tmpdir(), "friday-e2e-staging-"))
      let friday
      try {
        friday = await downloadedFriday(`${site.address}/updates.json`, staging)
        const base = friday.base
        const status = async () => (await fetch(`${base}/api/q/update_status`)).json()
        const settled = (check) => eventually(async () => { const s = await status(); return s.state !== "checking" && check(s) && s }, 60_000, "the updater to settle", wait)
        await settled((s) => s.versions.length)
        // the popup, at once, with the new version's notes
        await go(page, base, "/settings/updates")
        await has("Friday 0.2.1 is ready", dialog)
        await has("Fixed in 0.2.1.", dialog)
        await has("You have 0.2.0", dialog)
        await click("Later")
        await eventually(async () => (await status()).popup === false, 10_000, "Later kept on the server", wait)
        await until(`!document.querySelector(${JSON.stringify(dialog)})`, 5_000, "the popup closed")
        await has("Friday 0.2.1 is out")
        await has("You have 0.2.0 · Looked")
        // published since: Check now finds it, and a newer one than the one put off asks at once
        site.everyone = ["0.2.1", "0.2.2"]
        await click("Check now")
        await settled((s) => s.versions[0]?.version === "0.2.2")
        await has("Friday 0.2.2 is out")
        await has("Friday 0.2.2 is ready", dialog)
        await click("Later")
        await until(`!document.querySelector(${JSON.stringify(dialog)})`, 5_000, "the popup closed")
        // a test user's code, typed as given
        await type("Test user invite", "k7qf 29xm")
        await click("Join")
        await has("You're a test user, as Ana", "body", 30_000)
        await has(`Code ${CODE}`)
        const joined = await settled((s) => s.test_user?.known)
        expect(joined.test_user.code === CODE && joined.versions[0].version === "0.3.0" && joined.versions[0].test, `the server has ${JSON.stringify(joined.test_user)}, offering ${joined.versions[0]?.version}`)
        expect(site.asked.some((a) => a.path === "/updates.json" && a.code === CODE), "the code wasn't sent to the site")
        await has("for test users, before everyone", dialog)
        await click("Later")
        await until(`!document.querySelector(${JSON.stringify(dialog)})`, 5_000, "the popup closed")
        await click("Stop being a test user")
        await has("You're no longer a test user")
        const left = await settled((s) => s.test_user === null)
        expect(!left.versions.some((v) => v.test), "a test users' version is still offered after leaving")
        await until(`!!document.querySelector('[aria-label="Test user invite"]')`, 10_000, "the invite box back")
        // See what's new opens the popup; Update downloads, and a file that isn't the one published fails, said
        await click("See what's new")
        await has("Friday 0.2.2 is ready", dialog)
        await click("Update")
        await has("The download isn't the file the site published (its checksum differs).", "body", 30_000)
        const failed = await status()
        expect(failed.state === "failed" && failed.staged === null, `the server's updater is ${failed.state}`)
        expect((await text("body")).includes("Friday 0.2.2"), "the page lost the version it tried")
      } finally {
        friday?.stop()
        close()
        rmSync(staging, { recursive: true, force: true })
      }
    },
  },
]
