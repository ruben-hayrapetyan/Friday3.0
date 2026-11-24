// A project's options (tests/features.toml: project_options): in a project's popup on Projects & exams, Finish early
// and Pace, each opened, picked, said on the row at once, kept on the server and through a reload; finishing early a
// rule you then find in Rules; No and Not set taking them away.

const TITLE = "E2E Thesis chapter"

async function server(check, said, ms = 20_000) {
  for (let end = Date.now() + ms; ; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`the server didn't come to: ${said}`)
  }
}

const optionsOf = async (q, id) => (await q("project_options")).find((o) => o.id === id)
const project = async (q) => (await q("items", { status: "all", text: TITLE })).find((i) => i.title === TITLE && i.parent_id === null)
const row = (label) => `[...document.querySelectorAll("[role=dialog] button[aria-expanded]")].find((b) => (b.getAttribute("aria-label") || "").startsWith(${JSON.stringify(`${label}:`)}))?.getAttribute("aria-label")`

export default [
  {
    name: "Finish early: picked in the popup, said on its row, kept on the server and in Rules; No takes it away",
    async run({ open, click, has, until, q, c, day, expect }) {
      const made = (await c("add", { title: TITLE, preset: "Project", due: `${day(30)}T17:00`, firmness: "hard" })).result.item.id
      await c("add", { title: `${TITLE}: draft`, duration_min: 240, parent_id: made })
      await open(`/projects?id=${made}`)
      await has("Options", "[role=dialog]")
      expect((await until(row("Finish early"))).includes("No: it can take until its due"), "Finish early doesn't start at No")
      await click("Finish early:")
      await click("3 days early")
      await server(async () => (await optionsOf(q, made))?.early_days === 3, "3 days early")
      await has("A rule you'll find in Rules", "[role=dialog]")
      await until(`(${row("Finish early")} || "").startsWith("Finish early: 3 days early, by")`, 10_000, "the row saying 3 days early")
      const rule = (await q("rules")).find((r) => r.name === `you:project:${made}:early`)
      expect(rule?.enabled, "no rule of its own in Rules")
      await open("/rules")
      await has(TITLE, "body", 15_000)
      // a fresh load reads it from the server
      await open(`/projects?id=${made}`)
      await until(`(${row("Finish early")} || "").startsWith("Finish early: 3 days early")`, 10_000, "3 days early after a reload")
      await click("Finish early:")
      await click("No")
      await server(async () => !(await optionsOf(q, made)), "no options left")
      await until(`(${row("Finish early")} || "").includes("No: it can take until its due")`, 10_000, "the row back at No")
      expect(!(await q("rules")).some((r) => r.name === `you:project:${made}:early`), "its rule is still in Rules")
    },
  },
  {
    name: "Pace: Front-load it, then Toward the end, each the server's; Not set gives it back to its kind",
    async run({ open, click, until, q, expect }) {
      const made = (await project(q)).id
      await open(`/projects?id=${made}`)
      expect((await until(row("Pace"))) === "Pace: Not set", "Pace doesn't start at Not set")
      await click("Pace:")
      await click("Front-load it")
      await server(async () => (await optionsOf(q, made))?.pacing === "front", "front-loaded")
      await until(`${row("Pace")} === "Pace: Front-load it"`, 10_000, "the row saying Front-load it")
      await click("Pace:")
      await click("Toward the end")
      await server(async () => (await optionsOf(q, made))?.pacing === "back", "toward the end")
      await open(`/projects?id=${made}`)
      await until(`${row("Pace")} === "Pace: Toward the end"`, 10_000, "Toward the end after a reload")
      await click("Pace:")
      await click("Not set")
      await server(async () => !(await optionsOf(q, made)), "its kind's pace again")
      await until(`${row("Pace")} === "Pace: Not set"`, 10_000, "the row back at Not set")
    },
  },
  {
    name: "a project with no due date says so on Finish early, and its pace is still set on the server",
    async run({ open, click, until, q, c, expect }) {
      const made = (await c("add", { title: "E2E Garden plan", preset: "Project" })).result.item.id
      try {
        await open(`/projects?id=${made}`)
        expect(((await until(row("Finish early"))) ?? "").includes("It has no due date"), "a project with no due date doesn't say so")
        await click("Pace:")
        await click("Evenly")
        await server(async () => (await optionsOf(q, made))?.pacing === "linear", "evenly")
        await until(`${row("Pace")} === "Pace: Evenly"`, 10_000, "the row saying Evenly")
      } finally {
        await c("project_set", { id: made, pacing: "kind" })
        await c("drop", { id: made })
      }
    },
  },
]
