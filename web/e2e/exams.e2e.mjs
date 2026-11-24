// Exams and their prep (tests/features.toml: exams): New exam on Projects & exams, typed and added with its prep; the
// exam on the shelf and in its popup; prep added, ticked off and back, and deleted there; and its own days before it
// for other classes to wait, and back to your rule. Each step checked on the page and on the server.

const TITLE = "E2E CHEM 2090 Prelim"

async function server(check, said, ms = 20_000) {
  for (let end = Date.now() + ms; ; await new Promise((r) => setTimeout(r, 250))) {
    const found = await check()
    if (found) return found
    if (Date.now() > end) throw new Error(`the server didn't come to: ${said}`)
  }
}

const theExam = async (q) => (await q("exams")).find((e) => e.item.title === TITLE)
const tap = (until, selector, said = selector) =>
  until(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true })()`, 10_000, said)
const minutes = (a, b) => (new Date(b) - new Date(a)) / 60_000

export default [
  {
    name: "Cancel in New exam adds nothing",
    async run({ open, click, type, q, expect }) {
      await open("/projects")
      await click("New exam")
      await type("Name, e.g. MATH", "E2E Never added")
      await click("Cancel")
      expect(!(await q("exams")).some((e) => e.item.title === "E2E Never added"), "Cancel added the exam")
    },
  },
  {
    name: "New exam: named and added, it's on the server with its prep due at its start, and on the shelf",
    async run({ open, click, type, has, until, q, expect }) {
      await open("/projects")
      await click("New exam")
      await has("Prep it needs", "[role=dialog]")
      await type("Name, e.g. MATH", TITLE)
      await click("Add exam")
      const exam = await server(() => theExam(q), "the new exam among the exams")
      expect(exam.item.preset === "Exam", `its kind is ${exam.item.preset}`)
      expect(minutes(exam.item.start, exam.item.end) === 90, `it lasts ${minutes(exam.item.start, exam.item.end)} min, not 90`)
      expect(exam.item.start.endsWith("T09:00"), `it starts ${exam.item.start}, not at 9am`)
      expect(exam.prep.length === 1, `${exam.prep.length} prep`)
      const prep = exam.prep[0].item
      expect(prep.title === `Prep: ${TITLE}` && prep.duration_min === 240 && prep.due === exam.item.start, `its prep: ${JSON.stringify(prep).slice(0, 200)}`)
      expect(exam.remaining_min === 240, `${exam.remaining_min} min of prep left, not 240`)
      await has(TITLE, "[aria-label='With a deadline']")
      await tap(until, `[aria-label='With a deadline'] [role=button][aria-label^="${TITLE}"]`, "its row on the shelf")
      await until(`!!document.querySelector('[role=dialog] [aria-label="Its prep"]')`, 10_000, "its popup with its prep")
      await has(`Prep: ${TITLE}`, "[role=dialog]")
      await has("of 4h done", "[role=dialog]")
    },
  },
  {
    name: "in its popup, Add prep adds one; its tick finishes it and opens it again; Delete takes it away",
    async run({ open, click, type, has, until, q, expect }) {
      const exam = await theExam(q)
      await open(`/projects?exam=${exam.item.id}`)
      await click("Add prep")
      await type("New prep", "E2E practice exam", { enter: true })
      const added = await server(async () => (await theExam(q)).prep.find((p) => p.item.title === "E2E practice exam"), "the new prep")
      expect(added.item.due === exam.item.start && added.item.preset === "Exam prep", `the new prep: ${JSON.stringify(added.item).slice(0, 200)}`)
      await has("E2E practice exam", "[aria-label='Its prep']")
      const box = `[aria-label='Its prep'] [role=listitem][aria-label="E2E practice exam"] [role=checkbox]`
      await tap(until, box, "its tick")
      await server(async () => (await theExam(q)).prep.find((p) => p.item.id === added.item.id)?.item.status === "done", "the prep done")
      await until(`document.querySelector(${JSON.stringify(box)})?.getAttribute("aria-checked") === "true"`, 10_000, "its tick showing done")
      expect((await theExam(q)).done_min >= added.item.duration_min, "its time doesn't count as put in")
      await tap(until, box, "its tick again")
      await server(async () => (await theExam(q)).prep.find((p) => p.item.id === added.item.id)?.item.status === "todo", "the prep open again")
      await click("Delete E2E practice exam")
      await server(async () => !(await theExam(q)).prep.some((p) => p.item.id === added.item.id), "the prep gone")
      const gone = (await q("items", { status: "all" })).find((i) => i.id === added.item.id)
      expect(gone?.status === "dropped", `deleted, it's ${gone?.status}`)
      await until(`!document.querySelector('[aria-label="Its prep"] [role=listitem][aria-label="E2E practice exam"]')`, 10_000, "its row gone")
    },
  },
  {
    name: "Before this exam: its own days are kept on the server and said; As your other exams follows the rule again",
    async run({ open, click, has, until, q, expect }) {
      const exam = await theExam(q)
      await open(`/projects?exam=${exam.item.id}`)
      await has("Before this exam", "[role=dialog]")
      await click("Before this exam:")
      await click("The day before")
      const own = await server(async () => ((e) => e.focus_own && e.focus_days === 1 && e)(await theExam(q)), "its own day before")
      expect(own.focus_from?.slice(0, 10) < exam.item.start.slice(0, 10), `its focus starts ${own.focus_from}`)
      expect((await q("settings")).exam_focus_each?.[String(exam.item.id)] === 1, "not kept in exam_focus_each")
      await has("Only this class's work, the day before", "[role=dialog]")
      await open(`/projects?exam=${exam.item.id}`)
      await has("Only this class's work, the day before", "[role=dialog]")
      await click("Before this exam:")
      await click("As your other exams")
      await server(async () => !(await theExam(q)).focus_own, "following the rule again")
      expect(!(String(exam.item.id) in ((await q("settings")).exam_focus_each ?? {})), "its own days are still kept")
      const rule = (await theExam(q)).rule_days
      const words = rule == null ? "Other classes' work goes on as usual" : `Only this class's work, ${rule === 0 ? "on its day, until it starts" : rule === 1 ? "the day before" : `${rule} days before`}`
      await until(`document.querySelector('[role=dialog] button[aria-label^="Before this exam:"]')?.getAttribute("aria-label") === ${JSON.stringify(`Before this exam: ${words}`)}`, 10_000, `the row saying "${words}", as the rule gives it`)
    },
  },
]
