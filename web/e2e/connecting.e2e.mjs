// Google: connect, remove (tests/features.toml: connecting), in Settings → Integrations (the Google Calendar card) and
// Settings → Calendars: the accounts Friday reads, as the server has them; Remove asks first, Keep keeps it, and the
// server's refusal is said in the card; a sign-in waiting on Google's page says so and Cancel sign-in stops it on the
// server; a key file that isn't Google's is refused in words. Nothing here signs in to Google or opens its page, and
// no key file is ever kept: the sample's stand-in Google is a demo's (`answer` says it isn't, where a page hides
// buttons in a demo), and the files chosen are refused before anything is written.

import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"

const CARD = "Google Calendar"

/** Chooses `content` as the file in the page's file field, as a person picking it in the file dialog. */
async function choose(page, content) {
  const file = path.join(mkdtempSync(path.join(tmpdir(), "friday-e2e-key-")), "client_secret_e2e.json")
  writeFileSync(file, content)
  const { result } = await page("Runtime.evaluate", { expression: `document.querySelector("input[type=file]")` })
  if (!result.objectId) throw new Error("no file field")
  await page("DOM.setFileInputFiles", { files: [file], objectId: result.objectId })
}

export default [
  {
    name: "the Google card lists each account the server reads, with how many of its calendars, and Calendars lists them",
    async run({ open, click, has, text, q, expect }) {
      const access = await q("google_connect_status")
      const calendars = await q("google_calendars")
      expect(access.accounts.length > 0, "the sample has no Google account")
      await open("/settings/integrations")
      await has(`${calendars.filter((c) => c.on).length} connected`) // the box, closed
      await click(CARD)
      for (const a of access.accounts) {
        await has(a.email)
        const its = calendars.filter((c) => (c.account ?? "") === a.email)
        const on = its.filter((c) => c.on)
        const line = on.length <= 3 ? "Reads " : `Reads ${on.length} of its ${its.length} calendars.`
        expect((await text("main")).includes(line), `"${line}" isn't said for ${a.email}`)
      }
      expect(!(await text("main")).includes("Add another Google account"), "the demo offers to connect another account")
      await open("/settings/calendars")
      for (const c of calendars.filter((c) => c.on)) await has(c.name)
    },
  },
  {
    name: "Remove asks first; Keep keeps it; Remove is sent, and the server's refusal is said",
    async run({ open, click, has, gone, q, answer, expect }) {
      const status = await q("status")
      const access = await q("google_connect_status")
      const email = access.accounts[0].email
      await answer({ status: { ...status, demo: false } }) // the page shows what an account of yours has
      await open("/settings/integrations")
      await click(CARD)
      await click(`Remove ${email}`)
      await has(`Remove ${email}? Friday stops reading its calendars and mail.`)
      await click("Keep")
      await gone(`Remove ${email}?`)
      await click(`Remove ${email}`)
      await click("Remove")
      await has("The demo uses a stand-in Google, so there's nothing to remove.")
      expect((await q("google_connect_status")).accounts.some((a) => a.email === email), "the account was removed")
    },
  },
  {
    name: "a sign-in waiting on Google's page says so; Cancel sign-in stops it on the server",
    async run({ open, click, has, gone, q, answer, expect }) {
      const status = await q("status")
      const access = await q("google_connect_status")
      await answer({ status: { ...status, demo: false }, google_connect_status: { ...access, state: "waiting", account: null, url: "about:blank#google" } })
      await open("/settings/integrations")
      await click(CARD)
      await has("Waiting for Google…")
      await has("Google's page is open in your browser: choose the account and click Allow")
      await has("Didn't see it? Open Google's page")
      await click("Cancel sign-in")
      await gone("Waiting for Google…")
      await has("Add another Google account")
      expect((await q("google_connect_status")).state !== "waiting", "the server still waits on Google")
    },
  },
  {
    name: "a key file that isn't Google's, or a website's, is refused in words and nothing is kept",
    async run({ open, click, has, q, answer, page, expect }) {
      const status = await q("status")
      const access = await q("google_connect_status")
      await answer({ status: { ...status, demo: false }, google_connect_status: { ...access, client_file: false, calendar: false, accounts: [], state: "idle" } })
      await open("/settings/integrations")
      await click(CARD)
      await click("Advanced: Google with a Google Cloud key of your own") // folded when no account is connected
      await has("Choose the key file")
      await choose(page, '{"not": "a key"}')
      await has("That isn't Google's key file. It's the .json file Google Cloud downloads.")
      await choose(page, '{"web": {"client_id": "x"}}')
      await has("That key is for a website. Friday needs one for a Desktop app")
      expect((await q("google_connect_status")).client_file === access.client_file, "the key file changed")
    },
  },
  {
    name: "the server refuses removing in the demo, and an account not connected for Google Tasks",
    async run({ request, expect }) {
      const remove = await request("POST", "/api/c/google_remove", { account: "nobody@example.com" })
      expect(remove.status === 422 && remove.body.message.includes("stand-in Google"), JSON.stringify(remove))
      const tasks = await request("POST", "/api/c/google_tasks_connect", { account: "nobody@example.com" })
      expect(tasks.status === 422, JSON.stringify(tasks))
    },
  },
]
