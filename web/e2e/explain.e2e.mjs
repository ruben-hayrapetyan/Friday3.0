// Why the plan is as it is (tests/features.toml: explain), on the plan: a block's card says why it's there (why);
// Try elsewhere offers the cheapest other place, rule by rule, and Move there moves it (why_not), its History
// saying so; What changed lists what the last replan did after a change (changes); work that can't all fit says how
// late and what could give (triage), and a day over your usual offers ways to lighten it (lighten). Checked on the
// page against the server's answers.

const MEALS = /^(Breakfast|Lunch|Dinner)$/
const settle = async (check, what, ms = 30_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const local = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`

/** A block of work coming up that's on the page, opened in its card. */
const openBlock = async ({ q, evaluate, has }, wanted = () => true) => {
  for (const b of (await q("plan")).blocks) {
    if (b.pinned || b.fixed || b.background || MEALS.test(b.title) || new Date(b.start) < new Date(Date.now() + 3_600_000) || !(await wanted(b))) continue
    if (!(await evaluate(`!!document.querySelector('[data-block-key="${b.key}"]')`))) continue
    await evaluate(`document.querySelector('[data-block-key="${b.key}"]').click()`)
    await has(b.title, ".fr-block-card")
    return b
  }
  throw new Error("no block of work coming up on the page")
}

export default [
  {
    name: "a block's card says why it's there, as the server says it",
    async run(t) {
      const { open, has, q, planned } = t
      await planned()
      await open("/")
      const b = await openBlock(t)
      const why = await q("why", { key: b.key })
      await has(why.sentence, ".fr-block-card")
    },
  },
  {
    name: "Try elsewhere offers the cheapest other place; Move there moves it, and History says it was pinned",
    async run(t) {
      const { open, click, has, q, c, planned, expect } = t
      await planned()
      await open("/")
      const b = await openBlock(t, async (x) => !!(await q("why_not", { key: x.key })).to_start)
      const where = await q("why_not", { key: b.key })
      await click("Try elsewhere")
      await has(where.total > 0 ? "points more:" : "costs no more.", ".fr-block-card")
      await click("Move there")
      await settle(async () => (await q("plan")).blocks.some((x) => x.item_id === b.item_id && x.pinned === "preferred" && x.start === where.to_start), `${b.title} moved to ${where.to_start}`)
      await planned()
      await open("/")
      const moved = (await q("plan")).blocks.find((x) => x.item_id === b.item_id && x.start === where.to_start)
      expect(moved, "the moved block isn't in the plan")
      await t.evaluate(`document.querySelector('[data-block-key="${moved.key}"]')?.click()`)
      await has(b.title, ".fr-block-card")
      await click("History")
      await has("Pinned · You", ".fr-block-card")
      await c("unpin", { id: b.item_id })
    },
  },
  {
    name: "What changed lists what the replan after a change did",
    async run({ open, click, has, q, c, planned, day, expect }) {
      const made = (await c("add", { title: "E2E changed essay", duration_min: 90, due: `${day(3)}T17:00` })).result.item
      try {
        await planned()
        const changes = await q("changes")
        expect(changes.added.some((b) => b.item_id === made.id), "the server's changes don't list the essay added")
        await open("/")
        await click("Plan…")
        await click("What changed")
        await has("What changed", "[role=dialog]")
        await has("E2E changed essay", "[role=dialog]")
      } finally {
        await c("drop", { id: made.id })
      }
    },
  },
  {
    name: "work that can't all fit says how late it will be and what could give, as the server worked out",
    async run({ open, click, has, until, q, c, planned, evaluate }) {
      const due = new Date(Date.now() + 26 * 3_600_000)
      const made = (await c("add", { title: "E2E huge essay", duration_min: 16 * 60, firmness: "hard", due: local(due) })).result.item
      try {
        await planned()
        await settle(async () => (await q("status")).late_items.some((i) => i.item_id === made.id), "the essay late", 90_000)
        const triage = await q("triage")
        const late = Object.values(triage.late).reduce((s, h) => s + h, 0)
        await open("/")
        await has("E2E huge essay will be late", "[data-tour=attention]")
        await evaluate(`document.querySelector("[data-tour=attention]").click()`) // the line saying it, opened
        await click("See options")
        await has(`${late.toFixed(1)} h of work won’t make it`, "[role=dialog]", 60_000)
        await has("E2E huge essay", "[role=dialog]")
        for (const o of triage.options.slice(0, 3)) await has(o.action, "[role=dialog]")
        await click("Close")
      } finally {
        await c("drop", { id: made.id })
      }
    },
  },
  {
    name: "a day over your usual hours offers ways to lighten it, each tried on a copy of the plan",
    async run({ open, click, has, until, q, c, planned, evaluate, day, expect }) {
      const date = day(1)
      // a free hour that day, between what's fixed and what's planned, for an hour of work locked there
      const plan = await q("plan", { start: `${date}T00:00`, end: `${day(2)}T00:00` })
      const minutes = (t) => Number(t.slice(11, 13)) * 60 + Number(t.slice(14, 16))
      const taken = [...plan.fixed, ...plan.blocks].map((x) => [minutes(x.start), minutes(x.end)]).sort((a, b) => a[0] - b[0])
      let at = 8 * 60 // with half an hour clear on each side: a lock over an event or its buffer isn't kept
      for (const [from, to] of taken) {
        if (from >= at + 90) break
        at = Math.max(at, Math.ceil((to + 30) / 15) * 15)
      }
      const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
      const lower = await c("day_override", { date, cap_hours: 0.5 }) // that day's most work: half an hour
      const made = (await c("add", { title: "E2E long day", duration_min: 60, due: `${day(6)}T17:00` })).result.item
      try {
        await c("pin", { id: made.id, start: `${date}T${hhmm(at)}`, end: `${date}T${hhmm(at + 60)}`, kind: "locked" })
        await planned()
        const kept = (await q("plan")).blocks.find((b) => b.item_id === made.id)
        expect(kept?.pinned === "locked" && kept.start === `${date}T${hhmm(at)}`, `the lock wasn't kept: ${JSON.stringify(kept)}`)
        const cap = (await q("calendar", { start: date, days: 1 })).days[0].cap_hours
        expect(cap === 0.5, `the day's usual is ${cap} h, not the half hour set`)
        await settle(async () => ((await q("plan")).day_hours[date] ?? 0) - cap > 0.05, `${date} planned over its ${cap} h`, 60_000)
        await open("/")
        if (!(await evaluate(`[...document.querySelectorAll("[data-block-key]")].some((b) => b.dataset.blockKey.includes("${date}"))`))) return console.log(`      (${date} isn't in this week's view: nothing to check)`)
        await until(`!!document.querySelector("[data-tour=attention]")`, 15_000, "the plan's notes")
        await evaluate(`document.querySelector("[data-tour=attention]").click()`) // its notes, opened: one says the day is over
        await has("past your usual")
        await click("Lighten that day")
        await has("planned now", "[role=dialog]")
        await until(`!document.querySelector("[role=dialog]")?.innerText.includes("Trying what could move")`, 90_000, "the ways worked out")
        const ways = await q("lighten", { start: date, days: 1 })
        if (ways.options.length) {
          await has(ways.options[0].action, "[role=dialog]")
          expect(!ways.options.some((o) => o.action.includes("E2E long day")), "a locked block is offered to move")
        } else await has("Nothing there can move out without being late", "[role=dialog]")
        await click("Cancel")
      } finally {
        await c("drop", { id: made.id })
        await c("undo", { command_id: lower.command_id })
      }
    },
  },
]
