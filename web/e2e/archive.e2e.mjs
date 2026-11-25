// Finished projects (tests/features.toml: archive), on Projects: Archive in a project's popup puts its open steps away
// and moves it under Finished, with its steps and what it took; Open again brings it back with its steps; Delete asks
// first (Keep it keeps it) and then deletes it with its steps (dropped: Undo can bring them back), on the page and on
// the server.

const TITLE = "E2E Seminar paper"
const finished = async (q) => (await q("projects_finished")).find((f) => f.title === TITLE)
const waitFor = async (check, ms = 10_000) => {
  for (const end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
  }
  return null
}
let project
let steps

export default [
  {
    name: "Archive in a project's popup moves it under Finished, its open steps put away",
    async run({ open, click, has, gone, q, c, day, expect, planned }) {
      project = (await c("template_apply", { template: "Essay", title: TITLE, hours: 6, due: `${day(12)}T17:00` })).result.item
      const children = (await q("items", { status: "all" })).filter((i) => i.parent_id === project.id)
      steps = children.filter((i) => i.status === "todo").map((i) => i.id) // Outline, Draft, Revise
      expect(steps.length === 3, `the essay has ${steps.length} open steps, not 3`)
      await planned()
      await open(`/projects?id=${project.id}`)
      await has(TITLE, "[role=dialog]")
      await click("Archive")
      await has("it's under Finished")
      await gone(TITLE, "[role=dialog]")
      const shelf = await waitFor(() => finished(q))
      expect(shelf, "the server has no finished project after Archive")
      expect(shelf.steps === children.length, `Finished says ${shelf.steps} steps, not ${children.length}`)
      const after = await q("items", { status: "all" })
      expect(after.find((i) => i.id === project.id).status === "done", "the project isn't done")
      expect(!after.some((i) => steps.includes(i.id) && i.status === "todo"), "its steps are still open")
      expect(!(await q("projects")).some((p) => p.item.id === project.id), "it's still among the projects")
      await has("Finished", "section[aria-label=Finished]")
      await click("Finished")
      await has(TITLE, "section[aria-label=Finished]")
      await has(`${children.length} steps`, "section[aria-label=Finished]")
      await has("planned", "section[aria-label=Finished]")
    },
  },
  {
    name: "Open again brings it back from Finished with its steps",
    async run({ open, click, has, gone, q, expect }) {
      await open("/projects")
      await click("Finished")
      await has(TITLE, "section[aria-label=Finished]")
      await click("Open again")
      await waitFor(async () => !(await finished(q)))
      expect(!(await finished(q)), "it's still finished on the server")
      const back = await waitFor(async () => (await q("projects")).find((p) => p.item.id === project.id))
      expect(back, "it isn't among the projects again")
      const open_ = (await q("items", { status: "all" })).filter((i) => i.parent_id === project.id && i.status === "todo").map((i) => i.id).sort()
      expect(JSON.stringify(open_) === JSON.stringify([...steps].sort()), `its steps open again: ${open_}`)
      await gone(TITLE, "section[aria-label=Finished]").catch(() => {}) // the shelf may be gone with it
      await has(TITLE, "main")
    },
  },
  {
    name: "Delete asks first: Keep it keeps it; Delete it deletes it and its steps",
    async run({ open, click, has, gone, q, c, expect }) {
      await c("project_archive", { id: project.id })
      await open("/projects")
      await click("Finished")
      await click(`Delete ${TITLE}`)
      await has("Delete it", "section[aria-label=Finished]")
      await click("Keep it")
      await gone("Delete it", "section[aria-label=Finished]")
      expect(await finished(q), "Keep it deleted it")
      await click(`Delete ${TITLE}`)
      await click("Delete it")
      await gone(TITLE, "main")
      expect(await waitFor(async () => !(await finished(q))), "it's still under Finished on the server")
      const all = await q("items", { status: "all" })
      for (const id of [project.id, ...steps]) expect(all.find((i) => i.id === id)?.status === "dropped", `item ${id} isn't deleted`)
      expect(!(await q("projects")).some((p) => p.item.id === project.id), "it's among the projects again")
    },
  },
  {
    name: "the server refuses archiving or deleting what isn't a project",
    async run({ c, request, expect }) {
      const task = (await c("add", { title: "E2E email the TA", preset: "Errand", duration_min: 30 })).result.item
      try {
        for (const name of ["project_archive", "project_delete", "project_unarchive"]) {
          const refused = await request("POST", `/api/c/${name}`, { id: task.id })
          expect(refused.status === 422, `${name} of a to-do: ${JSON.stringify(refused)}`)
        }
        const none = await request("POST", "/api/c/project_delete", { id: 999_999 })
        expect(none.status === 422, `deleting nothing: ${JSON.stringify(none)}`)
      } finally {
        await c("drop", { id: task.id })
      }
    },
  },
]
