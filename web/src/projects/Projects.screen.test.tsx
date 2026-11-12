// Projects & exams over Alex's sample: no projects yet, two prelims with their prep. A new project from a template or
// blank, its steps (added, moved, timed, ticked off, waiting on one another, deleted), its timeline, saving it as a
// template, moving between projects; the exam cards (prep ticked off, opened, added, the day on the plan, exam focus)
// and a new exam with its prep.
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { beforeAll, describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { addDays } from "@/lib/time"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

type User = Awaited<ReturnType<typeof openFriday>>["user"]
const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title) as Item
/** Friday's today (its day ends in the small hours, not at midnight), `offset` days on. */
let today = ""
const day = (offset: number) => addDays(today, offset)
beforeAll(async () => {
  today = (await friday.q<{ today: string }>("calendar", { start: new Date().toISOString().slice(0, 10), days: "1" })).today
})

async function page(route = "/projects") {
  const f = await openFriday(route)
  await screen.findByText(/\d+ exams? ahead/, {}, { timeout: 10_000 })
  return f
}

/** Waits for `check` to pass, reading every query again each time as the live updates would (the screens have no
 * stream: setup.ts). */
async function live(client: Awaited<ReturnType<typeof openFriday>>["client"], check: () => unknown) {
  await waitFor(
    async () => {
      await client.invalidateQueries()
      await check()
    },
    { timeout: 8000, interval: 250 },
  )
}

/** A step's row in an open project, by its title. */
const step = (title: string) => {
  // its own title, not another step's "Waits on" button naming it
  const rows = screen.getAllByText(title).filter((el) => !el.closest("button")).map((el) => el.closest(".fr-row")).filter((r) => r?.querySelector('[aria-label="Delete step"]'))
  if (rows.length !== 1) throw new Error(`${rows.length} steps called ${title}`)
  return rows[0] as HTMLElement
}

async function newProject(user: User, name: string) {
  await user.click(screen.getAllByRole("button", { name: "New project" })[0])
  const dialog = await screen.findByRole("dialog")
  await user.type(within(dialog).getByPlaceholderText("Name, e.g. History essay"), name)
  return dialog
}

