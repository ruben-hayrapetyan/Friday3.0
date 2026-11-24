// Insights: trends (tests/features.toml: insights): the numbers on Insights → Trends are the server's `insights` for
// the weeks picked (things finished, hours, estimate against time taken, each kind's row, the best hours), a range
// picked reads them again for those weeks, and the tabs open Sleep, Meals and This week. Work finished now shows.

const big = `[...document.querySelectorAll("[data-tour=insights] > div")].map((d) => d.innerText.replace(/\\s+/g, " ").trim())`

async function agree({ until, text, expect }, data) {
  const tiles = await until(big, 10_000, "the three numbers")
  expect(tiles[0] === `${data.done} things finished in ${data.weeks} weeks`, `first: "${tiles[0]}", server ${data.done} in ${data.weeks}`)
  expect(tiles[1] === `${data.hours} h of work recorded`, `second: "${tiles[1]}", server ${data.hours} h`)
  const ratio = data.estimate_ratio ? `${data.estimate_ratio}× how long things take against the estimate` : "— Finish a few things to compare with estimates"
  expect(tiles[2] === ratio, `third: "${tiles[2]}", server ${data.estimate_ratio}`)
  const page = await text("main")
  expect(page.includes(`Based on ${data.done} finished ${data.done === 1 ? "thing" : "things"}`), "the head note's count")
  for (const k of data.by_kind) expect(page.includes(`${k.kind}`) && page.includes(`(${k.n})`), `${k.kind} (${k.n}) isn't shown`)
  expect(page.includes(data.best_hours ?? "Not enough recorded work yet to see a pattern."), `best hours: ${data.best_hours}`)
}

export default [
  {
    name: "Trends says the server's numbers for four weeks, the default",
    async run(t) {
      const { open, has, q } = t
      await open("/insights?tab=trends")
      await has("How long things really take")
      await agree(t, await q("insights", { weeks: 4 }))
    },
  },
  {
    name: "picking 2 or 12 weeks reads the numbers for those weeks",
    async run(t) {
      const { open, click, has, q, until, expect } = t
      await open("/insights?tab=trends")
      for (const weeks of [12, 2]) {
        await click(`${weeks} weeks`)
        const data = await q("insights", { weeks })
        await has(`things finished in ${weeks} weeks`)
        await agree(t, data)
        const cells = await until(`document.querySelector("[title*='in the last ${weeks} weeks']") ? true : false`, 5000, "the heatmap for those weeks")
        expect(cells, "the heatmap doesn't say its weeks")
      }
    },
  },
  {
    name: "a task finished with time logged now counts in the numbers on the page",
    async run(t) {
      const { open, has, q, c, expect } = t
      const before = await q("insights", { weeks: 4 })
      const item = (await c("add", { title: "E2E insights reading", preset: "Reading", duration_min: 60 })).result.item
      const start = new Date(Date.now() - 3 * 3_600_000)
      const p = (n) => String(n).padStart(2, "0")
      const at = (d) => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
      await c("log", { id: item.id, start: at(start), end: at(new Date(start.getTime() + 90 * 60_000)) })
      await c("done", { id: item.id })
      const after = await q("insights", { weeks: 4 })
      expect(after.done === before.done + 1, `finished ${before.done} → ${after.done}`)
      expect(Math.abs(after.hours - before.hours - 1.5) < 0.11, `hours ${before.hours} → ${after.hours}`)
      expect(after.by_kind.some((k) => k.kind === "Reading"), "Reading isn't among the kinds")
      await open("/insights?tab=trends")
      await has(`${after.done} things finished in 4 weeks`)
      await agree(t, after)
      await c("reopen", { id: item.id })
      await c("drop", { id: item.id })
    },
  },
  {
    name: "the tabs open Sleep, Meals and This week, and the address keeps the tab",
    async run({ open, click, until, has }) {
      await open("/insights?tab=trends")
      await click("Sleep")
      await until(`location.hash.includes("tab=sleep")`, 5000, "the Sleep tab")
      await has("Track my sleep")
      await click("Meals")
      await until(`location.hash.includes("tab=meals")`, 5000, "the Meals tab")
      await has("Track my meals")
      await click("This week")
      await until(`location.hash.includes("tab=week")`, 5000, "This week")
      await click("Trends")
      await has("How long things really take")
    },
  },
  {
    name: "the server refuses weeks out of range",
    async run({ request, expect }) {
      for (const weeks of [0, -1, 53]) {
        const r = await request("GET", `/api/q/insights?weeks=${weeks}`)
        expect(r.status === 422, `weeks=${weeks}: ${r.status}`)
      }
    },
  },
]
