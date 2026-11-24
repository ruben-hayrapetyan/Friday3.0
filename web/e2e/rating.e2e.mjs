// Events (tests/features.toml: rating): an event's card on the calendar, as a person uses it: going, working through
// it and skipping it; its time given to a to-do and freed; its category chosen and given back to Friday; an optional
// event kept and let go; and "Going" in What gives, so Friday stops offering to skip it. Each step checked on the page
// and on the server.

const TITLE = "E2E Salsa night"

/** Clicks the first element `selector` finds, once there is one. */
const tap = (until, selector, said = selector) =>
  until(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true })()`, 15_000, said)

/** Waits for the server to say what `check` wants. */
async function server(check, said, ms = 20_000) {
  for (let end = Date.now() + ms; ; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`the server didn't come to: ${said}`)
  }
}

/** Clicks the button in the open card whose words start with `label` (a block on the grid can have the same name). */
const inCard = (until, label) =>
  until(`(() => { const el = [...document.querySelectorAll(".fr-block-card button")].find((b) => b.textContent.trim().startsWith(${JSON.stringify(label)})); if (!el) return false; el.click(); return true })()`, 10_000, `"${label}" in the card`)

const today = async (q) => (await q("calendar")).today
const facts = async (q, id) => (await q("item", { id })).item
const checked = (label) => `[...document.querySelectorAll("[role=radio]")].find((el) => el.textContent.startsWith(${JSON.stringify(label)}))?.getAttribute("aria-checked") === "true"`

/** The plan page with `id`'s card open. */
async function card({ open, until, has }, id, title) {
  await open("/")
  await tap(until, `[data-block-key="F${id}"]`, `${title} on the calendar`)
  await has(title, ".fr-block-card")
}

async function event(c, q, title, start, end) {
  const d = await today(q)
  return (await c("add", { title, when: "fixed", start: `${d}T${start}`, end: `${d}T${end}` })).result.item.id
}

