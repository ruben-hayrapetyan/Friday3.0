// The plan on the calendar (tests/features.toml: plan_view): the Plan page draws the server's plan (its blocks and
// events this week); empty time dragged over offers Show what fits, which lists what the server says fits that long,
// and one picked is pinned there; Search finds events as the server's `events` does; Pace in the Plan menu says the
// pace in use and lists the saved ones.

const waitFor = async (check, ms = 15_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) {
    const found = await check()
    if (found) return found
  }
  return null
}

/** "1h 15m", "45m", "2h" as minutes. */
const minutesOf = (said) => {
  const h = said.match(/(\d+)h/)
  const m = said.match(/(\d+)m/)
  return (h ? Number(h[1]) * 60 : 0) + (m ? Number(m[1]) : 0)
}

/** Drags with the mouse over a free stretch of `date`'s column, `px` tall: the selection of empty time. */
async function selectEmpty({ page, until, wait }, date, px = 40) {
  const at = await until(`(() => {
    const day = Math.round(new Date("${date}T00:00:00Z").getTime() / 86400000)
    const col = [...document.querySelectorAll("[data-tour=calendar] [data-top-min]")].find((c) => Math.floor(Number(c.dataset.topMin) / 1440) === day)
    if (!col) return null
    col.scrollIntoView({ block: "nearest" })
    const r = col.getBoundingClientRect()
    const top = Math.max(r.top, 140), bottom = Math.min(r.bottom, innerHeight - 140)
    const taken = [...col.querySelectorAll("*")].map((e) => e.getBoundingClientRect()).filter((b) => b.height > 0 && b.width > 0 && b.height < r.height * 0.7).map((b) => [b.top - 3, b.bottom + 3])
    for (let y = top + 10; y + ${px} < bottom; y += 6) if (!taken.some(([a, b]) => a < y + ${px} && b > y)) return { x: r.left + r.width / 2, y }
    return null
  })()`, 3000, `a free stretch on ${date}`).catch(() => null)
  if (!at) return false
  const mouse = (type, y, buttons = 1) => page("Input.dispatchMouseEvent", { type, x: at.x, y, button: "left", buttons, clickCount: 1 })
  await mouse("mouseMoved", at.y, 0)
  await mouse("mousePressed", at.y)
  for (let step = 1; step <= 6; step++) await mouse("mouseMoved", at.y + (px * step) / 6)
  await mouse("mouseReleased", at.y + px, 0)
  await wait(300)
  return true
}

