// The To-do page as a view (tests/features.toml: items_view): every open to-do the server has (items) is listed under
// its kind with the section's count; By tag sections them by tag; Show done brings finished ones in; a line typed is
// read back before it's added, as the server reads it (parse), and nothing is added by reading; a to-do opened shows
// what the server has for it (item). Checked on the page against the server.

const shortTerm = (items) => items.filter((i) => i.status === "todo" && !i.long_term && i.when !== "fixed")
const SECTIONS = { Assignment: "Assignments", Chore: "Chores", Errand: "Errands" }

export default [
  {
    name: "each open to-do of a kind is listed under its kind, the section counting them",
    async run({ open, has, until, q, text, expect }) {
      const items = shortTerm(await q("items"))
      await open("/todo")
      await has("To-do")
      for (const [preset, section] of Object.entries(SECTIONS)) {
        // a project's steps of that kind too, under their project; a repeat's times as one row, its next
        const mine = [...new Map(items.filter((i) => i.preset === preset).map((i) => [i.series_id ?? `i${i.id}`, i])).values()]
        if (!mine.length) continue
        await until(`document.querySelector("main").innerText.toLowerCase().includes(${JSON.stringify(`${section.toLowerCase()}\n${mine.length}`)}) || document.querySelector("main").innerText.toLowerCase().includes(${JSON.stringify(`${section.toLowerCase()} ${mine.length}`)})`, 10_000, `${section} counting ${mine.length}`)
        const shown = await text("main")
        for (const i of mine) expect(shown.includes(i.title), `${i.title} (${preset}) isn't listed`)
      }
    },
  },
  {
    name: "By tag sections them by tag, each tag's to-dos under it",
    async run({ open, click, has, q, text, expect }) {
      const items = shortTerm(await q("items")).filter((i) => i.area && i.parent_id === null && i.preset === "Assignment")
      const tags = [...new Set(items.map((i) => i.area))]
      expect(tags.length >= 2, `only ${tags.length} tags among the assignments`)
      await open("/todo")
      await click("View options…")
      await click("By tag")
      await has(tags[0].toUpperCase())
      const shown = await text("main")
      for (const tag of tags) {
        const at = shown.indexOf(tag.toUpperCase())
        expect(at >= 0, `no section for ${tag}`)
        for (const i of items.filter((x) => x.area === tag)) expect(shown.indexOf(i.title, at) > at, `${i.title} isn't under ${tag}`)
      }
      await click("By kind") // the options are still open
    },
  },
  {
    name: "Show done brings finished to-dos in, and takes them out again",
    async run({ open, click, until, q, expect }) {
      const done = (await q("items", { status: "done" })).filter((i) => !i.long_term && i.when !== "fixed" && i.parent_id === null && !/^(Breakfast|Lunch|Dinner)$/.test(i.title))
      expect(done.length > 0, "nothing done in the sample")
      const open_ = new Set((await q("items")).map((i) => i.title))
      const only = done.find((i) => !open_.has(i.title))
      expect(only, "every done to-do has an open one of the same title")
      await open("/todo")
      await until(`!document.querySelector("main").innerText.includes(${JSON.stringify(only.title)})`, 10_000, `${only.title} hidden before Show done`)
      await click("View options…")
      await click("Show done")
      await until(`document.querySelector("main").innerText.includes(${JSON.stringify(only.title)})`, 10_000, `${only.title} shown once done ones are`)
      await click("Show done")
      await until(`!document.querySelector("main").innerText.includes(${JSON.stringify(only.title)})`, 10_000, `${only.title} hidden again`)
    },
  },
  {
    name: "a line typed is read back as the server reads it, and reading adds nothing",
    async run({ open, type, has, q, expect }) {
      const line = "E2E reading check ch 4 due fri 5pm ~2h"
      const before = (await q("items", { status: "all" })).length
      const read = await q("parse", { text: line })
      expect(read.fields.title && read.fields.due_local?.endsWith("T17:00") && read.fields.duration_units, `the server reads ${JSON.stringify(read.fields)}`)
      await open("/todo")
      await type("Add", line)
      await has("Due Fri 5pm")
      await has("2h")
      expect((await q("items", { status: "all" })).length === before, "reading the line added it")
    },
  },
  {
    name: "a to-do opened shows what the server has for it",
    async run({ open, has, q, expect }) {
      const item = shortTerm(await q("items")).find((i) => i.preset === "Assignment" && i.due && i.parent_id === null)
      expect(item, "no open assignment with a due")
      const detail = await q("item", { id: item.id })
      expect(detail.item.id === item.id && detail.item.title === item.title, "the server's item differs from its list")
      await open(`/todo?item=${item.id}`)
      await has(item.title)
      await has("Planned sessions")
      if (item.area) await has(item.area)
    },
  },
]
