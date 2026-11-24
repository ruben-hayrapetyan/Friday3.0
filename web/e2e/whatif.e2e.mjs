// What if (tests/features.toml: whatif), on the plan: Plan → What if starts trying; something typed is tried, not
// made, and said how it lands (whatif); Take this out takes it back out; Discard leaves with nothing kept; Keep makes
// what was tried for real (whatif_keep), and Undo takes it back. Checked on the page and on the server.

const settle = async (check, what, ms = 15_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const titled = async (q, title) => (await q("items", { status: "all", text: title })).filter((i) => i.title.toLowerCase().includes(title.toLowerCase()))
const inPanel = `document.querySelector('[aria-label="Something to try"]')`
const lands = `/Fits|Tight|Late/.test(document.querySelector('[aria-label="What if"]')?.innerText ?? "")`

/** Words on the page whatever their case (the panel's headings are set in capitals). */
const shows = (until, words) => until(`document.body.innerText.toLowerCase().includes(${JSON.stringify(words.toLowerCase())})`, 10_000, `"${words}" on the page`)

const start = async ({ open, click, until, planned }) => {
  await planned()
  await open("/")
  await click("Plan…")
  await click("What if")
  await until(`!!${inPanel}`, 10_000, "What if's panel")
}

export default [
  {
    name: "a to-do tried in What if is said how it lands, isn't made, and Take this out takes it back out",
    async run(t) {
      const { type, click, has, until, q, text, expect } = t
      await start(t)
      await shows(until, "Try something")
      await type("Something to try", "E2E whatif essay ~3h due fri 5pm")
      await click("Try")
      await shows(until, "Trying")
      await shows(until, "How it lands")
      await until(lands, 90_000, "how it lands (Fits, Tight or Late) in the header")
      const said = await text('[aria-label="What if"]')
      expect(/Keep/.test(said) && /Discard/.test(said), `the header says "${said}"`)
      expect((await titled(q, "E2E whatif essay")).length === 0, "trying it made it for real")
      await click("Take this out")
      await until(`!document.body.innerText.toLowerCase().includes("how it lands")`, 10_000, "the change taken out")
      await click("Leave What if")
      await until(`!${inPanel}`, 10_000, "What if closed")
      expect((await titled(q, "E2E whatif essay")).length === 0, "taking it out made it")
    },
  },
  {
    name: "Discard leaves What if and keeps nothing tried",
    async run(t) {
      const { type, click, has, until, q, expect } = t
      const rules = (await q("rules")).length
      await start(t)
      await type("Something to try", "No work after 8pm")
      await click("Try rule")
      await shows(until, "Trying")
      await until(lands, 90_000, "how it lands")
      await click("Discard")
      await until(`!${inPanel}`, 10_000, "What if closed")
      await new Promise((r) => setTimeout(r, 800))
      expect((await q("rules")).length === rules, "a rule tried and discarded was kept")
    },
  },
  {
    name: "Keep makes what was tried for real, as one change; Undo takes it back",
    async run(t) {
      const { type, click, has, until, q, expect } = t
      const had = new Set((await titled(q, "E2E whatif lab")).map((i) => i.id)) // a run before may have left one
      const fresh = async () => (await titled(q, "E2E whatif lab")).filter((i) => !had.has(i.id))
      await start(t)
      await type("Something to try", "E2E whatif lab ~2h due thu 5pm")
      await click("Try")
      await until(lands, 90_000, "how it lands")
      await until(`[...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Keep it" && !b.disabled)`, 30_000, "Keep it ready")
      await click("Keep it")
      await until(`!${inPanel}`, 10_000, "What if closed after Keep")
      await settle(async () => (await fresh()).some((i) => i.status === "todo"), "the kept to-do on the server")
      const [made] = await fresh()
      expect(made.duration_min === 120, `kept as ${made.duration_min} min, not 2h`)
      await has("Undo")
      await click("Undo")
      await settle(async () => (await fresh()).every((i) => i.status !== "todo"), "Undo taking it back")
    },
  },
]