export default [
  {
    name: "the Plan page draws this week's blocks and events as the server plans them",
    async run({ open, has, text, q, day, expect, planned }) {
      await planned()
      const plan = await q("plan", { start: `${day(0)}T00:00`, end: `${day(2)}T00:00` })
      const blocks = plan.blocks.filter((b) => !b.background && b.end > new Date().toISOString())
      expect(blocks.length > 0, "nothing planned today or tomorrow")
      await open("/")
      await has(blocks[0].title, "[data-tour=calendar]")
      const page = await text("[data-tour=calendar]")
      const missing = [...new Set(blocks.map((b) => b.title))].filter((t) => !page.includes(t.slice(0, 12)))
      expect(!missing.length, `planned but not drawn: ${missing.join(", ")}`)
      const events = plan.fixed.filter((e) => !e.background && e.start >= `${day(0)}T00:00` && e.start < `${day(2)}T00:00`)
      const gone = [...new Set(events.map((e) => e.title))].filter((t) => !page.includes(t.slice(0, 12)))
      expect(!gone.length, `events not drawn: ${gone.join(", ")}`)
    },
  },
  {
    name: "empty time dragged over offers Show what fits: the server's list for that long; one picked is pinned there",
    async run(t) {
      const { open, click, has, until, q, c, day, expect } = t
      await open("/")
      await has("Plan", "[data-tour=calendar]").catch(() => {})
      let date
      for (let n = 1; n <= 6 && !date; n++) if (await selectEmpty(t, day(n))) date = day(n)
      expect(date, "no free stretch drawn this week")
      await has("Show what fits")
      const head = await until(`[...document.querySelectorAll(".fr-float .fr-kicker")].map((k) => k.innerText).find((s) => s.includes("·"))`, 5000, "the selection's time")
      const minutes = minutesOf(head.split("·")[1])
      expect(minutes >= 30 && minutes <= 75, `selected ${head}`)
      await click("Show what fits")
      const fits = await q("fits", { minutes })
      if (!fits.length) return await has("Nothing fits without something going late.")
      await has(fits[0].title, ".fr-float")
      const shown = await until(`[...[...document.querySelectorAll(".fr-float")].find((f) => [...f.querySelectorAll(":scope > .fr-kicker")].some((k) => k.innerText.includes("·")))?.querySelectorAll("button") ?? []].map((b) => b.innerText.replace(/\\s+/g, " ").trim())`)
      expect(shown.length === fits.length, `shown ${shown.length}, the server's ${fits.length}`)
      fits.forEach((f, i) => expect(shown[i].startsWith(f.title), `${i}: "${shown[i]}" isn't ${f.title}`))
      const before = (await q("log_list", { limit: 1 }))[0]?.id ?? 0
      // the one in the menu, not the calendar's block of the same name
      await until(`(() => { const f = [...document.querySelectorAll(".fr-float")].find((f) => [...f.querySelectorAll(":scope > .fr-kicker")].some((k) => k.innerText.includes("·"))); const b = f && [...f.querySelectorAll("button")].find((b) => b.innerText.trim().startsWith(${JSON.stringify(fits[0].title)})); return b ? (b.click(), true) : false })()`, 5000, `${fits[0].title} in the menu`)
      const pin = await waitFor(async () => (await q("log_list", { limit: 5 })).find((e) => e.command === "pin" && e.id > before))
      expect(pin?.input.id === fits[0].item_id && pin.input.kind === "preferred", `pinned ${JSON.stringify(pin?.input)}`)
      expect(pin.input.start.startsWith(date), `pinned at ${pin.input.start}, not on ${date}`)
      const block = await waitFor(async () => (await q("plan", { start: `${date}T00:00`, end: `${date}T23:59` })).blocks.find((b) => b.item_id === fits[0].item_id && b.pinned === "preferred" && b.start >= pin.input.start && b.end <= pin.input.end), 120_000)
      // a preferred pin: the block lands inside the time picked (its length may be what's left of it)
      expect(block, `no block of ${fits[0].title} pinned within ${pin.input.start}–${pin.input.end}`)
      await c("undo", { command_id: pin.id })
    },
  },
  {
    name: "Search finds events by their words, as the server's events does",
    async run({ open, click, type, has, text, q, expect }) {
      const word = (await q("plan")).fixed.find((e) => e.title.length > 6 && !e.background)?.title.split(" ")[0]
      expect(word, "no event ahead to search for")
      const events = await q("events", { text: word, limit: 8 })
      expect(events.length > 0 && events.every((e) => e.title.toLowerCase().includes(word.toLowerCase())), `events for ${word}: ${JSON.stringify(events.map((e) => e.title))}`)
      await open("/")
      await click("Search (⌘K)")
      await type("Search", word)
      await has("Events", "[aria-label=Search][role=dialog]")
      const shown = await text("[aria-label=Search][role=dialog]")
      for (const e of events) expect(shown.includes(e.title), `${e.title} isn't found`)
      expect((await q("events", { text: "" })).length === 0, "no words finds events")
    },
  },
  {
    name: "Pace in the Plan menu says the pace in use and lists the saved paces",
    async run({ open, click, has, q, expect }) {
      const paces = await q("paces")
      expect(paces.paces[paces.now_label] || paces.now_label, "no pace in use")
      await open("/")
      await click("Plan…")
      await has("Pace")
      await click("Pace")
      for (const name of Object.keys(paces.paces)) await has(name)
      await has(paces.now_label)
    },
  },
]
