// Other ways to plan (tests/features.toml: ways): Plan → Other ways plans two more ways to plan the same work, each a
// card (how it differs, its hours and sittings); Preview lays one over the calendar with a banner, Back to the options
// shows the same ways again; Pick this makes it the plan and Friday learns from the pick. The card picked is the
// server's way for its seed, word for word.

const waitFor = async (check, ms = 15_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 400))) {
    const found = await check()
    if (found) return found
  }
  return null
}
const DIALOG = "[role=dialog][aria-label='Other ways']"
const cards = `[...document.querySelectorAll("${DIALOG} .fr-well")].filter((c) => c.innerText.includes("Pick this")).map((c) => c.innerText.replace(/\\s+/g, " "))`
let shown = []

async function openWays({ open, click, until, has }) {
  await open("/")
  await click("Plan…")
  await click("Other ways")
  await has("Other ways", DIALOG)
  return until(`(() => { const d = document.querySelector("${DIALOG}"); if (!d) return null; if (d.innerText.includes("No other way")) return "none"; const c = ${cards}; return c.length >= 1 && !d.innerText.includes("Planning way") ? c : null })()`, 240_000, "the other ways planned")
}

export default [
  {
    name: "Other ways plans two more ways, each with how it differs, its hours and sittings",
    async run(t) {
      const { expect } = t
      const found = await openWays(t)
      if (found === "none") return console.log("      (no other way would change much in this sample)")
      shown = found
      expect(shown.length === 2, `${shown.length} ways shown`)
      for (const c of shown) expect(/Way \d/i.test(c) && / h /.test(` ${c}`) && /sittings/.test(c) && /(nothing late|\d+ late)/.test(c), `a card: ${c}`)
      expect(shown[0] !== shown[1], "the two ways are the same")
    },
  },
  {
    name: "Preview lays a way over the calendar; Back to the options shows the same ways; × stops previewing",
    async run(t) {
      const { click, has, gone, until, expect } = t
      if (!shown.length) return
      const again = await openWays(t) // a new page load plans them again: the same seeds, the same ways
      expect(JSON.stringify(again) === JSON.stringify(shown), "the same seeds planned other ways")
      await click("Preview")
      await has("Back to the options") // the banner (its "Previewing" is drawn in capitals)
      const summary = shown[0].replace(/^Way 1 /i, "").split(" ").slice(0, 4).join(" ")
      await has(summary)
      await click("Back to the options")
      await has("Pick this", DIALOG)
      const back = await until(cards)
      expect(JSON.stringify(back) === JSON.stringify(shown), "Back to the options shows other ways")
      await click("Preview")
      await click("Stop previewing")
      await gone("Back to the options")
    },
  },
  {
    name: "Pick this makes it the plan: the server's way for that seed, and Friday counts the pick",
    async run(t) {
      const { click, gone, q, expect } = t
      if (!shown.length) return
      const before = await q("learning")
      const plan = (await q("status")).plan_generation
      const now = await openWays(t)
      // the first way the page found, asked of the server for the same plan: the card says it
      let first
      for (let seed = 1; seed <= 6 && !first; seed++) first = (await q("other_way", { seed })).way
      expect(first, "the server finds no other way")
      const hours = Number(now[0].match(/([\d.]+) h /)?.[1])
      expect(now[0].includes(first.summary) && Math.abs(hours - first.hours) <= 0.5 && now[0].includes(`${first.sessions} sittings`), `card "${now[0]}" isn't the server's ${JSON.stringify({ s: first.summary, h: first.hours, n: first.sessions })}`)
      const last = (await q("log_list", { limit: 1 }))[0]?.id ?? 0
      await click("Pick this")
      await gone("Pick this", DIALOG).catch(() => {})
      const picked = await waitFor(async () => (await q("log_list", { limit: 5 })).find((e) => e.command === "other_way_pick" && e.id > last))
      expect(picked, "Pick this sent nothing")
      expect(picked.input.seed === first.seed && JSON.stringify(picked.input.weights) === JSON.stringify(first.weights), `picked ${JSON.stringify(picked.input).slice(0, 200)}`)
      expect(await waitFor(async () => (await q("learning")).comparisons > before.comparisons), "the pick wasn't counted")
      expect(await waitFor(async () => (await q("status")).plan_generation > plan, 120_000), "no new plan after the pick")
    },
  },
  {
    name: "the server refuses a way with no seed and a pick without its rules",
    async run({ request, expect }) {
      const none = await request("GET", "/api/q/other_way")
      expect(none.status === 422, `no seed: ${none.status}`)
      const bad = await request("POST", "/api/c/other_way_pick", { weights: {}, seed: 1 })
      expect(bad.status === 422, `no rule_totals: ${JSON.stringify(bad)}`)
    },
  },
]
