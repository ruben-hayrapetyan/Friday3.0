// Repeats (tests/features.toml: series): one typed in To-do the way you'd say it, then found in Settings → Repeating
// with how often and when next; stopped and started with its switch, kept days apart and tagged from its row; one time
// skipped from its block on the calendar; deleted from its row; and an event made to repeat from its block. Every
// step checked on the page and on the server.

const TITLE = "E2E stretch"

const row = async (q, title = TITLE) => (await q("series_list")).find((r) => r.title === title)
const times = async (q, status = "todo", title = TITLE) => (await q("items", { status, text: title })).filter((i) => i.series_id !== null)

/** Until `check()` is truthy, within ten seconds. */
async function eventually(check, said, wait) {
  for (let end = Date.now() + 10_000; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited 10s for ${said}`)
  }
}

/** Clicks the element `selector` finds, once it's there. */
const tap = (until, selector) => until(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.scrollIntoView({ block: "center" }); el.click(); return true })()`, 10_000, selector)

/** The text of the Repeating row whose title is `title`. */
const rowText = (until, title) =>
  until(`(() => { const b = [...document.querySelectorAll("[role=switch]")].find((s) => s.getAttribute("aria-label")?.endsWith(${JSON.stringify(` ${title}`)})); return b ? b.closest(".fr-row").innerText.replace(/\\s+/g, " ") : false })()`, 10_000, `the row of ${title}`)

export default [
  {
    name: "a repeat typed in To-do is made, and Settings → Repeating lists it with how often, when next and who added it",
    async run({ open, type, has, until, q, planned, expect, wait }) {
      await open("/todo")
      await type("Add", `${TITLE} every day ~45m`, { enter: true })
      await has(TITLE)
      const found = await eventually(() => row(q), "the repeat on the server", wait)
      expect(found.rule === "FREQ=DAILY" && found.active && !found.fixed && found.source === "you", `read as ${JSON.stringify(found)}`)
      const made = await times(q)
      expect(made.length > 5 && made.every((i) => i.duration_min === 45), `its times: ${made.length}, ${made[0]?.duration_min} min`)
      await planned()
      await open("/settings/repeating")
      await has("Habits and routines")
      const text = await rowText(until, TITLE)
      expect(text.includes(found.pattern), `the row says "${text}", not "${found.pattern}"`)
      expect(text.includes("Added by you") && text.includes("Next "), `the row says "${text}"`)
    },
  },
  {
    name: "its switch stops it (its times go) and starts it again (they're back)",
    async run({ open, click, until, q, expect, wait }) {
      await open("/settings/repeating")
      await click(`Stop ${TITLE}`)
      await eventually(async () => (await row(q)).active === false, "it stopped on the server", wait)
      expect((await times(q)).length === 0, "its times are still to do")
      await until(`[...document.querySelectorAll("[role=switch]")].some((s) => s.getAttribute("aria-label") === "Start ${TITLE}")`, 10_000, "the switch says Start")
      expect((await rowText(until, TITLE)).includes("Stopped"), "the row doesn't say Stopped")
      await click(`Start ${TITLE}`)
      await eventually(async () => (await row(q)).active === true, "it started on the server", wait)
      expect((await times(q)).length > 5, "its times didn't come back")
      await until(`!(document.querySelector('[aria-label="Start ${TITLE}"]'))`, 10_000, "the switch says Stop")
    },
  },
  {
    name: "from its row: kept 3 days apart, and tagged",
    async run({ open, click, has, until, q, c, expect, wait }) {
      await c("area_add", { name: "E2E Fitness" })
      await open("/settings/repeating")
      await click(`Days between ${TITLE}`)
      await click("at least 3 days after the last time")
      await eventually(async () => (await row(q)).min_gap_days === 3, "3 days apart on the server", wait)
      await has("at least 3 days after the last time")
      await click(`Tag for ${TITLE}`)
      await click("E2E Fitness")
      await eventually(async () => (await row(q)).area === "E2E Fitness", "the tag on the server", wait)
      const tagged = await times(q)
      expect(tagged.length && tagged.every((i) => i.area === "E2E Fitness"), "its times aren't tagged")
      expect((await q("series_list")).filter((r) => r.title === TITLE).length === 1, "retagging split the repeat in two")
      await until(`[...document.querySelectorAll('[aria-label="Tag for ${TITLE}"]')].some((m) => m.innerText.includes("E2E Fitness"))`, 15_000, "the row showing its tag")
    },
  },
  {
    name: "one time skipped from its block on the calendar; the others stay",
    async run({ open, click, has, until, q, planned, day, expect, wait }) {
      await planned()
      const ids = new Set((await times(q)).map((i) => i.id))
      const plan = await q("plan", { start: `${day(-1)}T04:00`, end: `${day(8)}T04:00` })
      const blocks = plan.blocks.filter((b) => ids.has(b.item_id))
      expect(blocks.length, "none of its times are planned")
      await open("/")
      // the first of its blocks the calendar shows
      const key = await until(`(${JSON.stringify(blocks.map((b) => b.key))}).find((k) => document.querySelector('[data-block-key="' + k + '"]')) || false`, 10_000, "one of its blocks on the calendar")
      const block = blocks.find((b) => b.key === key)
      await tap(until, `[data-block-key="${key}"]`)
      await has("Skipping leaves the others as they are.")
      await click("Skip this one")
      await eventually(async () => (await q("item", { id: block.item_id })).item.status === "skipped", "it skipped on the server", wait)
      expect((await times(q)).length === ids.size - 1, "more than one time went")
      await planned()
      await until(`!document.querySelector('[data-block-key="${key}"]')`, 10_000, "its block gone from the calendar")
    },
  },
  {
    name: "deleted from its row: gone from Repeating, and its times go",
    async run({ open, click, until, q, expect, wait }) {
      await open("/settings/repeating")
      await rowText(until, TITLE)
      await click(`Delete ${TITLE}`)
      await eventually(async () => !(await row(q)), "it gone from the server", wait)
      expect((await times(q)).length === 0 && (await q("items", { text: TITLE })).length === 0, "its times are still to do")
      await until(`!document.querySelector('[aria-label="Stop ${TITLE}"]')`, 10_000, "its row gone")
    },
  },
  {
    name: "an event made to repeat every week from its block on the calendar",
    async run({ open, click, has, until, q, c, planned, day, expect, wait }) {
      const on = new Date().getHours() < 4 ? day(0) : day(1)
      const made = await c("add", { title: "E2E salsa", when: "fixed", start: `${on}T20:00`, end: `${on}T21:00` })
      const id = made.result.item.id
      await planned()
      await open("/")
      await tap(until, `[data-block-key="F${id}"]`)
      await click("Repeats")
      await click("Every week on")
      await eventually(async () => (await q("item", { id })).item.series_id !== null, "it repeats on the server", wait)
      const later = new Date(`${on}T12:00`)
      later.setDate(later.getDate() + 7)
      const next = `${later.getFullYear()}-${String(later.getMonth() + 1).padStart(2, "0")}-${String(later.getDate()).padStart(2, "0")}`
      const plan = await q("plan", { start: `${next}T04:00`, end: `${next}T23:59` })
      expect(plan.fixed.some((f) => f.title === "E2E salsa" && f.start === `${next}T20:00`), `no E2E salsa a week on (${next})`)
      const listed = await row(q, "E2E salsa")
      expect(listed && listed.fixed && listed.rule.startsWith("FREQ=WEEKLY"), `Repeating has ${JSON.stringify(listed)}`)
      await open("/settings/repeating")
      await has("Classes and commitments")
      await rowText(until, "E2E salsa")
      await c("series_delete", { id: listed.id })
    },
  },
]
