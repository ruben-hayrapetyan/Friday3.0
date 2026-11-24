// Undo (tests/features.toml: undo): a change's toast has Undo, which takes it back on the server and the page; ⌘Z
// undoes the last change made on the page, and says so when there's nothing to undo; and a to-do marked done is opened
// again by its Undo. Every step checked on the page and on the server.

const find = async (q, title) => (await q("items", { status: "all" })).find((i) => i.title === title)

/** Until `check()` is truthy, within `ms`. */
async function eventually(check, ms, said, wait) {
  for (let end = Date.now() + ms; ; await wait(250)) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`waited ${ms / 1000}s for ${said}`)
  }
}

/** Presses the button whose own words are `words` (the to-do panel's "Mark done", not a row's circle, whose name is
 * also "Mark done" but in its aria-label). */
const pressWords = (until, words) =>
  until(`(() => { const b = [...document.querySelectorAll("button")].find((b) => !b.getAttribute("aria-label") && b.textContent.trim() === ${JSON.stringify(words)} && b.getBoundingClientRect().width > 0); if (!b) return false; b.click(); return true })()`, 10_000, `a button reading "${words}"`)

/** Out of the text box, so the keys go to the page (⌘Z in a box is the box's own undo). */
const leaveFields = (until) => until(`(document.activeElement?.blur(), true)`, 2_000)

export default [
  {
    name: "the Undo in a new to-do's toast takes it back on the server and off the page",
    async run({ open, type, click, has, until, q, expect, wait }) {
      await open("/todo")
      await type("Add", "E2E undo me tomorrow ~30m", { enter: true })
      await has("E2E undo me")
      const item = await eventually(() => find(q, "E2E undo me"), 10_000, "the to-do on the server", wait)
      expect(item.status === "todo", `added as ${item.status}`)
      await click("Undo")
      await has("Undone")
      await eventually(async () => !(await find(q, "E2E undo me")), 10_000, "the to-do gone from the server", wait)
      await until(`!document.body.innerText.includes("E2E undo me")`, 10_000, "the to-do gone from the page")
    },
  },
  {
    name: "⌘Z undoes the last change made on the page",
    async run({ open, type, has, until, press, q, expect, wait }) {
      await open("/todo")
      await type("Add", "E2E keyboard undo check tomorrow ~20m", { enter: true })
      await has("E2E keyboard undo check")
      await eventually(() => find(q, "E2E keyboard undo check"), 10_000, "the to-do on the server", wait)
      await leaveFields(until)
      await press("Meta+z")
      await has("Undone")
      await eventually(async () => !(await find(q, "E2E keyboard undo check")), 10_000, "the to-do gone from the server", wait)
      await until(`!document.body.innerText.includes("E2E keyboard undo check")`, 10_000, "the to-do gone from the page")
      expect(!(await find(q, "E2E keyboard undo check")), "⌘Z left the to-do on the server")
    },
  },
  {
    name: "⌘Z with nothing done on the page says there's nothing to undo and changes nothing",
    async run({ open, has, until, press, q, expect }) {
      const before = (await q("items", { status: "all" })).length
      await open("/")
      await leaveFields(until)
      await press("Meta+z")
      await has("Nothing to undo")
      expect((await q("items", { status: "all" })).length === before, "⌘Z with nothing to undo changed the to-dos")
    },
  },
  {
    name: "a to-do marked done is opened again by its toast's Undo",
    async run({ open, click, has, until, q, c, planned, expect, wait }) {
      const made = await c("add", { title: "E2E undo the done", duration_min: 45, due: `${new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10)}T17:00` })
      const id = made.result.item.id
      await planned()
      await open(`/todo?item=${id}`)
      await has("Planned sessions")
      const others = (await q("items")).filter((i) => i.id !== id).length
      await pressWords(until, "Mark done")
      await eventually(async () => (await find(q, "E2E undo the done")).status === "done", 10_000, "done on the server", wait)
      await click("Undo")
      await has("Undone")
      await eventually(async () => (await find(q, "E2E undo the done")).status === "todo", 10_000, "to do again on the server", wait)
      expect((await find(q, "E2E undo the done")).status === "todo", "Undo didn't open it again")
      expect((await q("items")).filter((i) => i.id !== id).length === others, "another to-do was finished or opened")
      await has("Mark done")
      await c("drop", { id })
    },
  },
]
