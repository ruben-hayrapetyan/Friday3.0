// To-dos (tests/features.toml: items): added the way you'd say it, seen in To-do with what it was read as, opened,
// marked done and opened again; every step checked on the page and on the server.

const find = async (q, title) => (await q("items", { status: "all" })).find((i) => i.title === title)

export default [
  {
    name: "a to-do typed the way you'd say it is added, read as said, and shows in To-do",
    async run({ open, type, has, q, planned, expect }) {
      await open("/todo")
      await type("Add", "E2E lab writeup due fri 5pm ~2h", { enter: true })
      await has("E2E lab writeup")
      const item = await find(q, "E2E lab writeup")
      expect(item, "the server has no E2E lab writeup")
      expect(item.duration_min === 120, `read as ${item.duration_min} min, not 2h`)
      expect(item.due?.endsWith("T17:00") && new Date(item.due).getDay() === 5, `due ${item.due}, not Friday 5pm`)
      await planned()
    },
  },
  {
    name: "its detail opens from its row; Mark done finishes it, Open again opens it",
    async run({ open, until, click, has, q, expect }) {
      const item = await find(q, "E2E lab writeup")
      await open(`/todo?item=${item.id}`)
      await has("Planned sessions")
      await click("Mark done")
      await until(`true`, 100)
      for (let i = 0; i < 40 && (await find(q, "E2E lab writeup")).status !== "done"; i++) await new Promise((r) => setTimeout(r, 250))
      expect((await find(q, "E2E lab writeup")).status === "done", "Mark done didn't finish it on the server")
      await click("Open again")
      for (let i = 0; i < 40 && (await find(q, "E2E lab writeup")).status !== "todo"; i++) await new Promise((r) => setTimeout(r, 250))
      expect((await find(q, "E2E lab writeup")).status === "todo", "Open again didn't open it on the server")
    },
  },
]
