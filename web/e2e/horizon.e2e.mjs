// Projects (tests/features.toml: horizon), Projects & exams: New project from a template makes a project with its steps
// (template_apply), listed on the shelf (projects); a step moved down is reordered (reorder); a step made not to wait
// for the one before (step_any_time); Save as template keeps its steps in their order for New project to offer
// (template_save), and its × removes it. Insights' Load ahead says each week's hours as the server has them (load).
// Checked on the page and on the server.

const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const TITLE = "E2E history essay"
const project = async (q) => (await q("projects")).find((p) => p.item.title === TITLE)
const steps = (p) => p.children.filter((c) => c.parent_id === p.item.id)
/** Presses the button labeled `label` on the step row showing `title`. */
const onStep = (evaluate, title, label) =>
  evaluate(`(() => {
    const rows = [...document.querySelectorAll("[role=dialog] *")].filter((el) => el.children.length && [...el.querySelectorAll("button")].some((b) => (b.getAttribute("aria-label") ?? "") === ${JSON.stringify(label)}) && el.innerText.includes(${JSON.stringify(title)}))
    const row = rows.sort((a, b) => a.innerText.length - b.innerText.length)[0]
    const b = row && [...row.querySelectorAll("button")].find((b) => (b.getAttribute("aria-label") ?? "") === ${JSON.stringify(label)})
    if (!b) return false
    b.click()
    return true
  })()`)

export default [
  {
    name: "New project from the Essay template makes a project with the template's steps, on the shelf",
    async run({ open, type, click, has, until, q, expect }) {
      expect(!(await project(q)), "a run before left the project")
      const essay = (await q("settings")).templates.Essay
      expect(essay?.length >= 2, "no Essay template in the sample")
      await open("/projects")
      await click("New project")
      await has("New project")
      await type("Name", TITLE)
      await click("Essay")
      await click("Create project")
      await settle(async () => !!(await project(q)), "the project on the server")
      const p = await project(q)
      expect(JSON.stringify(steps(p).map((s) => s.title)) === JSON.stringify(essay.map((s) => s.title)), `its steps are ${steps(p).map((s) => s.title)}`)
      await until(`location.hash.includes("id=${p.item.id}")`, 10_000, "its popup's address")
      for (const s of essay) await has(s.title, "[role=dialog]")
      await open("/projects")
      await has(TITLE)
    },
  },
  {
    name: "a step moved down is reordered on the server and in the popup",
    async run({ open, has, until, q, evaluate, expect }) {
      const p = await project(q)
      const [a, b] = steps(p)
      await open(`/projects?id=${p.item.id}`)
      await has(a.title, "[role=dialog]")
      expect(await onStep(evaluate, a.title, "Move down"), `no Move down on ${a.title}`)
      await settle(async () => steps(await project(q))[0].id === b.id && steps(await project(q))[1].id === a.id, `${b.title} before ${a.title} on the server`)
      await until(`(() => { const t = document.querySelector("[role=dialog]").innerText; return t.indexOf(${JSON.stringify(b.title)}) < t.indexOf(${JSON.stringify(a.title)}) })()`, 10_000, "the popup in the new order")
    },
  },
  {
    name: "a step made not to wait for the one before is planned any time; made to wait again, it waits",
    async run({ open, has, q, evaluate, expect }) {
      const p = await project(q)
      const [above, step] = steps(p)
      await open(`/projects?id=${p.item.id}`)
      await has(step.title, "[role=dialog]")
      expect(await onStep(evaluate, step.title, `${step.title} waits: after ${above.title}. Make it not wait`), "no button to make it not wait")
      await settle(async () => ((await project(q)).any_time ?? []).includes(step.id), "any time on the server")
      expect(await onStep(evaluate, step.title, `${step.title} doesn't wait for ${above.title}. Make it wait`), "no button to make it wait again")
      await settle(async () => !((await project(q)).any_time ?? []).includes(step.id), "waiting again on the server")
    },
  },
  {
    name: "Save as template keeps its steps in their order; New project offers it, and its × removes it",
    async run({ open, click, has, until, q, expect }) {
      const p = await project(q)
      await open(`/projects?id=${p.item.id}`)
      await has(TITLE, "[role=dialog]")
      await click("Save as template")
      await settle(async () => !!(await q("settings")).templates[TITLE], "the template on the server")
      const kept = (await q("settings")).templates[TITLE].map((s) => s.title)
      expect(JSON.stringify(kept) === JSON.stringify(steps(await project(q)).map((s) => s.title)), `kept in the order ${kept}`)
      await open("/projects")
      await click("New project")
      await has(kept.join(", then "))
      await click(`Remove template ${TITLE}`)
      await settle(async () => !(await q("settings")).templates[TITLE], "the template gone from the server")
      await until(`!document.body.innerText.includes(${JSON.stringify(kept.join(", then "))})`, 10_000, "the template gone from New project")
      await click("Cancel")
    },
  },
  {
    name: "Insights' Load ahead says each week's hours as the server has them, and work added counts",
    async run({ open, has, q, c, planned, day, expect }) {
      const p = await project(q)
      if (p) {
        // the project made above, done with: archived and deleted with its steps, as Finished does
        await c("project_archive", { id: p.item.id })
        await c("project_delete", { id: p.item.id })
      }
      await planned()
      const weeks = await q("load", { weeks: 8 })
      expect(weeks.length >= 2, `only ${weeks.length} weeks ahead`)
      const said = (w) => `${w.hours.toFixed(0)} / ${w.capacity.toFixed(0)} h`
      await open("/insights")
      for (const w of weeks.slice(0, 3)) await has(said(w))
      const made = (await c("add", { title: "E2E load essay", duration_min: 600, due: `${day(1)}T23:00`, firmness: "hard" })).result.item
      try {
        await planned()
        const after = await q("load", { weeks: 8 })
        expect(after[0].due.some((d) => d.item_id === made.id) || after[1].due.some((d) => d.item_id === made.id), "its due isn't marked in its week")
        expect(after[0].hours + after[1].hours > weeks[0].hours + weeks[1].hours + 5, `10 hours added moved the load from ${weeks[0].hours}+${weeks[1].hours} to ${after[0].hours}+${after[1].hours}`)
        await open("/insights")
        await has(said(after[0]))
      } finally {
        await c("drop", { id: made.id })
      }
    },
  },
]
