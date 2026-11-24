// Other apps (tests/features.toml: integrations): Settings → Integrations' gallery, searched and opened as a person
// would; Todoist's token box (Connect only once a token is pasted; never pressed, so nothing reaches Todoist);
// Microsoft To Do's Sign in, which opens Microsoft's page with this Friday's app and its way back here (the page is
// caught, not loaded), and the page you come back to when you said no; and a connected one (Apple Reminders, which
// needs no account): how its to-dos arrive, and Disconnect asked, cancelled, then done. Each step checked on the page
// and on the server.

import { load } from "../scripts/browser.mjs"

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const panel = (name) => `[role=dialog][aria-label=${JSON.stringify(name)}]`
const button = (name, within = "body") =>
  `[...document.querySelector(${JSON.stringify(within)})?.querySelectorAll("button") ?? []].find((b) => b.textContent.trim() === ${JSON.stringify(name)})`

export default [
  {
    name: "the gallery's search finds a service by its other names, and says when nothing matches",
    async run({ open, type, has, until, text, expect }) {
      await open("/settings/integrations")
      await has("Open a box to connect it")
      await type("Search integrations", "wunderlist")
      await until(`!!document.querySelector('[data-integration="microsoft_todo"]')`, 5_000, "Microsoft To Do found as wunderlist")
      const found = await until(`[...document.querySelectorAll("[data-integration]")].map((b) => b.dataset.integration).join(",")`, 5_000)
      expect(found === "microsoft_todo", `wunderlist found ${found}`)
      await type("Search integrations", "zzqq nothing")
      await has("Nothing called “zzqq nothing” yet.")
      expect(!(await text("body")).includes("Todoist"), "Todoist still shown for a search that matches nothing")
      await type("Search integrations", "")
      await until(`document.querySelectorAll("[data-integration]").length > 10`, 5_000, "the whole gallery back")
    },
  },
  {
    name: "Todoist's box: its token steps, and Connect only once a token is pasted",
    async run({ open, click, type, has, until, q, expect }) {
      await open("/settings/integrations")
      await click("Todoist")
      await has("Copy the API token shown there.", panel("Todoist"))
      await has("Open Todoist's token page", panel("Todoist"))
      expect(await until(`${button("Connect", panel("Todoist"))}?.disabled === true`, 5_000, "Connect disabled with no token"), "")
      await type("Paste the token", "0123456789abcdef")
      await until(`${button("Connect", panel("Todoist"))}?.disabled === false`, 5_000, "Connect ready once a token is pasted")
      await click("Close")
      await until(`!document.querySelector(${JSON.stringify(panel("Todoist"))})`, 5_000, "the box closed")
      expect((await q("integrations")).length === 0, "something connected without pressing Connect")
    },
  },
  {
    name: "Sign in with Microsoft opens Microsoft's page with this Friday's app; coming back with a no connects nothing",
    async run({ page, open, click, has, until, q, expect }) {
      await open("/settings/integrations")
      await until(`(window.open = (url) => ((window.__opened = url), null), true)`, 2_000) // the page is caught, not loaded
      await click("Microsoft To Do")
      await has("Press Sign in with Microsoft", panel("Microsoft To Do"))
      await click("Sign in with Microsoft")
      const opened = await until(`window.__opened`, 10_000, "Microsoft's page opened")
      const url = new URL(opened)
      const base = await until(`location.origin`)
      expect(url.origin === "https://login.microsoftonline.com", `opened ${url.origin}`)
      expect(url.searchParams.get("client_id") === "test-microsoft-id", `client_id ${url.searchParams.get("client_id")}`)
      expect(url.searchParams.get("redirect_uri") === `${base}/oauth/callback`, `redirect_uri ${url.searchParams.get("redirect_uri")}`)
      await has("Finish on Microsoft To Do's page in your browser", panel("Microsoft To Do"))
      await has("Open it again", panel("Microsoft To Do"))
      // Microsoft sends you back here: you said no
      await load(page, `${base}/oauth/callback?state=${url.searchParams.get("state")}&error=access_denied`)
      await has("Not connected")
      await has("Microsoft To Do didn't connect: you said no")
      expect((await q("integrations")).length === 0, "a sign-in you said no to connected something")
    },
  },
  {
    name: "a connected one: how its to-dos arrive is saved as picked, and Disconnect asks, cancels, then disconnects",
    async run({ open, click, has, until, q, c, wait, expect }) {
      const made = (await c("integration_connect", { kind: "reminders", token: "" })).result.source
      await open("/settings/integrations")
      await has("Connected")
      await until(`!!document.querySelector('section[aria-label="Connected"] [data-integration="reminders"]')`, 10_000, "Apple Reminders under Connected")
      await click("Apple Reminders")
      await has("New to-dos", panel("Apple Reminders"))
      await click("Always in the Inbox")
      await eventually(async () => (await q("integrations")).find((i) => i.id === made.id)?.arrival === "inbox", 10_000, "arriving in the Inbox, on the server", wait)
      await until(`[...document.querySelectorAll('[role=radio]')].find((r) => r.textContent.startsWith("Always in the Inbox"))?.getAttribute("aria-checked") === "true"`, 5_000, "the choice shown")
      await click("Disconnect")
      await has("Nothing changes in Apple Reminders.", panel("Apple Reminders"))
      await click("Cancel")
      await until(`!document.querySelector('[role=alertdialog][aria-label="Disconnect Apple Reminders"]')`, 5_000, "the question gone")
      expect((await q("integrations")).some((i) => i.id === made.id), "Cancel disconnected it")
      await click("Disconnect")
      await click("Keep them")
      await eventually(async () => !(await q("integrations")).some((i) => i.id === made.id), 10_000, "disconnected on the server", wait)
      await has("Apple Reminders disconnected")
      await until(`!document.querySelector('section[aria-label="Connected"] [data-integration="reminders"]')`, 10_000, "Apple Reminders no longer under Connected")
      await has("Open Friday on your Mac to connect Apple Reminders.", panel("Apple Reminders")) // its box back to Connect
    },
  },
]
