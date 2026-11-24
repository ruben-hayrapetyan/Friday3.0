// The log (tests/features.toml: log_view): a block's History on the calendar lists what was done to its to-do, by
// whom, newest first, from the server's log; a change made from the popover joins it; one undone is struck through.
// (`stats` has no page: its numbers are checked headless, tests/system/test_log_view_pipeline.py.)

const TITLE = "E2E history: problem set"

/** Until `check()` is truthy, within ten seconds. */
async function eventually(check, said, wait) {
  for (let end = Date.now() + 10_000; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited 10s for ${said}`)
  }
}

/** The history's lines, as shown. */
const lines = (until) =>
  until(`(() => { const b = [...document.querySelectorAll("button[aria-expanded=true]")].find((x) => x.textContent.includes("History")); if (!b) return false; const box = b.parentElement.nextElementSibling; return box ? [...box.children].map((s) => ({ text: s.innerText.replace(/\\s+/g, " "), struck: s.style.textDecoration.includes("line-through") })) : false })()`, 10_000, "the history open")

/** Opens the popover of one of the item's blocks the calendar shows; its key. */
async function openBlock({ q, until, day, expect }, id) {
  const plan = await q("plan", { start: `${day(-1)}T04:00`, end: `${day(8)}T04:00` })
  const keys = plan.blocks.filter((b) => b.item_id === id).map((b) => b.key)
  expect(keys.length, `${TITLE} isn't planned`)
  return until(`(() => { const k = ${JSON.stringify(keys)}.find((k) => document.querySelector('[data-block-key="' + k + '"]')); if (!k) return false; document.querySelector('[data-block-key="' + k + '"]').click(); return k })()`, 10_000, "its block on the calendar")
}

export default [
  {
    name: "a block's History lists its to-do's changes from the log, newest first, by who made them",
    async run(t) {
      const { open, click, has, until, q, c, planned, day, expect } = t
      const made = await c("add", { title: TITLE, duration_min: 60, due: `${day(1)}T22:00` })
      const id = made.result.item.id
      await c("edit", { id, notes: "questions 1–5" })
      await planned()
      await open("/")
      await openBlock(t, id)
      await click("History")
      await has("Added · You")
      const shown = await lines(until)
      const log = await q("log_list", { item_id: id, limit: 12 })
      expect(log.map((e) => e.command).join() === "edit,add", `the server's log: ${log.map((e) => e.command)}`)
      expect(shown.length === log.length, `${shown.length} lines shown for ${log.length} in the log`)
      expect(shown[0].text.includes("Changed · You") && shown[1].text.includes("Added · You"), `shown: ${shown.map((s) => s.text).join(" | ")}`)
      expect(!shown.some((s) => s.struck), "something's struck through that wasn't undone")
    },
  },
  {
    name: "Pin here from the popover joins its History; undone, it's struck through",
    async run(t) {
      const { open, click, has, until, q, c, planned, expect, wait } = t
      const item = (await q("items", { text: TITLE }))[0]
      expect(item, `no ${TITLE}`)
      await open("/")
      await openBlock(t, item.id)
      await click("Pin here")
      const pinned = await eventually(async () => (await q("log_list", { item_id: item.id, limit: 1 })).find((e) => e.command === "pin"), "the pin in the log", wait)
      await planned()
      await open("/")
      await openBlock(t, item.id)
      await click("History")
      await has("Pinned · You")
      expect((await lines(until))[0].text.includes("Pinned · You"), "the pin isn't the newest line")
      const undo = await c("undo", { command_id: pinned.id })
      expect((await q("log_list", { item_id: item.id, limit: 12 })).find((e) => e.id === pinned.id).undone_by === undo.command_id, "the server doesn't say what undid it")
      await planned()
      await open("/")
      await openBlock(t, item.id)
      await click("History")
      await has("Pinned · You")
      const after = await lines(until)
      const line = after.find((s) => s.text.includes("Pinned"))
      expect(line.struck, "the undone pin isn't struck through")
      expect(after.filter((s) => s.struck).length === 1, "more than the pin is struck through")
      await c("drop", { id: item.id })
    },
  },
]
