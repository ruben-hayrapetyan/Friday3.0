// Mail by app password (tests/features.toml: mail_app), Settings → Integrations → iCloud Mail / Other mail (IMAP): the
// box opens to its steps and form; Connect waits for an address and a password (and, for other mail, a server); a
// server that can't be reached is said in words and nothing is kept; a mailbox kept in secrets.toml is listed as
// connected, read, and Stop reading forgets it. No real mail server is asked: the one given doesn't exist (.invalid).

import { readFileSync, writeFileSync } from "node:fs"
import path from "node:path"

const HOST = "imap.friday-e2e.invalid"
const ADDRESS = "e2e@friday-e2e.invalid"

const disabled = (name) => `(() => { const b = [...document.querySelectorAll("[role=dialog] button")].find((b) => b.textContent.trim() === ${JSON.stringify(name)}); return b ? b.disabled : null })()`

export default [
  {
    name: "iCloud Mail opens to its steps; Connect waits for an address and a password",
    async run({ open, click, type, has, until, evaluate, expect }) {
      await open("/settings/integrations")
      await type("Search integrations", "icloud")
      await click("iCloud Mail")
      await has("App-Specific Passwords")
      await has("Your password stays on this Mac.")
      expect((await until(`${disabled("Connect")} === true`)) === true, "Connect is pressable with nothing typed")
      await type("Address", "not-an-address")
      await type("App password", "abcd-efgh")
      expect((await until(`${disabled("Connect")} === true`)) === true, "Connect is pressable for an address without @")
      await type("Address", "someone@icloud.com")
      expect((await until(`${disabled("Connect")} === false`)) === true, "Connect stays off with an address and a password")
      expect(!(await evaluate(`!!document.querySelector('[aria-label="IMAP server"]')`)), "iCloud asks for a server")
    },
  },
  {
    name: "other mail asks for its server too; one that can't be reached is said in words and nothing is kept",
    async run({ open, click, type, has, until, q, expect }) {
      await open("/settings/integrations")
      await type("Search integrations", "imap")
      await click("Other mail (IMAP)")
      await has("Find your provider's IMAP server name")
      await type("Address", ADDRESS)
      await type("App password", "e2e-password")
      expect((await until(`${disabled("Connect")} === true`)) === true, "Connect is pressable without the server")
      await type("IMAP server", HOST)
      await click("Connect")
      await has("Friday couldn't reach Other mail: check the connection and server", "body", 30_000)
      expect((await q("mail_app_accounts")).length === 0, "a mailbox that couldn't be reached was kept")
    },
  },
  {
    name: "a mailbox kept is listed as connected and read; Stop reading forgets it",
    async run({ open, click, type, has, until, q, folder, expect }) {
      expect(folder, "this test needs the sample's folder (run without --url, or give --folder)")
      const secrets = path.join(folder, "secrets.toml")
      let kept = ""
      try {
        kept = readFileSync(secrets, "utf8")
      } catch {
        // none yet
      }
      // as mail_app_set keeps one once its server took the password (commands/mail_app.py)
      writeFileSync(secrets, `${kept}\n[mail_app]\nprovider = "other"\naddress = "${ADDRESS}"\npassword = "e2e-password"\nhost = "${HOST}"\n`, { mode: 0o600 })
      const listed = await q("mail_app_accounts")
      expect(listed.length === 1 && listed[0].address === ADDRESS && listed[0].name === "Other mail", `the server lists ${JSON.stringify(listed)}`)
      expect(!JSON.stringify(listed).includes("e2e-password"), "the password is sent back")
      await open("/settings/integrations")
      await has("Connected")
      await click("Other mail (IMAP), Connected")
      await has(`Reading ${ADDRESS}`)
      await click("Stop reading")
      for (let i = 0; i < 40 && (await q("mail_app_accounts")).length; i++) await new Promise((r) => setTimeout(r, 250))
      expect((await q("mail_app_accounts")).length === 0, "Stop reading didn't forget it on the server")
      expect(!readFileSync(secrets, "utf8").includes(ADDRESS), "secrets.toml still has it")
      await open("/settings/integrations")
      await type("Search integrations", "imap")
      expect(await until(`!!document.querySelector('[aria-label="Other mail (IMAP)"]')`), "its box still says it's connected")
    },
  },
  {
    // 24 Nov, found writing this test: mail_app_forget (like mail_app_set and token_add) is an unlogged command, and
    // the server announces only logged ones (server/app.py execute → announce); the page refreshes itself only when
    // the live stream is down (hooks/useCommand.ts). So Stop reading forgets the mailbox, but its panel still says
    // "Reading …" with its Stop reading button until the page is read again.
    name: "Stop reading takes the mailbox off its panel at once (fixed 24 Nov)",
    async run({ open, click, has, until, folder, expect }) {
      writeFileSync(path.join(folder, "secrets.toml"), `[mail_app]\nprovider = "other"\naddress = "${ADDRESS}"\npassword = "x"\nhost = "${HOST}"\n`)
      await open("/settings/integrations")
      await click("Other mail (IMAP), Connected")
      await has(`Reading ${ADDRESS}`)
      await click("Stop reading")
      expect(await until(`!document.body.innerText.includes(${JSON.stringify(`Reading ${ADDRESS}`)})`), "still says it's reading")
    },
  },
]
