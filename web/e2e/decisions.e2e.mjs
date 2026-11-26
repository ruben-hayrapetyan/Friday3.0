// Decisions (tests/features.toml: decisions), in the Inbox: an errand locked where hard work has to go makes it late,
// and the Inbox asks two things — keep the lock where it is (lock_keep), and whether to leave the work late
// (late_accept). Each answered from its pane leaves the Inbox and isn't asked again, while the plan keeps the lock
// and the work stays late, as answered. Checked on the page and on the server.

const settle = async (check, what, ms = 90_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 400))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const local = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
const decisions = async (q) => (await q("status")).decisions
/** Opens the Inbox message whose row shows `title`. */
const openRow = (evaluate, title) =>
  evaluate(`(() => {
    const rows = [...document.querySelectorAll("button, [role=button], [role=option]")].filter((b) => b.getBoundingClientRect().width > 0 && b.innerText.includes(${JSON.stringify(title)}))
    const row = rows.sort((a, b) => a.innerText.length - b.innerText.length)[0]
    if (!row) return false
    row.click()
    return true
  })()`)

let made = null

export default [
  {
    name: "an errand locked where hard work has to go: the Inbox asks to keep the lock, and Keep it is kept",
    async run({ open, click, has, until, q, c, planned, evaluate, expect, day }) {
      // Two free waking hours tomorrow, nothing fixed in them or half an hour either side: the lock there, and the
      // work's only time is the lock's, so the lock alone makes it late (26 Nov: locked over the next two hours, at
      // 2pm a class and after midnight sleep made the work late with or without it, and the lock wasn't asked about)
      const fixed = (await q("plan", { start: `${day(1)}T00:00`, end: `${day(2)}T00:00` })).fixed
      const free = (from) => fixed.every((f) => f.end <= local(new Date(from - 30 * 60_000)) || f.start >= local(new Date(from + 150 * 60_000)))
      const at = [...Array(33).keys()].map((n) => new Date(`${day(1)}T10:00`).getTime() + n * 15 * 60_000).find(free)
      expect(at !== undefined, `no two free hours tomorrow: ${JSON.stringify(fixed.map((f) => [f.title, f.start, f.end]))}`)
      const start = new Date(at)
      const end = new Date(start.getTime() + 2 * 3_600_000)
      const errand = (await c("add", { title: "E2E errand run", duration_min: 120, due: local(new Date(start.getTime() + 4 * 86_400_000)) })).result.item
      await c("pin", { id: errand.id, start: local(start), end: local(end), kind: "locked" })
      const work = (await c("add", { title: "E2E problem set", duration_min: 120, firmness: "hard", release: local(start), due: local(end) })).result.item
      made = { errand: errand.id, work: work.id }
      await planned()
      await settle(async () => (await decisions(q)).some((d) => d.kind === "lock" && d.item_id === errand.id), "the lock asked about")
      const asked = (await decisions(q)).find((d) => d.kind === "lock" && d.item_id === errand.id)
      expect(asked.title === "Keep E2E errand run where you locked it?", `asked "${asked.title}"`)
      await open("/inbox")
      await has(asked.title)
      expect(await openRow(evaluate, asked.title), "no row for the lock")
      await has("Let it move")
      await click("Keep it")
      await settle(async () => !(await decisions(q)).some((d) => d.key === asked.key), "the lock no longer asked about")
      await until(`!document.querySelector("main").innerText.includes(${JSON.stringify(asked.title)})`, 10_000, "the lock's question gone from the Inbox")
      await planned()
      const blocks = (await q("plan", { start: local(start), end: local(new Date(end.getTime() + 60_000)) })).blocks.filter((b) => b.item_id === errand.id)
      expect(blocks.length && blocks.every((b) => b.pinned === "locked"), `the errand isn't kept locked: ${JSON.stringify(blocks)}`)
      expect(!(await decisions(q)).some((d) => d.kind === "lock" && d.item_id === errand.id), "kept, the lock is asked about again")
    },
  },
  {
    name: "the late work is asked about; Leave it late leaves it late and it isn't asked again",
    async run({ open, click, has, until, q, evaluate, expect }) {
      expect(made, "the test before didn't make the work")
      await settle(async () => (await decisions(q)).some((d) => d.kind === "late" && d.items.some((i) => i.item_id === made.work)), "the late work asked about")
      const asked = (await decisions(q)).find((d) => d.kind === "late")
      await open("/inbox")
      await has(asked.title)
      expect(await openRow(evaluate, asked.title), "no row for the late work")
      await has("E2E problem set")
      await has("Leave it late")
      await click("Leave it late")
      await settle(async () => !(await decisions(q)).some((d) => d.kind === "late" && d.items.some((i) => i.item_id === made.work)), "the late work no longer asked about")
      expect((await q("status")).late_items.some((i) => i.item_id === made.work), "left late, the work isn't late any more")
      await open("/inbox")
      // the sidebar's day still lists it: the Inbox itself (main) doesn't
      await until(`!document.querySelector("main").innerText.includes("E2E problem set")`, 10_000, "the late work gone from the Inbox")
    },
  },
  {
    name: "the lock and the work taken away, nothing about them is asked",
    async run({ q, c, planned, expect }) {
      if (!made) return
      await c("drop", { id: made.work })
      await c("drop", { id: made.errand })
      await planned()
      const left = (await decisions(q)).filter((d) => d.item_id === made.errand || (d.items ?? []).some((i) => i.item_id === made.work))
      expect(!left.length, `still asked: ${JSON.stringify(left)}`)
    },
  },
]
