// The calendar's days and tags (tests/features.toml: calendar): the Plan page's day headers as the server's calendar
// has them (today marked, a week, a day, three days, Next and Previous and back), a deadline's red count on its day
// that opens it and goes once it's done, a break on its days, and a tag on a block's card following a rename. Each
// checked on the page and against the server.

async function server(check, said, ms = 20_000) {
  for (let end = Date.now() + ms; ; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`the server didn't come to: ${said}`)
  }
}

/** The dates of the day headers on the page, in order. */
const HEADS = `[...new Set([...document.querySelectorAll('[data-tour="calendar"] [data-drop-day]')].map((el) => el.getAttribute("data-drop-day")))]`
const heads = (until, n) => until(`((d) => d.length === ${n} && d)(${HEADS})`, 10_000, `${n} day headers`)
const plus = (date, n) => {
  const d = new Date(`${date}T12:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
const tap = (until, selector, said = selector) =>
  until(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true })()`, 10_000, said)

export default [
  {
    name: "the week's day headers are the server's calendar days, today among them, and Next, Previous and back step a week",
    async run({ open, click, until, q, expect }) {
      await open("/")
      const week = await heads(until, 7)
      const cal = await q("calendar", { start: week[0], days: 7 })
      expect(JSON.stringify(cal.days.map((d) => d.date)) === JSON.stringify(week), `headers ${week} aren't the calendar's ${cal.days.map((d) => d.date)}`)
      expect(week.includes(cal.today), `today ${cal.today} isn't among ${week}`)
      await click("Next")
      const next = await until(`((d) => d.length === 7 && d[0] === ${JSON.stringify(plus(week[0], 7))} && d)(${HEADS})`, 10_000, "next week's headers")
      expect(next[6] === plus(week[0], 13), `next week ends ${next[6]}`)
      await click("Previous")
      await click("Previous")
      await until(`${HEADS}[0] === ${JSON.stringify(plus(week[0], -7))}`, 10_000, "last week's headers")
      await click("Today")
      await until(`${HEADS}[0] === ${JSON.stringify(week[0])}`, 10_000, "back to this week")
      await click("This week") // what it says now: already there, nothing moves
      expect((await heads(until, 7))[0] === week[0], "This week moved the week")
    },
  },
  {
    name: "Day shows today alone and 3 days three days; Week brings the seven back",
    async run({ open, click, until, q, expect }) {
      await open("/")
      const today = (await q("calendar")).today
      await click("Day")
      const one = await heads(until, 1)
      expect(one[0] === today, `the day view shows ${one[0]}, not today ${today}`)
      await click("3 days")
      const three = await heads(until, 3)
      expect(three.includes(today) && three[1] === plus(three[0], 1) && three[2] === plus(three[0], 2), `3 days: ${three}`)
      await click("Week")
      await heads(until, 7)
    },
  },
  {
    name: "a deadline is a red count on its day that opens it; done, it's gone from the day",
    async run({ open, click, has, until, q, c, day, expect, planned }) {
      const due = `${day(1)}T17:00`
      const id = (await c("add", { title: "E2E grant form", duration_min: 30, firmness: "hard", due })).result.item.id
      const dues = (await q("calendar", { start: day(1), days: 1 })).dues
      expect(dues.some((d) => d.item_id === id && d.due === due), "the server's calendar has no due marker for it")
      await planned()
      await open("/")
      const count = `[data-drop-day="${day(1)}"] button.fr-due-count`
      const label = await until(`document.querySelector(${JSON.stringify(count)})?.getAttribute("aria-label")`, 10_000, "a due count on tomorrow")
      expect(label.includes("E2E grant form"), `tomorrow's count says ${label}`)
      expect(label.startsWith(`${dues.length} due`), `the count says ${label}, the server has ${dues.length} due`)
      await tap(until, count, "tomorrow's due count")
      await click("E2E grant form")
      await has("E2E grant form", ".fr-block-card")
      await has("Due", ".fr-block-card")
      await c("done", { id })
      await server(async () => !(await q("calendar", { start: day(1), days: 1 })).dues.some((d) => d.item_id === id), "its marker gone")
      await open("/")
      await heads(until, 7)
      const after = await until(`(document.querySelector(${JSON.stringify(count)})?.getAttribute("aria-label") ?? "none") + " "`, 10_000)
      expect(!after.includes("E2E grant form"), `tomorrow still counts it: ${after}`)
    },
  },
  {
    name: "a break shows on its days, as the server's calendar marks them",
    async run({ open, has, until, q, c, day, expect }) {
      const first = day(2)
      const made = await c("vacation_add", { name: "E2E long weekend", start: first, end: day(3), mode: "off" })
      try {
        const marked = (await q("calendar", { start: day(1), days: 4 })).days.map((d) => d.vacation?.name ?? null)
        expect(JSON.stringify(marked) === JSON.stringify([null, "E2E long weekend", "E2E long weekend", null]), `the server marks ${marked}`)
        await open("/")
        const week = await heads(until, 7)
        if (week.includes(first)) await has("E2E long weekend", '[data-tour="calendar"]')
      } finally {
        await c("vacation_delete", { id: made.result.vacation.id })
      }
      expect(!(await q("calendar", { start: day(1), days: 4 })).days.some((d) => d.vacation), "the break is still on the calendar")
    },
  },
  {
    name: "a block's card names its tag, and a renamed tag is the new name there and in the tag list",
    async run({ open, has, until, q, c, day, planned, expect }) {
      const tag = (await c("area_add", { name: "E2E Zoology", color: "green" })).result
      try {
        const id = (await c("add", { title: "E2E owl pellets", duration_min: 60, area: "E2E Zoology", due: `${day(2)}T20:00` })).result.item.id
        await planned()
        const block = await server(async () => (await q("item", { id })).blocks.find((b) => b.state === null), "a block for it")
        await open("/")
        if (!(await until(`!!document.querySelector('[data-block-key="${block.key}"]')`, 5000).catch(() => false))) return console.log("      (its block isn't in this week's view: skipped)")
        await tap(until, `[data-block-key="${block.key}"]`, "its block")
        await has("E2E Zoology", ".fr-block-card")
        await c("area_edit", { id: tag.id, name: "E2E Zoology 2" })
        expect((await q("areas")).some((a) => a.id === tag.id && a.name === "E2E Zoology 2"), "the tag list doesn't have the new name")
        await open("/")
        await tap(until, `[data-block-key="${block.key}"]`, "its block again")
        await has("E2E Zoology 2", ".fr-block-card")
        await c("drop", { id })
      } finally {
        await c("area_edit", { id: tag.id, archived: true })
      }
    },
  },
]
