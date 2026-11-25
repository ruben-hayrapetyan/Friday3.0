// Ongoing projects (tests/features.toml: ongoing), Projects & exams: New ongoing makes hours a week with no deadline
// (ongoing_add), opened in its popup and on the Ongoing shelf (ongoing_projects); its hours, priority and pause are
// changed from its rows (ongoing_set); Delete asks, then takes it off the shelf, the server and the plan
// (ongoing_delete). Checked on the page and on the server.

const settle = async (check, what, ms = 20_000) => {
  for (let end = Date.now() + ms; Date.now() < end; await new Promise((r) => setTimeout(r, 300))) if (await check()) return
  throw new Error(`waited ${ms / 1000}s for ${what}`)
}
const mine = async (q) => (await q("ongoing_projects")).find((o) => o.title === "E2E guitar")
/** Presses an option of the open row, inside the popup. */
const pick = (evaluate, group, label) =>
  evaluate(`(() => {
    const g = document.querySelector('[role=dialog] [role=radiogroup][aria-label=${JSON.stringify(group)}], [role=radiogroup][aria-label=${JSON.stringify(group)}]')
    const b = g && [...g.querySelectorAll("button")].find((b) => b.innerText.trim().split("\\n")[0].trim() === ${JSON.stringify(label)})
    if (!b) return false
    b.click()
    return true
  })()`)
const row = (evaluate, label) =>
  evaluate(`(() => { const b = [...document.querySelectorAll("button[aria-expanded]")].find((b) => (b.getAttribute("aria-label") ?? "").startsWith(${JSON.stringify(label + ":")})); if (!b) return false; b.click(); return true })()`)

export default [
  {
    name: "New ongoing makes hours a week with no deadline, opened in its popup and on the shelf",
    async run({ open, type, click, has, until, q, expect }) {
      expect(!(await mine(q)), "a run before left E2E guitar")
      await open("/projects")
      await click("New ongoing project")
      await has("Hours a week with no deadline")
      await type("Name", "E2E guitar")
      await click("Create ongoing project")
      await settle(async () => !!(await mine(q)), "the ongoing project on the server")
      const o = await mine(q)
      expect(o.hours_per_week === 3 && o.active, `made as ${JSON.stringify({ hours: o.hours_per_week, active: o.active })}`)
      await until(`location.hash.includes("ongoing=${o.id}")`, 10_000, "its popup's address")
      await has("E2E guitar")
      await has("3h a week")
      await open("/projects")
      await has("E2E guitar", "[aria-label=Ongoing]")
    },
  },
  {
    name: "its hours, priority and pause change from its rows, on the server and in the popup",
    async run({ open, click, has, until, q, evaluate, expect }) {
      const o = await mine(q)
      await open(`/projects?ongoing=${o.id}`)
      await has("E2E guitar")
      expect(await row(evaluate, "Hours a week"), "no Hours a week row")
      await click("5h") // a chip under the row
      await settle(async () => (await mine(q)).hours_per_week === 5, "5 hours a week on the server")
      await has("5h a week")
      expect(await row(evaluate, "Priority"), "no Priority row")
      expect(await pick(evaluate, "Priority", "High"), "no High to pick")
      await settle(async () => (await mine(q)).priority === 4, "high priority on the server")
      await until(`[...document.querySelectorAll("button[aria-expanded]")].some((b) => b.getAttribute("aria-label") === "Priority: High")`, 10_000, "the Priority row saying High")
      expect(await row(evaluate, "Paused"), "no Paused row")
      expect(await pick(evaluate, "Paused", "Until I resume it"), "no Until I resume it")
      await settle(async () => (await mine(q)).active === false, "paused on the server")
      await has("Paused until you resume it: no time is planned for it.")
      expect(await row(evaluate, "Paused"), "no Paused row")
      expect(await pick(evaluate, "Paused", "No"), "no No to pick")
      await settle(async () => (await mine(q)).active === true, "resumed on the server")
    },
  },
  {
    name: "Delete asks first, then takes it off the shelf and the server",
    async run({ open, click, has, until, q, expect }) {
      const o = await mine(q)
      await open(`/projects?ongoing=${o.id}`)
      await has("E2E guitar")
      await click("Delete")
      await click("Delete it")
      await settle(async () => !(await mine(q)), "the ongoing project gone from the server")
      await open("/projects")
      await has("Projects & exams")
      await until(`!(document.querySelector("[aria-label=Ongoing]")?.innerText ?? "").includes("E2E guitar")`, 10_000, "E2E guitar gone from the shelf")
      expect(!(await q("plan")).blocks.some((b) => b.title === "E2E guitar"), "its time is still planned")
    },
  },
]
