// Pins (tests/features.toml: pins), on the plan: a block opened from the calendar is pinned where it is ("Pin here"),
// the card staying open and saying Unpin; Unpin gives it back to Friday; a locked block says Unlock, which keeps it
// pinned but movable. Each checked on the page and in the server's plan.

const MEALS = /^(Breakfast|Lunch|Dinner)$/
const settle = async (check, what, ms = 30_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}

/** A block of work coming up that's on the page and free to pin: its key, item and time. */
const aBlock = async ({ q, evaluate }) => {
  const now = new Date()
  for (const b of (await q("plan")).blocks) {
    if (b.pinned || b.fixed || b.background || MEALS.test(b.title) || new Date(b.start) < new Date(now.getTime() + 3_600_000)) continue
    if (await evaluate(`!!document.querySelector('[data-block-key="${b.key}"]')`)) return b
  }
  throw new Error("no block of work coming up on the page")
}
const pinOf = async (q, item) => (await q("plan")).blocks.filter((b) => b.item_id === item).map((b) => b.pinned)
const openBlock = async ({ evaluate, has }, key, title) => {
  await evaluate(`document.querySelector('[data-block-key="${key}"]').click()`)
  await has(title, ".fr-block-card")
}

export default [
  {
    name: "Pin here keeps a block where it is; the card stays open and says Unpin; Unpin gives it back to Friday",
    async run(t) {
      const { open, click, has, until, q, planned, expect } = t
      await planned()
      await open("/")
      const b = await aBlock(t)
      await openBlock(t, b.key, b.title)
      await click("Pin here")
      await settle(async () => (await q("plan")).blocks.some((x) => x.item_id === b.item_id && x.pinned === "preferred" && x.start === b.start && x.end === b.end), `${b.title} pinned at ${b.start} on the server`)
      await until(`[...document.querySelectorAll(".fr-block-card button")].some((x) => x.textContent.trim() === "Unpin")`, 10_000, "Unpin on the card")
      await has(b.title, ".fr-block-card")
      await click("Unpin")
      await settle(async () => (await pinOf(q, b.item_id)).every((p) => !p), `${b.title} unpinned on the server`)
      await planned()
    },
  },
  {
    name: "a locked block says Unlock; Unlock leaves it pinned but free to move, and Unpin lets it go",
    async run(t) {
      const { open, click, has, until, q, c, planned, expect } = t
      await open("/")
      const b = await aBlock(t)
      await c("pin", { id: b.item_id, start: b.start, end: b.end, kind: "locked" })
      await settle(async () => (await pinOf(q, b.item_id)).includes("locked"), "locked on the server")
      await planned()
      await open("/")
      const locked = (await q("plan")).blocks.find((x) => x.item_id === b.item_id && x.pinned === "locked")
      expect(locked && locked.start === b.start, `the lock moved it to ${locked?.start}`)
      await openBlock(t, locked.key, b.title)
      expect(!(await t.text(".fr-block-card")).includes("Pin here"), "a locked block offers Pin here")
      await click("Unlock")
      await settle(async () => (await q("plan")).blocks.some((x) => x.item_id === b.item_id && x.pinned === "preferred"), "unlocked to a pin on the server")
      await until(`[...document.querySelectorAll(".fr-block-card button")].some((x) => x.textContent.trim() === "Unpin")`, 10_000, "Unpin on the card")
      await click("Unpin")
      await settle(async () => (await pinOf(q, b.item_id)).every((p) => !p), "no pin left on the server")
      await planned()
    },
  },
]
