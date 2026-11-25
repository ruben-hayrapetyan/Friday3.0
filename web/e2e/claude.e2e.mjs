// Ask Claude (tests/features.toml: claude), from the plan's menu: what you want, asked (ask_claude), comes back as
// changes to tick; nothing changes until Apply, Apply runs only those ticked, a change that can't be made can't be
// ticked, and the toast's Undo takes them back. The demo's AI has nothing to propose, which the page says; for the
// proposals, the AI's answer is made up here (`stub`) and everything after it, applying and undoing, is the server's.

const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const titled = async (q, title) => (await q("items", { status: "all", text: title })).filter((i) => i.title === title && i.status === "todo")
const event = async (q, title) => (await q("plan")).fixed.filter((f) => f.title === title && f.status === "todo")

const openAsk = async ({ open, click, has }) => {
  await open("/")
  await click("Plan…")
  await click("Ask Claude")
  await has("Ask", '[role=dialog][aria-label="Ask Claude"]')
}

export default [
  {
    name: "asked something the AI has no change for, the page says so and nothing changes",
    async run(t) {
      const { type, click, has, q, expect } = t
      const before = (await q("items", { status: "all" })).length
      await openAsk(t)
      await type("What you want", "Move my 5pm tomorrow to Thursday")
      await click("Ask")
      await has("Claude had no changes to suggest for this. Try saying it another way.", "body", 60_000)
      expect((await q("items", { status: "all" })).length === before, "asking changed the to-dos")
    },
  },
  {
    name: "the AI's changes are ticked to apply; Apply runs only those ticked, and Undo takes them back",
    async run(t) {
      const { type, click, has, until, q, stub, day, evaluate, expect } = t
      const at = `${day(2)}T15:00`
      const actions = [
        { sentence: "Add E2E coffee with Sam", command: "add", input: { title: "E2E coffee with Sam", when: "fixed", start: at, end: `${day(2)}T16:00` }, error: null, event: true },
        { sentence: "Add E2E reading for an hour", command: "add", input: { title: "E2E reading", duration_min: 60 }, error: null, event: false },
        { sentence: "Delete what isn't there", command: "drop", input: { id: 999999 }, error: "no such item", event: false },
      ]
      await stub({ "c/ask_claude": { command_id: null, result: { reply: "Here is what I'd change.", actions }, provisional: null, changes: null, preview: false, repeated: false, generation: null } })
      await openAsk(t)
      await type("What you want", "coffee with Sam thursday at 3, and an hour of reading")
      await click("Ask")
      await has("Here is what I'd change.")
      await has("Add E2E coffee with Sam")
      await has("no such item")
      expect(!(await titled(q, "E2E coffee with Sam")).length && !(await titled(q, "E2E reading")).length, "a proposal ran before Apply")
      await has("Apply 2")
      const offered = await evaluate(`[...document.querySelectorAll("[role=dialog] button")].find((b) => b.innerText.includes("Delete what isn't there"))?.disabled`)
      expect(offered === true, "a change that can't be made can be ticked")
      await click("Add E2E reading for an hour") // untick it
      await has("Apply 1")
      await click("Apply")
      await settle(async () => (await event(q, "E2E coffee with Sam")).length === 1, "the coffee on the plan")
      const [coffee] = await event(q, "E2E coffee with Sam")
      expect(coffee.start === at, `the coffee is at ${coffee.start}, not ${at}`)
      expect(!(await titled(q, "E2E reading")).length, "the change unticked was applied")
      await has("Applied 1 change")
      await until(`[...document.querySelectorAll("[role=status] button")].some((b) => b.textContent.trim() === "Undo")`, 10_000, "Undo on the toast")
      await evaluate(`[...document.querySelectorAll("[role=status] button")].find((b) => b.textContent.trim() === "Undo").click()`)
      await settle(async () => (await event(q, "E2E coffee with Sam")).length === 0, "Undo taking the coffee off the plan")
    },
  },
]
