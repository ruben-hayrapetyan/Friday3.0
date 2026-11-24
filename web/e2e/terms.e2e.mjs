// Terms (tests/features.toml: terms): Friday stays locked on its terms until you press Accept; changed terms come back
// with what changed; Quit leaves your data; a version that changed while you read is refused and asked again. The
// sample has accepted them, so the page is told they're needed (`answer`); what Accept sends goes to the real server.

const latest = async (q, command) => (await q("log_list", { limit: 30 })).find((e) => e.command === command)

export default [
  {
    name: "terms not yet accepted lock Friday on them; Accept sends the version read and opens Friday",
    async run({ open, has, gone, click, text, q, answer, expect, until }) {
      const terms = await q("terms")
      expect(terms.needed === false && terms.accepted === terms.version, "the sample should have accepted the terms")
      await answer({ terms: { ...terms, accepted: null, needed: true } })
      const before = (await latest(q, "terms_accept"))?.id ?? 0
      await open("/")
      await has("Before you start, read Friday's terms and accept them to use Friday.")
      await has("1. Agreeing to these terms")
      const page = await text()
      expect(!page.includes("What changed"), "a first acceptance shows no list of changes")
      expect(await until(`!document.querySelector("[data-tour=now]") && !document.querySelector("nav")`, 2000), "the app shows behind the terms")
      await answer(null) // from here the page reads the server's own answer, as it would once accepted
      await click("Accept")
      await gone("Before you start, read Friday's terms")
      await until(`!!document.querySelector("nav, [data-tour]")`, 10_000, "the app after Accept")
      let sent
      for (let i = 0; i < 40 && !(sent = await latest(q, "terms_accept"))?.id; i++) await new Promise((r) => setTimeout(r, 250))
      for (let i = 0; i < 40 && sent.id <= before; i++) (await new Promise((r) => setTimeout(r, 250)), (sent = await latest(q, "terms_accept")))
      expect(sent.id > before, "Accept sent nothing to the server")
      expect(sent.input.version === terms.version, `Accept sent version ${sent.input.version}, not ${terms.version}`)
      expect((await q("terms")).needed === false, "the server still needs the terms accepted")
    },
  },
  {
    name: "changed terms say so and list what changed above the text",
    async run({ open, has, text, q, answer, expect }) {
      const terms = await q("terms")
      expect(terms.changes.length > 0, "the terms have no list of changes to show")
      await answer({ terms: { ...terms, accepted: "2026-11-01", needed: true } })
      await open("/")
      await has("Friday's terms have changed. Read what's new and accept them to keep using Friday.")
      await has("What changed")
      const page = await text()
      for (const change of terms.changes) expect(page.includes(change.replace(/\*/g, "").slice(0, 30)), `"${change}" isn't listed`)
      expect(page.includes("Version of 9 November 2026"), "the version isn't said as a date")
    },
  },
  {
    name: "Quit in a browser tab says the tab can be closed, and Friday stays locked",
    async run({ open, has, click, q, answer }) {
      const terms = await q("terms")
      await answer({ terms: { ...terms, accepted: null, needed: true } })
      await open("/")
      await has("Your data stays on your computer either way.")
      await click("Quit")
      await has("You can close this tab now. Your data stays on your computer.")
      await has("Before you start, read Friday's terms")
    },
  },
  {
    name: "terms that changed while open are refused by the server, and the page asks again",
    async run({ open, has, click, q, answer, request, expect, wait }) {
      const terms = await q("terms")
      const refused = await request("POST", "/api/c/terms_accept", { version: "2026-01-01" })
      expect(refused.status === 422 && refused.body.message.includes("changed while you were reading"), `the server took an old version: ${JSON.stringify(refused)}`)
      await answer({ terms: { ...terms, version: "2026-01-01", accepted: null, needed: true } })
      const before = (await latest(q, "terms_accept"))?.id ?? 0
      await open("/")
      await click("Accept")
      await wait(1500)
      await has("Before you start, read Friday's terms") // read again: still asked
      const after = (await latest(q, "terms_accept"))?.id ?? 0
      expect(after === before, "an old version was recorded as accepted")
      expect((await q("terms")).accepted === terms.version, "the real acceptance changed")
    },
  },
]
