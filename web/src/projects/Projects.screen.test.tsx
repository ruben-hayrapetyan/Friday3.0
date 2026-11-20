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
  await screen.findByText(/\d+ with a deadline/, {}, { timeout: 10_000 })
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

/** A length field (todo/Pickers LengthField): opened, then a common amount picked, or one typed and Enter. */
async function setLength(user: User, scope: HTMLElement, label: string, choice: { pick: string } | { type: string }) {
  const field = within(scope).getByRole("button", { name: new RegExp(`^${label}: `) })
  await user.click(field)
  const picker = (await screen.findAllByRole("dialog", { name: label })).at(-1) as HTMLElement
  if ("pick" in choice) await user.click(within(picker).getByRole("button", { name: choice.pick }))
  else await user.type(within(picker).getByRole("textbox", { name: `${label}, typed` }), `${choice.type}{Enter}`)
  await waitFor(() => expect(field.getAttribute("aria-expanded")).toBe("false")) // a choice closes it
}

async function newProject(user: User, name: string) {
  await user.click(screen.getAllByRole("button", { name: "New project" })[0])
  const dialog = await screen.findByRole("dialog")
  await user.type(within(dialog).getByPlaceholderText("Name, e.g. History essay"), name)
  return dialog
}

describe("projects", () => {
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
    await user.click(await within(dialog).findByRole("button", { name: "Rocketry" }, { timeout: 10_000 })) // the tags load after the dialog opens
    await user.click(within(dialog).getByRole("button", { name: "Tomorrow" }))
    // the due chosen, said as a plain sentence: not "Now: …" (read as the time now) nor in the mono of figures (17 Nov)
    const reading = within(dialog).getByText(/^Due \w{3} \d+ \w{3}, 11:59pm \(tomorrow\)$/)
    expect(reading.className).not.toMatch(/tnum|fr-mono/)
    // "About how long, in all" over its field, as Tag and Due, not squeezed beside it onto two lines
    const label = within(dialog).getByText("About how long, in all")
    expect((label.parentElement as HTMLElement).style.flexDirection).toBe("column")
    expect(label.style.width).toBe("")
    await setLength(user, dialog, "About how long, in all", { type: "7h" })
    expect(within(dialog).getByRole("button", { name: "About how long, in all: 7h" })).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Create project" }))
    const made = await waitForSent("template_apply")
    expect(made.body).toEqual({ template: "Presentation", title: "Rocketry design review", hours: 7, due: `${day(1)}T23:59`, area: "Rocketry" })
    await waitFor(() => expect(window.location.hash).toMatch(/id=\d+/))
    await live(client, () => expect(screen.getByText(/^0 of 3 steps done · .* in all$/)).toBeTruthy())
    expect(screen.getByRole("button", { name: /^Due: (?!No due date)/ })).toBeTruthy() // its due, in its row
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
    // moved at once, before the server answers (17 Nov: "make the reordering instant")
    expect(step("Print handouts").compareDocumentPosition(step("Rehearse")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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
    // a step's length: a common amount picked, or any typed (16 Nov: not a quarter hour at a time)
    await setLength(user, step("Research"), "Length of Research", { pick: "2h" })
    expect((await waitForSent("edit")).body).toEqual({ id: research.id, duration_min: 120 })
    await live(client, async () => expect((await itemNamed("Research")).duration_min).toBe(120))
    sent.length = 0
    await setLength(user, step("Research"), "Length of Research", { type: "12h" })
    expect((await waitForSent("edit")).body).toEqual({ id: research.id, duration_min: 720 })
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

  // 19 Nov, a user's notes: "then" / "any time" between two steps read as the upper one's; your choice: say it on the
  // waiting step, naming the one above: "after <step>" or "doesn't wait"
  it("chains the steps in their order, each saying it comes after the one above, and one stops waiting with a click", async () => {
    // 17 Nov, your choice: a project's order is its chain; no "Waits on" of its own
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await live(client, () => expect(step("Rehearse")).toBeTruthy())
    expect(screen.queryByText("Waits on")).toBeNull()
    const rehearse = await itemNamed("Rehearse")
    const link = screen.getByRole("button", { name: /^Rehearse waits: after .+\. Make it not wait$/ })
    const above = /^Rehearse waits: after (.+)\. Make it not wait$/.exec(link.getAttribute("aria-label") ?? "")?.[1] as string
    expect(link.textContent).toBe(`after ${above}`)
    // 20 Nov, a user's notes: "dependence relationship between sub-tasks is placed directly on the separating line":
    // the line is drawn above the link, and its step's row draws none of its own under it
    expect(link.classList.contains("fr-row")).toBe(true)
    const row = link.nextElementSibling as HTMLElement
    expect(row.hasAttribute("data-step-row") && row.style.boxShadow).toBe("none")
    expect(link.style.marginBottom).not.toBe("-8px")
    await user.click(link)
    // at once, before the server answers
    expect(screen.getByRole("button", { name: `Rehearse doesn't wait for ${above}. Make it wait` }).textContent).toBe("doesn't wait")
    expect((await waitForSent("step_any_time")).body).toEqual({ id: rehearse.id, any_time: true })
    await waitFor(async () => expect((await friday.q<{ item: { id: number }; any_time: number[] }[]>("projects")).find((x) => x.item.id === rehearse.parent_id)?.any_time).toContain(rehearse.id))
    await user.click(screen.getByRole("button", { name: `Rehearse doesn't wait for ${above}. Make it wait` }))
    expect((await waitForSent("step_any_time")).body).toEqual({ id: rehearse.id, any_time: false })
    expect(await screen.findByRole("button", { name: `Rehearse waits: after ${above}. Make it not wait` })).toBeTruthy()
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

  it("asks before saving over a template of the same name", async () => {
    // 15 Nov, a client: saving again wrote over the one saved before without a word
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    await live(client, () => expect(screen.getByRole("button", { name: /Save as template/ })).toBeTruthy())
    sent.length = 0
    await user.click(screen.getByRole("button", { name: /Save as template/ }))
    expect(screen.getByText("A template called “Rocketry design review” is saved already. Replace it?")).toBeTruthy()
    expect(sent.filter((s) => s.name === "template_save")).toHaveLength(0)
    await user.click(screen.getByRole("button", { name: "Keep it" }))
    expect(screen.queryByText(/Replace it\?/)).toBeNull()
    expect(sent.filter((s) => s.name === "template_save")).toHaveLength(0)
    await user.click(screen.getByRole("button", { name: /Save as template/ }))
    await user.click(screen.getByRole("button", { name: "Replace" }))
    expect((await waitForSent("template_save")).body).toEqual({ name: "Rocketry design review", project_id: (await itemNamed("Rocketry design review")).id })
    expect(screen.queryByText(/Replace it\?/)).toBeNull()
  })

  it("removes a template you saved, with Undo; Essay and Presentation stay", async () => {
    const { user, client } = await page()
    await user.click(screen.getAllByRole("button", { name: "New project" })[0])
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByRole("button", { name: /^Rocketry design review/ })
    expect(within(dialog).queryByRole("button", { name: "Remove template Essay" })).toBeNull()
    expect(within(dialog).queryByRole("button", { name: "Remove template Presentation" })).toBeNull()
    await user.click(within(dialog).getByRole("button", { name: "Remove template Rocketry design review" }))
    expect(within(dialog).queryByRole("button", { name: /^Rocketry design review/ })).toBeNull() // gone at once
    const removed = (await waitForSent("settings_set")).body as { key: string; value: Record<string, unknown> }
    expect(removed.key).toBe("templates")
    expect(Object.keys(removed.value)).toEqual(["Essay", "Presentation"])
    await user.click(await screen.findByRole("button", { name: "Undo" }))
    await live(client, () => expect(within(dialog).getByRole("button", { name: /^Rocketry design review/ })).toBeTruthy())
    expect(screen.getByRole("dialog")).toBeTruthy() // still open
  })

  it("changes a project's tag in its popup, and its steps that had the old one with it", async () => {
    // 15 Nov, a client: a project's tag couldn't be changed; a step tagged otherwise keeps its own
    const slides = await itemNamed("Slides")
    await friday.c("edit", { id: slides.id, area: "MATH 1910" })
    const { user, client } = await page()
    await user.click(await screen.findByRole("button", { name: /Rocketry design review/ }))
    const project = await itemNamed("Rocketry design review")
    await user.click(await screen.findByRole("button", { name: "Tag for Rocketry design review" }))
    await user.click(screen.getByRole("option", { name: "PHYS 1112" }))
    expect(screen.getByRole("button", { name: "Tag for Rocketry design review" }).textContent).toBe("PHYS 1112") // at once
    expect((await waitForSent("edit")).body).toEqual({ id: project.id, area: "PHYS 1112" })
    const areas = async () => Object.fromEntries((await Promise.all(["Rocketry design review", "Research", "Slides", "Rehearse"].map(itemNamed))).map((i) => [i.title, i.area]))
    await waitFor(async () => expect(await areas()).toEqual({ "Rocketry design review": "PHYS 1112", Research: "PHYS 1112", Slides: "MATH 1910", Rehearse: "PHYS 1112" }), { timeout: 15_000 })
    // one Undo puts them all back
    await user.click((await screen.findAllByRole("button", { name: "Undo" })).at(-1) as HTMLElement)
    await waitFor(async () => expect(await areas()).toEqual({ "Rocketry design review": "Rocketry", Research: "Rocketry", Slides: "MATH 1910", Rehearse: "Rocketry" }), { timeout: 15_000 }) // a replan under a full run's load can take seconds (failed so in 0.6.1's gate, 19 Nov)
    await live(client, () => expect(screen.getByRole("button", { name: "Tag for Rocketry design review" }).textContent).toBe("Rocketry"))
    await friday.c("edit", { id: slides.id, area: "Rocketry" })
  })

  it("makes a blank project, moves between projects in its popup, and closes it to see them all", async () => {
    const { user, client } = await page()
    const dialog = await newProject(user, "Lab notebook cleanup")
    expect(within(dialog).getByText("Add your own steps")).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: /Blank/ }))
    await user.click(within(dialog).getByRole("button", { name: "No due date" }))
    // how long, typed (16 Nov: "what if i need 100 hours, i just want to type it")
    await setLength(user, dialog, "About how long, in all", { type: "40 hours" })
    await user.click(within(dialog).getByRole("button", { name: "Create project" }))
    expect((await waitForSent("add")).body).toEqual({ title: "Lab notebook cleanup", preset: "Project", due: null, area: null, duration_min: 2400 })
    // no steps yet: a to-do of its own, worked on as a whole (17 Nov, proposal (h))
    await live(client, () => expect(screen.getByText(/^Worked on as a whole · 40h · Add steps to split it up$/)).toBeTruthy())
    expect(screen.queryByRole("button", { name: /Save as template/ })).toBeNull()
    const first = screen.getByRole("dialog", { name: "Lab notebook cleanup" })
    await user.click(screen.getByRole("button", { name: "Project" }))
    await user.click(screen.getByRole("option", { name: "Rocketry design review" }))
    expect(await screen.findByText(/of 3 steps done/)).toBeTruthy()
    // picking another swaps what the popup shows, the same popup (17 Nov: projects open in a popup)
    expect(screen.getByRole("dialog", { name: "Rocketry design review" })).toBe(first)
    expect(screen.queryByRole("button", { name: /^Projects & exams$/ })).toBeNull() // no page back-link: the popup's ✕
    await user.click(within(first).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(window.location.hash).not.toContain("id="))
    expect(screen.queryByRole("dialog", { name: "Rocketry design review" })).toBeNull()
    // both on the deadline shelf (one with no due among them), and New project makes another
    const shelf = screen.getByRole("region", { name: "With a deadline" })
    for (const name of [/^Rocketry design review, /, /^Lab notebook cleanup, /]) expect(within(shelf).getByRole("button", { name })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "New project" }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
  })
})

describe("exams", () => {
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
    await user.click(await within(dialog).findByRole("button", { name: "Rocketry" }, { timeout: 10_000 })) // the tags load after the dialog opens
    await user.click(within(dialog).getByRole("button", { name: "No tag" }))
    await user.click(within(dialog).getByRole("button", { name: "ENGL 1170" }))
    await setLength(user, dialog, "Prep it needs", { type: "3h" })
    expect(within(dialog).getByRole("button", { name: "Prep it needs: 3h" })).toBeTruthy()
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

  // 19 Nov, a user's notes: "move text box for length of the exam to the same line as the others if possible (you can
  // make it less wide too)" and "add dropdown for customizing the exam focus ... e.g. start focusing on that class's
  // work 3 days before"
  it("has its length box on the row of usual lengths, as narrow as a length", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    const box = within(dialog).getByRole("textbox", { name: "Length" }) as HTMLInputElement
    const row = within(dialog).getByRole("button", { name: "3h" }).parentElement!
    expect(row.contains(box)).toBe(true)
    expect(box.placeholder).toBe("e.g. 2h 15m") // the box is as wide as its placeholder: "e.g. an hour and a half" had widened it
  })

  it("sets the exam's focus as it's made: as your rule gives an exam of its name, or its own", async () => {
    const opened = await page()
    await opened.user.click(screen.getByRole("button", { name: "New exam" }))
    const before = await screen.findByRole("dialog", { name: "New exam" })
    expect(await within(before).findByRole("button", { name: "Before this exam: Other classes' work goes on as usual" }, { timeout: 10_000 })).toBeTruthy() // no rule
    // 20 Nov, the user, of "Focus on its class": "not sure what that means". Said as the exam's popup says it, with what it does
    expect(within(before).queryByText(/focus on its class/i)).toBeNull()
    expect(within(before).getByText("Work for other classes due after it can wait until it's over.")).toBeTruthy()
    opened.unmount()
    await friday.c("rule_add", { text: "focus on exams 5 days before" })
    try {
      const { user } = await page()
      await user.click(screen.getByRole("button", { name: "New exam" }))
      const dialog = await screen.findByRole("dialog", { name: "New exam" })
      const name = within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2")
      await user.type(name, "CHEM 2090 Prelim 3")
      expect(await within(dialog).findByRole("button", { name: "Before this exam: Only this class's work, 5 days before (your rule)" }, { timeout: 10_000 })).toBeTruthy()
      await user.clear(name)
      await user.type(name, "CHEM 2090 Quiz 4") // the rule is for exams by their name: not a quiz's
      const focus = await within(dialog).findByRole("button", { name: "Before this exam: Other classes' work goes on as usual (your rule)" }, { timeout: 10_000 })
      await user.click(focus)
      expect(within(dialog).getByRole("radio", { name: /^As your other exams.*isn't for exams named so/ })).toBeTruthy()
      expect(within(dialog).getByRole("dialog", { name: "Before this exam" }).style.overflowY).toBe("auto") // its 9 choices scroll in its height
      await user.click(within(dialog).getByRole("radio", { name: /^3 days before/ }))
      expect(within(dialog).getByRole("button", { name: "Before this exam: Only this class's work, 3 days before" })).toBeTruthy()
      sent.length = 0
      await user.click(within(dialog).getByRole("button", { name: "Add exam" }))
      const set = (await waitForSent("settings_set")).body as { key: string; value: Record<string, number | null> }
      const exam = (await friday.q<{ item: { id: number; title: string } }[]>("exams")).find((x) => x.item.title === "CHEM 2090 Quiz 4")!
      expect(set.key).toBe("exam_focus_each")
      expect(set.value[String(exam.item.id)]).toBe(3)
      await waitFor(async () => expect((await friday.q<{ exam_focus_each: Record<string, number> }>("settings")).exam_focus_each[String(exam.item.id)]).toBe(3))
      // one Undo takes back the exam, its prep and its focus
      await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
      await waitFor(() => expect(sent.filter((s) => s.name === "undo")).toHaveLength(3), { timeout: 5000 })
    } finally {
      await friday.c("rule_remove", { name: "you:exam-focus" })
    }
  })

  it("takes an exam of any length, typed in the box beside the usual ones", async () => {
    // 15 Nov, a client: a 2h 30m final had no way in (1h, 1h 30m, 2h or 3h only)
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    const chips = ["45m", "1h", "1h 30m", "2h", "2h 30m", "3h"]
    for (const c of chips) expect(within(dialog).getByRole("button", { name: c })).toBeTruthy()
    await user.type(within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2"), "HIST 1500 Final")
    const box = within(dialog).getByRole("textbox", { name: "Length" })
    await user.clear(box)
    await user.type(box, "2h 30m")
    expect(within(dialog).getByText("→ 2h 30m")).toBeTruthy()
    await user.keyboard("{Enter}")
    expect(within(dialog).getByRole("button", { name: "2h 30m" }).getAttribute("aria-pressed")).toBe("true")
    await setLength(user, dialog, "Prep it needs", { pick: "None" })
    sent.length = 0
    await user.click(within(dialog).getByRole("button", { name: "Add exam" }))
    const exam = (await waitForSent("add")).body as { start: string; end: string }
    expect((Date.parse(exam.end) - Date.parse(exam.start)) / 60_000).toBe(150)
    expect(await screen.findByText("Exam added")).toBeTruthy()
    await user.click((await screen.findAllByRole("button", { name: "Undo" })).at(-1) as HTMLElement)
    await waitForSent("undo")
  })

  // 16 Nov, the user: "what if i need 100 hours, i just want to type it"
  it("takes the prep an exam needs typed, however much", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    await user.type(within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2"), "CHEM 2090 Final")
    await setLength(user, dialog, "Prep it needs", { type: "101 hours" })
    expect(within(dialog).getByRole("button", { name: "Prep it needs: 101h" })).toBeTruthy()
    sent.length = 0
    await user.click(within(dialog).getByRole("button", { name: "Add exam" }))
    await waitFor(() => expect(sent.filter((s) => s.name === "add")).toHaveLength(2), { timeout: 5000 })
    expect(sent.filter((s) => s.name === "add")[1].body).toMatchObject({ preset: "Exam prep", duration_min: 101 * 60 })
    await user.click((await screen.findAllByRole("button", { name: "Undo" })).at(-1) as HTMLElement)
    await waitForSent("undo")
  })

  it("adds an exam with no prep", async () => {
    const { user } = await page()
    await user.click(screen.getByRole("button", { name: "New exam" }))
    const dialog = await screen.findByRole("dialog", { name: "New exam" })
    await user.type(within(dialog).getByPlaceholderText("Name, e.g. MATH 2940 Prelim 2"), "Rocketry safety quiz")
    await setLength(user, dialog, "Prep it needs", { pick: "None" })
    expect(within(dialog).getByRole("button", { name: "Prep it needs: None" })).toBeTruthy()
    // a double click adds it once (audit, 12 Nov: it made two)
    await user.dblClick(within(dialog).getByRole("button", { name: "Add exam" }))
    expect(await screen.findByText("Exam added")).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New exam" })).toBeNull())
    expect(sent.filter((s) => s.name === "add")).toHaveLength(1)
  })

})
