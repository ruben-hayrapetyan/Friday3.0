// Shove (tests/features.toml: shove): taking time back from the Plan menu and with S, as a person would; work that
// would then go late listed, gone Back from, kept, or shoved anyway; the Shoved panel's Undo; and a shove given back
// from its block on the calendar. Every step checked on the page and on the server (the shove's event, the plan).

const hour = () => new Date().getHours()
/** Friday's tomorrow (its day starts at 4am: before then, tomorrow is the calendar's today). */
const tomorrow = (day) => (hour() < 4 ? day(0) : day(1))

/** The shoves on the server from yesterday to three days on. */
async function shoves(q, day) {
  const plan = await q("plan", { start: `${day(-1)}T04:00`, end: `${day(3)}T04:00` })
  return plan.fixed.filter((f) => f.event_kind === "shove")
}

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

/** Clicks the element `selector` finds, once it's there. */
const press = (until, selector) => until(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true })()`, 10_000, selector)

export default [
  {
    name: "from the Plan menu, tomorrow evening is shoved: the server has it, work moves out, and the panel's Undo takes it back",
    async run({ open, click, has, until, q, planned, day, expect, wait }) {
      await planned()
      const before = (await shoves(q, day)).length
      await open("/")
      await click("Plan…")
      await click("Shove")
      await has("Shove: take time back")
      await click("Evening")
      const shown = await until(`(() => { const t = document.body.innerText; return t.includes("This time holds work that would then be late") ? "late" : t.includes("It’s yours now") ? "shoved" : false })()`, 60_000, "the shove's answer")
      if (shown === "late") await click("Shove anyway")
      await has("It’s yours now, striped on the calendar.")
      const on = tomorrow(day)
      const made = await eventually(async () => (await shoves(q, day)).find((s) => s.start === `${on}T17:00` && s.end === `${on}T22:00`), 10_000, "the shove on the server", wait)
      expect(made, "no 5–10pm shove tomorrow on the server")
      expect((await shoves(q, day)).length === before + 1, "more than one shove was made")
      await has("5–10pm")
      // the panel's Undo, before it closes on its own
      await click("Undo")
      await eventually(async () => !(await shoves(q, day)).some((s) => s.id === made.id), 10_000, "the shove gone", wait)
      // and shoved again, the plan keeps work out of it
      await open("/")
      await click("Plan…")
      await click("Shove")
      await click("Evening")
      const again = await until(`(() => { const t = document.body.innerText; return t.includes("This time holds work that would then be late") ? "late" : t.includes("It’s yours now") ? "shoved" : false })()`, 60_000, "the shove's answer")
      if (again === "late") await click("Shove anyway")
      await has("It’s yours now")
      await planned()
      const plan = await q("plan", { start: `${on}T04:00`, end: `${day(hour() < 4 ? 1 : 2)}T04:00` })
      const inside = plan.blocks.filter((b) => !b.fixed && b.start < `${on}T22:00` && b.end > `${on}T17:00`)
      expect(inside.length === 0, `work still planned in the shoved evening: ${inside.map((b) => `${b.title} ${b.start}`).join(", ")}`)
    },
  },
  {
    name: "with S: work that would go late is listed; Back changes nothing, Keep must-dos keeps its time and shoves the rest",
    async run({ open, click, has, until, q, c, planned, day, expect, press: key }) {
      const on = tomorrow(day)
      const next = hour() < 4 ? day(1) : day(2)
      // hard work that can only be done tomorrow: shoving the whole day would make it late
      const made = await c("add", { title: "E2E shove: lab report", duration_min: 240, firmness: "hard", release: `${on}T04:00`, due: `${on}T23:00` })
      const id = made.result.item.id
      await planned()
      const before = (await shoves(q, day)).filter((s) => s.start.startsWith(on)).length
      await open("/")
      await key("s")
      await has("Shove: take time back")
      await click("All day")
      await has("This time holds work that would then be late:", "body", 60_000)
      await has("E2E shove: lab report")
      await until(`/\\+[\\d.]+ h late/.test(document.body.innerText)`, 5_000, "how late it would be")
      await click("Back")
      await has("Quick")
      expect((await shoves(q, day)).filter((s) => s.start.startsWith(on)).length === before, "Back still shoved")
      await click("All day")
      await has("Keep must-dos", "body", 60_000)
      await click("Keep must-dos")
      await has("It’s yours now")
      await planned()
      const plan = await q("plan", { start: `${on}T04:00`, end: `${next}T04:00` })
      const kept = plan.blocks.filter((b) => b.item_id === id)
      expect(kept.length > 0 && kept.every((b) => b.pinned === "locked"), `its time isn't kept locked: ${JSON.stringify(kept)}`)
      const mine = (await shoves(q, day)).filter((s) => s.start >= `${on}T04:00` && s.start < `${next}T04:00`)
      expect(mine.length > before, "nothing was shoved")
      for (const s of mine)
        for (const b of kept) expect(!(s.start < b.end && s.end > b.start), `a shove ${s.start}–${s.end} covers the kept ${b.start}–${b.end}`)
      const other = plan.blocks.filter((b) => !b.fixed && b.item_id !== id && mine.some((s) => b.start < s.end && b.end > s.start))
      expect(other.length === 0, `other work in the shoved time: ${other.map((b) => b.title).join(", ")}`)
      // tidy: the day back for the tests after
      for (const s of mine) await c("unshove", { id: s.id })
      await c("drop", { id })
    },
  },
  {
    name: "a shove's block on the calendar opens with Give it back, which gives the time back to the plan",
    async run({ open, click, has, until, q, c, planned, day, expect, wait }) {
      const out = await c("shove", { range: "1h", decision: "shove_anyway" })
      const [id] = out.result.created
      expect(id, "the shove made nothing")
      await planned()
      await open("/")
      await press(until, `[data-block-key="F${id}"]`)
      await has("Give it back")
      await click("Give it back")
      await eventually(async () => !(await shoves(q, day)).some((s) => s.id === id), 10_000, "the shove gone from the server", wait)
      await until(`!document.querySelector('[data-block-key="F${id}"]')`, 10_000, "the shove gone from the calendar")
    },
  },
]