export default [
  {
    name: "an event's card: Work through it, Skip it and I'm going, each the server's at once and kept on the card",
    async run(t) {
      const { click, has, until, q, c, expect } = t
      const id = await event(c, q, TITLE, "14:00", "15:00")
      await card(t, id, TITLE)
      await has("Work through it", ".fr-block-card")
      expect(await until(checked("I'm going")), "a busy event isn't shown as going")
      await click("Work through it")
      await server(async () => (await facts(q, id)).left_out === "through", "worked through")
      await until(checked("Work through it"), 10_000, "Work through it chosen")
      await has("Any work Friday picks.", ".fr-block-card")
      await click("Skip it")
      await server(async () => (await facts(q, id)).left_out === "skipped", "skipped")
      await until(checked("Skip it"), 10_000, "Skip it chosen")
      await click("I'm going")
      await server(async () => (await facts(q, id)).left_out === null, "going")
      await until(checked("I'm going"), 10_000, "I'm going chosen")
      // and after a fresh load, the card reads it from the server
      await click("Work through it")
      await server(async () => (await facts(q, id)).left_out === "through", "worked through again")
      await card(t, id, TITLE)
      await until(checked("Work through it"), 10_000, "Work through it still chosen after a reload")
    },
  },
  {
    name: "working through it, the to-do its name suggests is asked about; Yes or another task gets its time, Any work lets it go",
    async run(t) {
      const { click, has, type, until, q, c, expect } = t
      const id = (await q("events", { text: TITLE }))[0].id
      const task = (await c("add", { title: "E2E Salsa playlist", duration_min: 30 })).result.item.id
      const other = (await c("add", { title: "E2E water the plants", duration_min: 15 })).result.item.id
      try {
        await card(t, id, TITLE)
        if (!(await until(checked("Work through it"), 3000).catch(() => false))) await click("Work through it")
        await has("Is this time for E2E Salsa playlist?", ".fr-block-card") // named like it
        await click("Another task")
        await type("Find a task", "E2E water")
        await inCard(until, "E2E water the plants")
        await server(async () => (await facts(q, id)).holds?.id === other, "its time held for the plants")
        await has("Time for E2E water the plants", ".fr-block-card")
        await click("Any work")
        await server(async () => (await facts(q, id)).holds === null, "the hold let go")
        await has("Is this time for E2E Salsa playlist?", ".fr-block-card")
        await click("Yes")
        await server(async () => (await facts(q, id)).holds?.id === task, "its time held for the playlist")
        await card(t, id, TITLE)
        await has("Time for E2E Salsa playlist", ".fr-block-card")
        await click("Any work")
        await server(async () => (await facts(q, id)).holds === null, "the hold let go again")
        expect(!(await t.text(".fr-block-card")).includes("Time for E2E Salsa playlist"), "the card still says the time is the playlist's")
      } finally {
        for (const i of [task, other]) await c("drop", { id: i })
      }
    },
  },
  {
    name: "its category, chosen on the card, is the server's and says so; Let Friday decide gives it back",
    async run(t) {
      const { click, has, q, c, expect } = t
      const settings = await q("settings")
      const before = settings.categories
      if (!before.categories.length) {
        const two = [{ name: "Social", slug: "social", color: "pink", pattern: "" }, { name: "Study", slug: "study", color: "green", pattern: "" }]
        await c("settings_set", { key: "categories", value: { ...before, categories: two } })
      }
      try {
        const names = (await q("settings")).categories.categories.map((k) => k.name)
        const id = (await q("events", { text: TITLE }))[0].id
        const was = await facts(q, id)
        const pick = names.find((n) => n !== was.category) ?? names[0]
        await card(t, id, TITLE)
        await click(`Category of ${TITLE}`)
        await click(pick)
        const chosen = await server(async () => ((f) => f.category === pick && f.category_by === "you" && f)(await facts(q, id)), `${pick}, by you`)
        expect(chosen, "not chosen")
        await has("your choice", ".fr-block-card")
        await click(`Category of ${TITLE}`)
        await click("Let Friday decide")
        await server(async () => (await facts(q, id)).category_by !== "you", "Friday choosing again")
        await card(t, id, TITLE)
        expect(!(await t.text(".fr-block-card")).includes("your choice"), "the card still says it's your choice")
      } finally {
        if (!before.categories.length) await c("settings_set", { key: "categories", value: before })
      }
    },
  },
  {
    name: "an optional event: I'm going keeps it, and Let Friday decide gives it back to work",
    async run(t) {
      const { click, has, q, c } = t
      const title = "E2E Gym with Sam"
      const id = await event(c, q, title, "16:00", "17:00")
      await c("event_optional", { title, mode: "optional" })
      const d = await today(q)
      const onPlan = async () => (await q("plan", { start: `${d}T00:00`, end: `${d}T23:59` })).fixed.find((f) => f.id === id)
      try {
        await server(async () => (await onPlan())?.optional, "optional on the plan")
        await card(t, id, title)
        await has("Friday", ".fr-block-card") // "Optional: Friday uses its time…" or "Friday would skip it: …"
        await click("I'm going")
        await server(async () => (await onPlan())?.going === true, "kept: going this time")
        await card(t, id, title)
        await has("You're going: work keeps off it.", ".fr-block-card")
        await click("Let Friday decide")
        await server(async () => (await onPlan())?.going === false, "Friday's to give again")
      } finally {
        await c("event_optional", { title, mode: "kept" })
        await c("drop", { id })
      }
    },
  },
  {
    name: "What gives offers to skip an event before late work, and Going stops it being offered",
    async run(t) {
      const { open, has, until, q, c, day, expect } = t
      const d = day(1)
      const club = (await c("add", { title: "E2E Salsa club", when: "fixed", start: `${d}T18:00`, end: `${d}T21:00` })).result.item.id
      const busy = (await c("add", { title: "E2E Busy day", when: "fixed", start: `${d}T06:00`, end: `${d}T18:00` })).result.item.id
      const report = (await c("add", { title: "E2E Lab report", duration_min: 180, firmness: "hard", release: `${d}T17:00`, due: `${d}T21:00` })).result.item.id
      try {
        await t.planned()
        const offered = async () => (await q("triage")).options.some((o) => o.skip_title === "E2E Salsa club")
        expect(await offered(), "Triage doesn't offer to skip E2E Salsa club")
        await open("/?triage")
        await has("E2E Salsa club", "[role=dialog]", 60_000)
        await tap(until, `[aria-label="Going to E2E Salsa club?"] button`, "Going on E2E Salsa club's row")
        await has("Friday won’t suggest skipping it again", "[role=dialog]")
        await server(async () => !(await offered()), "Salsa club no longer offered", 60_000)
      } finally {
        for (const id of [club, busy, report]) await c("drop", { id })
      }
    },
  },
]
