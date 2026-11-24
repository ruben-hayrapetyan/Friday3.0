// Late on paper, on time in practice (tests/features.toml: beat_plan): three problem sets every plan shows late (due
// in two hours, two and a half hours each, the two hours busy), finished on time in an hour each. Insights says how
// many of the things shown late you finished on time and how, with the server's numbers; its link goes to the
// Inbox's question, and answered there, the link goes.

const pad = (n) => String(n).padStart(2, "0")
const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(500)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

const SECTION = "Late on paper, on time in practice"

export default [
  {
    name: "work shown late and finished on time faster: Insights says how many and how, as the server has it",
    async run({ open, has, until, q, c, expect, wait }) {
      const now = new Date()
      now.setSeconds(0, 0)
      const due = local(new Date(now.getTime() + 2 * 3_600_000))
      const busy = await c("add", { title: "E2E beat: busy", when: "fixed", start: local(now), end: due })
      const ids = []
      for (const n of [1, 2, 3])
        ids.push((await c("add", { title: `E2E beat: problem set ${n}`, preset: "Assignment", duration_min: 150, firmness: "hard", due })).result.item.id)
      await c("replan")
      await eventually(async () => {
        const late = new Set((await q("status")).late_items.map((i) => i.item_id))
        return ids.every((id) => late.has(id))
      }, 180_000, "every plan to show them late", wait)
      const before = await q("beat_plan")
      for (const id of ids) await c("done", { id, actual_min: 60 })
      await c("drop", { id: busy.result.item.id })
      const out = await q("beat_plan")
      expect(out.on_time === before.on_time + 3, `on time: ${before.on_time} → ${out.on_time}`)
      const mine = out.finishes.filter((f) => ids.includes(f.item_id))
      expect(mine.length === 3 && mine.every((f) => f.ways.includes("faster") && f.speed === 0.4), `the finishes: ${JSON.stringify(mine)}`)
      await open("/insights?tab=trends")
      await has(SECTION, "body", 20_000)
      const all = out.on_time + out.late
      await has(`${out.on_time} of ${all} things your plans showed late you finished on time (${Math.round((out.on_time / all) * 100)}%).`)
      const chip = await until(`[...document.querySelectorAll(".fr-chip")].map((c) => c.innerText.replace(/\\s+/g, " ")).find((t) => t.startsWith("took less time than planned")) || false`, 10_000, "the faster chip")
      expect(chip.endsWith(String(out.counts.faster)), `the chip says "${chip}", the server ${out.counts.faster}`)
    },
  },
  {
    name: "its link opens the Inbox's question; answered there, Insights no longer points to it",
    async run({ open, click, has, until, q, expect, wait }) {
      const out = await q("beat_plan")
      const speed = out.asking.find((a) => a.startsWith("Assignment takes you about"))
      expect(speed, `nothing asked about Assignment's speed: ${JSON.stringify(out.asking)}`)
      await open("/insights?tab=trends")
      await has(SECTION, "body", 20_000)
      await click(out.asking.length === 1 ? "A question about it is waiting in the Inbox" : `${out.asking.length} questions about it are waiting in the Inbox`)
      await until(`location.hash.startsWith("#/inbox")`, 10_000, "the Inbox open")
      await has(speed)
      await until(`(() => { const row = [...document.querySelectorAll("[role=listitem]")].find((r) => r.innerText.includes(${JSON.stringify(speed)})); if (!row) return false; row.click(); return true })()`, 10_000, "its row")
      const pct = speed.match(/about (\d+)%/)[1]
      await click(`Plan Assignment at ${pct}% of its length`)
      await eventually(async () => !(await q("beat_plan")).asking.includes(speed), 10_000, "the question answered on the server", wait)
      const left = (await q("beat_plan")).asking.length
      await open("/insights?tab=trends")
      await has(SECTION, "body", 20_000)
      if (left === 0) await until(`!document.body.innerText.includes("waiting in the Inbox")`, 10_000, "the link gone")
      else await has(left === 1 ? "A question about it is waiting in the Inbox" : `${left} questions about it are waiting in the Inbox`)
    },
  },
]