describe("projects", () => {
  it("has none yet, and says what a project is", async () => {
    await page()
    expect(screen.getByText("0 projects open", { exact: false })).toBeTruthy()
    expect(screen.getByText(/No projects yet\. A project is something with steps/)).toBeTruthy()
  })

  it("closes the new project dialog with Escape, Cancel or a click outside", async () => {
    const { user } = await page()
    await user.click(screen.getAllByRole("button", { name: "New project" })[0])
    expect(await screen.findByRole("dialog")).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    // The empty section's own button opens it too.
    await user.click(screen.getAllByRole("button", { name: "New project" }).at(-1) as HTMLElement)
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog")).toBeNull()
    await user.click(screen.getAllByRole("button", { name: "New project" })[0])
    const dialog = await screen.findByRole("dialog")
    await user.click(dialog.previousElementSibling as HTMLElement)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("makes a project from a template, with its tag, due and hours, and opens it", async () => {
    const { user, client } = await page()
    const dialog = await newProject(user, "Rocketry design review")
    expect(within(dialog).getByText("Outline, then Draft, then Revise")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: /Presentation/ }))
    await user.click(within(dialog).getByRole("button", { name: "Rocketry" }))
    await user.click(within(dialog).getByRole("button", { name: "Tomorrow" }))
    await user.click(within(dialog).getByRole("button", { name: "More" }))
    await user.click(within(dialog).getByRole("button", { name: "More" }))
    await user.click(within(dialog).getByRole("button", { name: "Less" }))
    expect(within(dialog).getByText("7h")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Create project" }))
    const made = await waitForSent("template_apply")
    expect(made.body).toEqual({ template: "Presentation", title: "Rocketry design review", hours: 7, due: `${day(1)}T23:59`, area: "Rocketry" })
    await waitFor(() => expect(window.location.hash).toMatch(/id=\d+/))
    await live(client, () => expect(screen.getByText(/^Due .* · 0 of 3 steps done · .* in all$/)).toBeTruthy())
    for (const s of ["Research", "Slides", "Rehearse"]) expect(step(s)).toBeTruthy()
    expect(screen.getByText("Timeline")).toBeTruthy()
    expect(screen.getByText("When each step is planned, up to the deadline")).toBeTruthy()
  })

  it("adds a step, moves it, and changes how long it takes", async () => {
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    const parent = await itemNamed("Rocketry design review")
    // ↩ twice adds it once (audit, 12 Nov: the second ↩ came before the first was saved, and added it again)
    await user.type(await screen.findByRole("textbox", { name: "Add a step" }), "Print handouts ~30m{Enter}{Enter}")
    expect((await waitForSent("add")).body).toEqual({ text: "Print handouts ~30m", parent_id: parent.id, area: "Rocketry" })
    await live(client, () => expect(step("Print handouts")).toBeTruthy())
    await waitFor(() => expect((screen.getByRole("textbox", { name: "Add a step" }) as HTMLInputElement).value).toBe(""))
    expect(sent.filter((s) => s.name === "add")).toHaveLength(1)
    await user.click(within(step("Print handouts")).getByRole("button", { name: "Move up" }))
    const order = await waitForSent("reorder")
    expect(order.body).toMatchObject({ parent_id: parent.id })
    expect((order.body as { ids: number[] }).ids.at(-2)).toBe((await itemNamed("Print handouts")).id)
    // The first can't go up, nor the last down.
    await live(client, () => expect(within(step("Research")).getByRole("button", { name: "Move up" }).style.opacity).toBe("0.25"))
    sent.length = 0
    await user.click(within(step("Research")).getByRole("button", { name: "Move up" }))
    await user.click(within(step("Rehearse")).getByRole("button", { name: "Move down" }))
    expect(sent.filter((s) => s.name === "reorder")).toHaveLength(0)
    await user.click(within(step("Research")).getByRole("button", { name: "Move down" }))
    await waitForSent("reorder")
    const research = await itemNamed("Research")
    await user.click(within(step("Research")).getByRole("button", { name: "Longer" }))
    expect((await waitForSent("edit")).body).toEqual({ id: research.id, duration_min: (research.duration_min ?? 60) + 15 })
    await live(client, async () => expect((await itemNamed("Research")).duration_min).toBe((research.duration_min ?? 60) + 15))
    sent.length = 0
    await user.click(within(step("Research")).getByRole("button", { name: "Shorter" }))
    expect((await waitForSent("edit")).body).toMatchObject({ id: research.id })
  })

  it("ticks a step done and opens it again", async () => {
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await waitFor(() => expect(step("Slides")).toBeTruthy())
    const slides = await itemNamed("Slides")
    await user.click(within(step("Slides")).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: slides.id })
    await live(client, () => expect(screen.getByText(/1 of 4 steps done/)).toBeTruthy())
    await user.click(within(step("Slides")).getByRole("checkbox", { name: "Mark not done" }))
    expect((await waitForSent("reopen")).body).toEqual({ id: slides.id })
    await live(client, () => expect(screen.getByText(/0 of 4 steps done/)).toBeTruthy())
  })

  it("makes a step wait on another from its list of the other steps", async () => {
    // a Presentation's steps each wait on the one before: Rehearse on Slides, Slides on Research
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await live(client, () => expect(within(step("Rehearse")).getByText(/Waiting on Slides/)).toBeTruthy())
    const [rehearse, research] = [await itemNamed("Rehearse"), await itemNamed("Research")]
    await user.click(within(step("Rehearse")).getByTitle("Slides"))
    expect(screen.getByText("Rehearse waits on")).toBeTruthy()
    expect(within(step("Rehearse")).queryByRole("button", { name: "Rehearse" })).toBeNull()
    await user.click(within(step("Rehearse")).getByRole("button", { name: "Research" }))
    expect((await waitForSent("depend")).body).toEqual({ item_id: rehearse.id, depends_on_id: research.id })
    await user.click(within(step("Rehearse")).getByRole("button", { name: "Done" }))
    expect(screen.queryByText("Rehearse waits on")).toBeNull()
  })

  it("shows what a step waits on, won't let it loop, and lets it go", async () => {
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await live(client, () => expect(within(step("Rehearse")).getByText(/Waiting on .*Slides/)).toBeTruthy())
    // Slides can't wait on Rehearse: Rehearse already waits on it
    await user.click(within(step("Slides")).getByTitle("Research"))
    const loop = within(step("Slides")).getByRole("button", { name: /Rehearse/ })
    expect(loop.textContent).toContain("would loop")
    await user.click(within(step("Slides")).getByRole("button", { name: "Done" }))
    // and Rehearse lets Slides go
    await user.click(within(step("Rehearse")).getByTitle(/Slides/))
    await user.click(within(step("Rehearse")).getAllByRole("button", { name: "Slides" }).at(-1) as HTMLElement)
    expect((await waitForSent("undepend")).body).toEqual({ item_id: (await itemNamed("Rehearse")).id, depends_on_id: (await itemNamed("Slides")).id })
  })

  it("saves a project as a template and deletes a step", async () => {
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await user.click(await screen.findByRole("button", { name: /Save as template/ }))
    expect((await waitForSent("template_save")).body).toEqual({ name: "Rocketry design review", project_id: (await itemNamed("Rocketry design review")).id })
    expect(await screen.findByText(/New project offers it/)).toBeTruthy()
    const handouts = await itemNamed("Print handouts")
    await user.click(within(step("Print handouts")).getByRole("button", { name: "Delete step" }))
    expect((await waitForSent("drop")).body).toEqual({ id: handouts.id })
    await live(client, () => expect(screen.queryByText("Print handouts")).toBeNull())
  })

  it("makes a blank project, moves between projects, and goes back to them all", async () => {
    const { user, client } = await page()
    const dialog = await newProject(user, "Lab notebook cleanup")
    expect(within(dialog).getByText("Add your own steps")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: /Blank/ }))
    await user.click(within(dialog).getByRole("button", { name: "No due date" }))
    await user.click(within(dialog).getByRole("button", { name: "Create project" }))
    expect((await waitForSent("add")).body).toEqual({ title: "Lab notebook cleanup", preset: "Project", due: null, area: null, duration_min: 360 })
    await live(client, () => expect(screen.getByText(/0 of 0 steps done/)).toBeTruthy())
    expect(screen.queryByRole("button", { name: /Save as template/ })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Project" }))
    await user.click(screen.getByRole("option", { name: "Rocketry design review" }))
    expect(await screen.findByText(/of 3 steps done/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Projects & exams" }))
    await waitFor(() => expect(window.location.hash).not.toContain("id="))
    expect(screen.getByText(/2 projects open/)).toBeTruthy()
    const card = screen.getByRole("button", { name: /Rocketry design review/ })
    expect(within(card).getByText(/of 3 steps/)).toBeTruthy()
    expect(within(card).getByText("Next")).toBeTruthy()
    expect(within(card).getByText(/^Due /)).toBeTruthy()
    // The dashed card at the end makes another.
    await user.click(screen.getAllByRole("button", { name: "New project" }).at(-1) as HTMLElement)
    expect(await screen.findByRole("dialog")).toBeTruthy()
  })
})

describe("exams", () => {
  it("shows the prelims ahead, each with its prep and how ready you are", async () => {
    await page()
    expect(screen.getByText(/2 exams ahead/)).toBeTruthy()
    const phys = screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })
    expect(within(phys).getByText("Prep: PHYS 1112 Prelim 2")).toBeTruthy()
    expect(within(phys).getByRole("progressbar")).toBeTruthy()
    expect(within(phys).getByRole("textbox", { name: "Add prep for PHYS 1112 Prelim 2" })).toBeTruthy()
  })

  it("adds prep to an exam, due when it starts", async () => {
    const { user } = await page()
    const exam = (await friday.q<{ item: Item }[]>("exams")).find((e) => e.item.title === "PHYS 1112 Prelim 2")?.item as Item
    const phys = screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })
    const line = within(phys).getByRole("textbox", { name: "Add prep for PHYS 1112 Prelim 2" })
    await user.type(line, "practice prelim ~2h")
    await user.click(within(phys).getByRole("button", { name: "Add" }))
    expect((await waitForSent("add")).body).toEqual({ text: "practice prelim ~2h", preset: "Exam prep", due: exam.start, area: "PHYS 1112", before: [exam.id] })
    await waitFor(() => expect((line as HTMLInputElement).value).toBe(""))
    sent.length = 0
    await user.type(line, "formula sheet ~30m{Enter}{Enter}")
    expect((await waitForSent("add")).body).toMatchObject({ text: "formula sheet ~30m" })
    await waitFor(() => expect((line as HTMLInputElement).value).toBe(""))
    expect(sent.filter((s) => s.name === "add")).toHaveLength(1)
  })

  it("ticks prep done and opens it again", async () => {
    const { user, client } = await page()
    const phys = screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })
    const prep = within(phys).getByText("Prep: PHYS 1112 Prelim 2").closest(".fr-row") as HTMLElement
    await user.click(within(prep).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: (await itemNamed("Prep: PHYS 1112 Prelim 2")).id })
    await live(client, () => expect(within(screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })).getAllByRole("checkbox", { name: "Mark not done" }).length).toBeGreaterThan(0))
    await user.click(within(screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })).getAllByRole("checkbox", { name: "Mark not done" })[0])
    expect((await waitForSent("reopen")).body).toEqual({ id: (await itemNamed("Prep: PHYS 1112 Prelim 2")).id })
  })

  it("opens a piece of prep on the To-do page", async () => {
    const { user } = await page()
    const phys = screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })
    await user.click(within(phys).getAllByTitle("Open")[0])
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/todo\?item=\d+$/))
  })

  it("shows the exam's day on the plan", async () => {
    const { user } = await page()
    const phys = screen.getByRole("article", { name: /^PHYS 1112 Prelim 2/ })
    await user.click(within(phys).getByRole("button", { name: "See the day" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("offers to focus on each exam's course before it, and says so once it's on", async () => {
    const first = await page()
    await first.user.click(screen.getByRole("button", { name: /Focus on each exam before it/ }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
    first.unmount()
    const settings = await friday.q<{ exam_focus: Record<string, unknown> }>("settings")
    await friday.c("settings_set", { key: "exam_focus", value: { ...settings.exam_focus, on: true, days_before: 3 } })
    await page()
    expect(await screen.findByText("Exam focus is on, 3 days before each")).toBeTruthy()
    expect(screen.getAllByText(/other courses' work waits until after it\./).length).toBeGreaterThan(0)
  })

  it("folds exams more than three weeks off under a line that opens them", async () => {
    await friday.c("add", { title: "CHEM 2090 Final", preset: "Exam", start: `${day(35)}T09:00`, end: `${day(35)}T11:30`, area: "CHEM 2090" })
    const { user } = await page()
    const more = await screen.findByRole("button", { name: /1 more later this term: CHEM 2090 Final/ }, { timeout: 5000 })
    expect(screen.queryByRole("article", { name: /^CHEM 2090 Final/ })).toBeNull()
    await user.click(more)
    expect(screen.getByRole("article", { name: /^CHEM 2090 Final/ })).toBeTruthy()
    expect(screen.getByRole("button", { name: /Later this term/ })).toBeTruthy()
  })

  it("closes the new exam dialog with Escape, Cancel or a click outside", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    expect(await screen.findByRole("dialog", { name: "New exam" })).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull())
    await user.click(screen.getByRole("button", { name: "New exam" }))
    await user.click(within(await screen.findByRole("dialog", { name: "New exam" })).getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    await user.click((await screen.findByRole("dialog", { name: "New exam" })).previousElementSibling as HTMLElement)
    expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull()
  })

  it("adds an exam with its prep, said once with one Undo", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    const add = within(dialog).getByRole("button", { name: "Add exam" }) as HTMLButtonElement
    expect(add.disabled).toBe(true)
    await user.type(within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2"), "ENGL 1170 Midterm")
    const date = within(dialog).getByLabelText("Day") as HTMLInputElement
    expect(date.value).toBe(day(7)) // a week off, to start with
    fireEvent.change(date, { target: { value: day(10) } })
    await user.clear(within(dialog).getByRole("textbox", { name: "Starts" }))
    await user.keyboard("2pm")
    await user.click(within(dialog).getByRole("button", { name: "2h" }))
    await user.click(within(dialog).getByRole("button", { name: "Rocketry" }))
    await user.click(within(dialog).getByRole("button", { name: "No tag" }))
    await user.click(within(dialog).getByRole("button", { name: "ENGL 1170" }))
    await user.click(within(dialog).getByRole("button", { name: "More prep" }))
    await user.click(within(dialog).getByRole("button", { name: "Less prep" }))
    await user.click(within(dialog).getByRole("button", { name: "Less prep" }))
    expect(within(dialog).getByText("3h", { selector: "span" })).toBeTruthy()
    await user.click(add)
    await waitFor(() => expect(sent.filter((s) => s.name === "add")).toHaveLength(2), { timeout: 5000 })
    const [exam, prep] = sent.filter((s) => s.name === "add").map((s) => s.body as Record<string, unknown>)
    expect(exam).toEqual({ title: "ENGL 1170 Midterm", preset: "Exam", start: `${day(10)}T14:00`, end: `${day(10)}T16:00`, area: "ENGL 1170" })
    expect(prep).toMatchObject({ title: "Prep: ENGL 1170 Midterm", preset: "Exam prep", due: `${day(10)}T14:00`, duration_min: 180, area: "ENGL 1170", before: [expect.any(Number)] })
    expect(await screen.findByText("Exam and its prep added")).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull())
    await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
    await waitFor(() => expect(sent.filter((s) => s.name === "undo")).toHaveLength(2), { timeout: 5000 })
  })

  it("adds an exam with no prep", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    await user.type(within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2"), "Rocketry safety quiz")
    for (let n = 0; n < 4; n++) await user.click(within(dialog).getByRole("button", { name: "Less prep" }))
    expect(within(dialog).getByText("None")).toBeTruthy()
    // a double click adds it once (audit, 12 Nov: it made two)
    await user.dblClick(within(dialog).getByRole("button", { name: "Add exam" }))
    expect(await screen.findByText("Exam added")).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull())
    expect(sent.filter((s) => s.name === "add")).toHaveLength(1)
  })

  it("says there are none ahead once they're gone, and offers to add one", async () => {
    for (const e of await friday.q<{ item: Item }[]>("exams")) await friday.c("drop", { id: e.item.id })
    const { user } = await page()
    expect(await screen.findByText(/No exams ahead\. They come in from your class calendar/)).toBeTruthy()
    await user.click(screen.getAllByRole("button", { name: "New exam" }).at(-1) as HTMLElement)
    expect(await screen.findByRole("dialog", { name: "New exam" })).toBeTruthy()
  })
})
