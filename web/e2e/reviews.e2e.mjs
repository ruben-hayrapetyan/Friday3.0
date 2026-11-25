// Looking back (tests/features.toml: reviews): Insights → This week says the week as the server has it (week_review):
// what you finished, the hours worked of those planned, where the time went; how the week felt and a note for next
// Sunday are kept with the week (week_note) and shown again; the morning brief says today as the server does
// (brief); the Inbox asks about each block of a past day nobody said anything about (review). Checked on the page
// against the server.

const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}

export default [
  {
    name: "This week says what you finished, the hours worked of those planned, and where the time went",
    async run({ open, has, q, day, expect }) {
      const week = await q("week_review", { date: day(0) })
      const planned = week.areas.reduce((s, a) => s + a.planned_h, 0)
      const actual = week.areas.reduce((s, a) => s + a.actual_h, 0)
      await open("/insights?tab=week")
      await has("Week of")
      const n = (week.finished ?? []).length
      await has(`You finished ${n} ${n === 1 ? "thing" : "things"} and worked ${actual.toFixed(1)} of ${planned.toFixed(1)} planned hours.`)
      await has("Where the time went")
      for (const g of (week.groups ?? []).slice(0, 4)) await has(g.name)
      expect((week.groups ?? []).length > 0, "the sample's week has no time anywhere")
    },
  },
  {
    name: "how the week felt and a note for next Sunday are kept with the week, and shown again",
    async run({ open, click, type, has, until, q, day, evaluate, expect }) {
      const start = (await q("week_review", { date: day(0) })).start
      await open("/insights?tab=week")
      await has("Where the time went")
      await click("Good")
      await settle(async () => (await q("week_review", { date: day(0) })).note?.feel === "Good", "the feel kept on the server")
      await type("A note for next Sunday", "E2E: mornings worked, evenings didn't")
      await evaluate("document.activeElement.blur()")
      await settle(async () => (await q("week_review", { date: day(0) })).note?.notes === "E2E: mornings worked, evenings didn't", "the note kept on the server")
      const week = await q("week_review", { date: day(0) })
      expect(week.start === start, "the note went to another week")
      await open("/insights?tab=week")
      await until(`[...document.querySelectorAll("textarea")].some((t) => t.value === "E2E: mornings worked, evenings didn't")`, 10_000, "the note shown again")
      // the chosen feel is drawn apart from the others (its own background): Good's differs from Fine's
      const look = (f) => `getComputedStyle([...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "${f}")).backgroundColor`
      await until(`${look("Good")} !== ${look("Fine")} && ${look("Fine")} === ${look("Rough")}`, 10_000, "Good still chosen")
    },
  },
  {
    name: "the morning brief says today as the server does",
    async run({ open, click, has, q }) {
      const brief = await q("brief")
      await open("/")
      await click("Plan…")
      await click("Morning brief")
      await has("Good morning", "[role=dialog]")
      if (brief.summary) await has(brief.summary, "[role=dialog]")
      for (const r of brief.rocks.slice(0, 3)) await has(r.title, "[role=dialog]")
    },
  },
  {
    name: "the Inbox asks about each block of yesterday nobody said anything about",
    async run({ open, has, q, day, expect }) {
      const review = await q("review", { date: day(-1) })
      const asked = (review.gaps ?? []).filter((g) => !g.answer)
      if (!asked.length) return console.log("      (nothing of yesterday's waits for an answer: nothing to ask)")
      await open("/inbox")
      for (const g of asked) await has(g.title, "main")
      expect(review.date === day(-1), `the review is of ${review.date}`)
    },
  },
]
