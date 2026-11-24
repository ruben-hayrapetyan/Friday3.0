// The mail log (tests/features.toml: mail): Settings → Integrations, the Google box's Gmail card lists the mail Friday
// saw in Alex's sample, read or skipped and why, with the counts; "Read it anyway" on a skipped newsletter sends it to
// be read on the next sync, and the server's next reading of the mail reads it. Checked on the page and the server.

const limit = (ms, run) => async (t) => {
  let timer
  const late = new Promise((_, fail) => (timer = setTimeout(() => fail(new Error(`the test took over ${ms / 1000}s`)), ms)))
  try {
    return await Promise.race([run(t), late])
  } finally {
    clearTimeout(timer)
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function eventually(check, ms, said) {
  for (let end = Date.now() + ms; ; await sleep(1000)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const PANEL = '[role=dialog][aria-label="Google Calendar"]'

async function openLog({ open, until, has }) {
  await open("/settings/integrations")
  await until(`(() => { const b = document.querySelector('[data-integration="google"]'); if (!b) return false; b.click(); return true })()`, 15_000, "the Google box")
  await has("Recent mail ·", PANEL, 15_000)
}

/** The log's row for `subject`: its words, or presses its button. */
const row = (subject) => `[...document.querySelectorAll('${PANEL} .fr-row')].find((r) => r.innerText.includes(${JSON.stringify(subject)}) && r.querySelector("span span"))`

const mailLog = (q) => q("mail_log", { limit: 60 })
const shared = {}

export default [
  {
    name: "the log counts the mail as the server has it and shows each with why it was skipped",
    run: limit(90_000, async (t) => {
      const { text, until, q, expect } = t
      const mail = await mailLog(q)
      expect(mail.some((m) => m.status === "read") && mail.some((m) => m.status === "skipped"), "the sample has no read and skipped mail")
      await openLog(t)
      const said = await text(PANEL)
      const counts = ["read", "skipped", "failed", "waiting"].map((k) => [k, mail.filter((m) => m.status === k).length]).filter(([, n]) => n)
      const want = `Recent mail · ${counts.map(([k, n]) => `${n} ${k}`).join(", ")}`
      expect(said.includes(want), `the log doesn't say "${want}": ${said.slice(0, 400)}`)
      for (const m of mail.slice(0, 8)) expect(said.includes(m.subject), `${m.subject} isn't in the log`)
      shared.skipped = mail.slice(0, 8).find((m) => m.status === "skipped")
      expect(shared.skipped, "no skipped mail among the eight shown")
      const line = await until(`${row(shared.skipped.subject)}?.innerText`, 5_000)
      expect(line.startsWith("Skipped") && line.includes(shared.skipped.why) && line.includes("Read it anyway"), `the row says: ${line}`)
      const found = mail.slice(0, 8).find((m) => m.status === "read" && m.found)
      if (found) {
        const read = await until(`${row(found.subject)}?.innerText`, 5_000)
        expect(read.includes(`${found.found} suggested`) && !read.includes("Read it"), `a read message with suggestions says: ${read}`)
      }
    }),
  },
  {
    name: "Read it anyway on a skipped message: the server reads it on its next reading of the mail",
    run: limit(240_000, async (t) => {
      const { until, q, open, has, expect } = t
      const m = shared.skipped
      await openLog(t)
      await until(`(() => { const b = [...(${row(m.subject)}?.querySelectorAll("button") ?? [])].find((b) => b.textContent.trim() === "Read it anyway"); if (!b) return false; b.click(); return true })()`, 10_000, `Read it anyway beside ${m.subject}`)
      await has("It's read on the next sync, with its PDFs")
      const queued = (await mailLog(q)).find((x) => x.id === m.id)
      expect(queued.why !== m.why && /PDFs/.test(queued.why ?? ""), `the server didn't queue it: ${JSON.stringify(queued)}`)
      await eventually(async () => (await mailLog(q)).find((x) => x.id === m.id)?.status === "read", 200_000, `${m.subject} read by the next sync`)
      await open("/settings/integrations")
      await openLog(t)
      const line = await until(`${row(m.subject)}?.innerText`, 5_000)
      expect(line.startsWith("Read") && !line.includes("Read it anyway"), `after its reading the row says: ${line}`)
    }),
  },
]
