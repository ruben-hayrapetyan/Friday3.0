// Kinds of to-do (tests/features.toml: kinds), in Settings → Tags/Kinds: a kind added as a copy of another shows in the
// priority list and on the server with the copied kind's settings; a name taken is refused with the server's words;
// deleting one moves what used it to the kind you pick; kinds calendars read into can't be deleted.

const presets = async (q) => (await q("settings")).presets

export default [
  {
    name: "a new kind, working like Reading, is added to the list and the server",
    async run({ open, type, click, has, q, expect }) {
      await open("/settings/tags")
      await has("Kinds, in priority order")
      await type("New kind", "E2E Lab report")
      await click("Starts as a copy of…")
      await click("Reading")
      await click("Add kind")
      await has("Added E2E Lab report")
      for (let i = 0; i < 40 && !(await presets(q))["E2E Lab report"]; i++) await new Promise((r) => setTimeout(r, 250))
      const all = await presets(q)
      expect(all["E2E Lab report"], "the server has no kind E2E Lab report")
      expect(JSON.stringify(all["E2E Lab report"]) === JSON.stringify(all.Reading), `not a copy of Reading: ${JSON.stringify(all["E2E Lab report"])}`)
      await has("E2E Lab report", "main")
      const field = await q("settings")
      expect(field.presets["E2E Lab report"] && !field.presets["e2e lab report"], "added twice")
    },
  },
  {
    name: "a name already taken, in any case, is refused with the server's words and nothing changes",
    async run({ open, type, click, has, q, expect }) {
      const before = Object.keys(await presets(q)).length
      await open("/settings/tags")
      await type("New kind", "e2e lab REPORT")
      await click("Add kind")
      await has("There is already a kind called e2e lab REPORT")
      expect(Object.keys(await presets(q)).length === before, "a second kind was added")
    },
  },
  {
    name: "deleting a kind moves its to-dos to the kind picked; Cancel keeps it",
    async run({ open, click, has, gone, q, c, expect, text }) {
      const item = (await c("add", { title: "E2E titration writeup", preset: "E2E Lab report", duration_min: 60 })).result.item
      expect(item.preset === "E2E Lab report", `added as ${item.preset}`)
      await open("/settings/tags")
      await click("Delete E2E Lab report")
      await has("Delete E2E Lab report. Anything of this kind becomes")
      await click("Cancel")
      await gone("Anything of this kind becomes")
      expect((await presets(q))["E2E Lab report"], "Cancel deleted it")
      await click("Delete E2E Lab report")
      await click("Move its items to…")
      await click("Assignment")
      await click("Delete")
      await has("Deleted E2E Lab report; 1 moved to Assignment")
      for (let i = 0; i < 40 && (await presets(q))["E2E Lab report"]; i++) await new Promise((r) => setTimeout(r, 250))
      expect(!(await presets(q))["E2E Lab report"], "the server still has the kind")
      const moved = (await q("item", { id: item.id })).item
      expect(moved.preset === "Assignment", `its to-do is now ${moved.preset}, not Assignment`)
      await gone("E2E Lab report", "main")
      expect(!(await text("main")).includes("E2E Lab report"), "the deleted kind still shows")
      await c("drop", { id: item.id })
    },
  },
  {
    name: "kinds calendars read into have no delete; the server refuses deleting one",
    async run({ open, has, until, request, q, expect }) {
      await open("/settings/tags")
      await has("Assignment", "main")
      expect(await until(`![...document.querySelectorAll("button")].some((b) => b.getAttribute("aria-label") === "Delete Assignment")`, 500), "Assignment can be deleted")
      expect(await until(`[...document.querySelectorAll("button")].some((b) => b.getAttribute("aria-label")?.startsWith("Delete "))`, 2000), "no kind has a delete button")
      const refused = await request("POST", "/api/c/kind_remove", { name: "Exam", move_to: "Assignment" })
      expect(refused.status === 422 && refused.body.message.includes("calendars and mail are read into Exam"), JSON.stringify(refused))
      expect((await q("settings")).presets.Exam, "Exam is gone")
    },
  },
]
