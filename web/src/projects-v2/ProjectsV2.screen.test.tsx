// Black box: the new Projects & exams page (/projects-v2) over Alex's sample, a real server behind it. Its way in from
// the current page; the deadline shelf (exams and projects as rows on six weeks, the next step ticked in place, a row
// opened as Friday opens it); an ongoing project made, opened, its options each saying their value, paused and
// resumed, deleted; a project archived to Finished, opened again, and deleted there.
import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"

configure({ asyncUtilTimeout: 8000 })

type F = Awaited<ReturnType<typeof openFriday>>

async function page(route = "/projects-v2") {
  const f = await openFriday(route)
  await screen.findByText(/\d+ with a deadline/, {}, { timeout: 10_000 })
  return f
}

/** Reads every query again until `check` passes, as the live updates would (the screens have no stream). */
async function live(f: F, check: () => unknown) {
  await waitFor(
    async () => {
      await f.client.invalidateQueries()
      await check()
    },
    { timeout: 10_000, interval: 250 },
  )
}

const shelf = (name: string) => screen.getByRole("region", { name })
type User = F["user"]

/** A setting's row: opened by its value, a choice picked by its words (projects-v2/Rows.tsx). */
async function choose(user: User, scope: HTMLElement, label: string, choice: string | RegExp) {
  await user.click(within(scope).getByRole("button", { name: new RegExp(`^${label}: `) }))
  await user.click(within(within(scope).getByRole("radiogroup", { name: label })).getByRole("radio", { name: choice }))
}

/** A length in a setting's row: the row opened, an amount picked or one typed and Enter (Ongoing.tsx LengthPicks). */
async function setRowLength(user: User, scope: HTMLElement, label: string, choice: { pick: string } | { type: string }) {
  await user.click(within(scope).getByRole("button", { name: new RegExp(`^${label}: `) }))
  const group = within(scope).getByRole("group", { name: label })
  if ("pick" in choice) await user.click(within(group).getByRole("button", { name: choice.pick }))
  else await user.type(within(group).getByRole("textbox", { name: `${label}, typed` }), `${choice.type}{Enter}`)
  await waitFor(() => expect(within(scope).queryByRole("group", { name: label })).toBeNull())
}

/** A length field (todo/Pickers LengthField): opened, then an amount picked or one typed and Enter. */
async function setLength(user: User, scope: HTMLElement, label: string, choice: { pick: string } | { type: string }) {
  const field = within(scope).getByRole("button", { name: new RegExp(`^${label}: `) })
  await user.click(field)
  const picker = (await screen.findAllByRole("dialog", { name: label })).at(-1) as HTMLElement
  if ("pick" in choice) await user.click(within(picker).getByRole("button", { name: choice.pick }))
  else await user.type(within(picker).getByRole("textbox", { name: `${label}, typed` }), `${choice.type}{Enter}`)
  await waitFor(() => expect(field.getAttribute("aria-expanded")).toBe("false"))
}
const rowNamed = (title: RegExp) => within(shelf("With a deadline")).getByRole("button", { name: title })

describe("the new Projects & exams page", () => {
  it("is found from the current page", async () => {
    const f = await openFriday("/projects")
    await f.user.click(await screen.findByRole("link", { name: /Try the new layout/ }))
    await waitFor(() => expect(window.location.hash).toBe("#/projects-v2"))
    expect(await screen.findByText(/\d+ with a deadline/)).toBeTruthy()
    await f.user.click(screen.getByRole("link", { name: /Current page/ }))
    await waitFor(() => expect(window.location.hash).toBe("#/projects"))
  })

  it("shows the exams as rows on six weeks, flagged at the exam, with their next prep to tick", async () => {
    const f = await page()
    const exams = (await friday.q<{ item: Item; prep: { item: Item }[] }[]>("exams")).filter((e) => e.prep.some((p) => p.item.status === "todo"))
    const exam = exams[0]
    const row = await within(shelf("With a deadline")).findByRole("button", { name: new RegExp(`^${exam.item.title}, `) })
    expect(within(row).getByText(/^Exam (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+$/)).toBeTruthy()
    expect(within(shelf("With a deadline")).getByText("This week")).toBeTruthy()
    const next = exam.prep.find((p) => p.item.status === "todo")!.item
    expect(within(row).getByText(next.title)).toBeTruthy()
    await f.user.click(within(row).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: next.id })
    await waitFor(() => expect(within(row).queryByText(next.title)).toBeNull()) // gone at once, before the server
    await friday.c("reopen", { id: next.id }) // the other tests see it as it was
  })

  it("opens an exam in a side panel with its address, the shelves still there, and closes it", async () => {
    const f = await page()
    const [exam] = await friday.q<{ item: Item }[]>("exams")
    await f.user.click(await within(shelf("With a deadline")).findByRole("button", { name: new RegExp(`^${exam.item.title}, `) }))
    await waitFor(() => expect(window.location.hash).toBe(`#/projects-v2?exam=${exam.item.id}`))
    const panel = await screen.findByRole("complementary", { name: exam.item.title })
    expect(shelf("With a deadline")).toBeTruthy() // still in view beside it
    await f.user.click(within(panel).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(window.location.hash).toBe("#/projects-v2"))
  })

  it("changes an exam's prep in its panel: renamed, its length and by when, ticked, deleted, and more added", async () => {
    const f = await page()
    const exams = await friday.q<{ item: Item; prep: { item: Item }[] }[]>("exams")
    const exam = exams.find((e) => e.prep.length > 0) as { item: Item; prep: { item: Item }[] }
    const prep = exam.prep[0].item
    await f.user.click(await within(shelf("With a deadline")).findByRole("button", { name: new RegExp(`^${exam.item.title}, `) }))
    const panel = await screen.findByRole("complementary", { name: exam.item.title })
    const row = within(panel).getByRole("listitem", { name: prep.title })
    await f.user.click(within(row).getByRole("button", { name: prep.title }))
    const box = within(row).getByRole("textbox", { name: `Rename ${prep.title}` })
    await f.user.clear(box)
    await f.user.type(box, "Review sheet{Enter}")
    expect((await waitForSent("edit")).body).toEqual({ id: prep.id, title: "Review sheet" })
    sent.length = 0
    const renamed = await within(panel).findByRole("listitem", { name: "Review sheet" }) // at once
    await setLength(f.user, renamed, "Length of Review sheet", { type: "7.5 hours" })
    expect((await waitForSent("edit")).body).toEqual({ id: prep.id, duration_min: 450 })
    expect(within(renamed).getByRole("button", { name: /^When Review sheet is due: by / })).toBeTruthy()
    await f.user.click(within(renamed).getByRole("checkbox", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: prep.id })
    await f.user.click(within(renamed).getByRole("checkbox", { name: "Mark not done" }))
    expect((await waitForSent("reopen")).body).toEqual({ id: prep.id })
    await f.user.click(within(panel).getByRole("button", { name: /Add prep/ }))
    await f.user.type(within(panel).getByRole("textbox", { name: "New prep" }), "Practice exam 3")
    await setLength(f.user, panel, "How long the new prep takes", { pick: "3h" })
    await f.user.click(within(panel).getByRole("button", { name: "Add" }))
    expect((await waitForSent("add")).body).toMatchObject({ title: "Practice exam 3", preset: "Exam prep", duration_min: 180, due: exam.item.start, before: [exam.item.id] })
    expect(await within(panel).findByRole("listitem", { name: "Practice exam 3" })).toBeTruthy() // at once
    await f.user.click(within(renamed).getByRole("button", { name: "Delete Review sheet" }))
    expect((await waitForSent("drop")).body).toEqual({ id: prep.id })
    await waitFor(() => expect(within(panel).queryByRole("listitem", { name: "Review sheet" })).toBeNull())
    await friday.c("reopen", { id: prep.id }) // the other tests see it as it was
    await friday.c("edit", { id: prep.id, title: prep.title, duration_min: prep.duration_min })
  })

  it("makes an ongoing project, opens it, and says each option's value", async () => {
    const f = await page()
    await f.user.click(screen.getByRole("button", { name: "New ongoing project" }))
    const dialog = await screen.findByRole("dialog", { name: "New ongoing project" })
    await f.user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Guitar practice")
    await setLength(f.user, dialog, "Hours a week", { pick: "2h" })
    await setLength(f.user, dialog, "Hours a week", { type: "4h" })
    expect(within(dialog).getByRole("button", { name: "Hours a week: 4h a week" })).toBeTruthy()
    await f.user.click(within(dialog).getByRole("button", { name: "Create ongoing project" }))
    expect((await waitForSent("ongoing_add")).body).toEqual({ title: "Guitar practice", hours_per_week: 4, area: null })
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/projects-v2\?ongoing=\d+$/))
    const panel = await screen.findByRole("complementary", { name: "Guitar practice" })
    expect(within(panel).getByRole("button", { name: "Days a week: Whenever it fits" })).toBeTruthy()
    await choose(f.user, panel, "Days a week", /^2 days a week/)
    expect(await within(panel).findByRole("button", { name: "Days a week: 2 days a week, about 2h each" })).toBeTruthy() // at once
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ rhythm_days: 2 })
    expect(within(panel).getByRole("button", { name: "A short week: Half: half of what's missed comes into next week" })).toBeTruthy()
    sent.length = 0
    await choose(f.user, panel, "Priority", /^High\b/)
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ priority: 4 })
    expect(within(panel).getByRole("button", { name: "Priority: High" })).toBeTruthy()
    sent.length = 0
    await setRowLength(f.user, panel, "Hours a week", { pick: "5h" })
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ hours_per_week: 5 })
    sent.length = 0
    await setRowLength(f.user, panel, "Hours a week", { type: "4h" }) // and typed
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ hours_per_week: 4 })
    await live(f, () => expect(within(panel).getByRole("button", { name: "Hours a week: 4h a week" })).toBeTruthy())
  })

  it("takes an ongoing project's hours a week typed", async () => {
    const f = await page()
    await f.user.click(screen.getByRole("button", { name: "New ongoing project" }))
    const dialog = await screen.findByRole("dialog", { name: "New ongoing project" })
    await f.user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Thesis reading")
    await setLength(f.user, dialog, "Hours a week", { type: "12.5 hours" })
    await f.user.click(within(dialog).getByRole("button", { name: "Create ongoing project" }))
    expect((await waitForSent("ongoing_add")).body).toEqual({ title: "Thesis reading", hours_per_week: 12.5, area: null })
    await f.user.click(await screen.findByRole("button", { name: /Delete/ }))
    await f.user.click(screen.getByRole("button", { name: "Delete it" })) // the next tests see only Guitar practice
    await waitForSent("ongoing_delete")
  })

  it("shows the ongoing project on its shelf, pauses it until a date, and resumes it", async () => {
    const f = await page()
    const card = await within(shelf("Ongoing")).findByRole("button", { name: "Guitar practice" })
    expect(within(card).getByRole("img", { name: /Worked on 0 of the last 56 days/ })).toBeTruthy()
    expect(within(card).getByText(/of 4h this week/)).toBeTruthy()
    await f.user.click(card)
    const panel = await screen.findByRole("complementary", { name: "Guitar practice" })
    expect(within(panel).getByRole("button", { name: "Paused: No" })).toBeTruthy()
    await choose(f.user, panel, "Paused", /^For two weeks/)
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ paused_until: expect.stringMatching(/^\d{4}-\d\d-\d\d$/) })
    expect(await within(panel).findByRole("button", { name: /^Paused: Until (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+/ })).toBeTruthy()
    await choose(f.user, panel, "Paused", /^No\b/)
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ paused_until: "" })
    expect(await within(panel).findByRole("button", { name: "Paused: No" })).toBeTruthy()
  })

  it("deletes an ongoing project after saying what goes and what stays", async () => {
    const f = await page()
    await f.user.click(await within(shelf("Ongoing")).findByRole("button", { name: "Guitar practice" }))
    await f.user.click(await screen.findByRole("button", { name: /Delete/ }))
    expect(screen.getByText(/the hours you put in stay in your history/)).toBeTruthy()
    await f.user.click(screen.getByRole("button", { name: "Delete it" }))
    expect((await waitForSent("ongoing_delete")).body).toEqual({ id: expect.any(Number) })
    await waitFor(() => expect(window.location.hash).toBe("#/projects-v2"))
    await live(f, () => expect(within(shelf("Ongoing")).queryByRole("button", { name: "Guitar practice" })).toBeNull())
  })

  it("archives a project to Finished, opens it again, and deletes it there", async () => {
    const made = await friday.c<{ result: { item: Item } }>("add", { title: "Poster", preset: "Project", due: "2026-12-30T17:00", duration_min: 240 })
    const id = made.result.item.id
    await friday.c("add", { title: "Print the poster", parent_id: id, duration_min: 60 })
    const f = await page()
    await f.user.click(await waitFor(() => rowNamed(/^Poster, /)))
    await waitFor(() => expect(window.location.hash).toBe(`#/projects-v2?id=${id}`))
    await f.user.click(await screen.findByRole("button", { name: /Archive/ }))
    expect((await waitForSent("project_archive")).body).toEqual({ id })
    await waitFor(() => expect(window.location.hash).toBe("#/projects-v2")) // back on the shelves at once
    expect(within(shelf("With a deadline")).queryByRole("button", { name: /^Poster, / })).toBeNull()
    await live(f, () => expect(shelf("Finished")).toBeTruthy())
    await f.user.click(within(shelf("Finished")).getByRole("button", { name: /Finished/ }))
    expect(await within(shelf("Finished")).findByText("Poster")).toBeTruthy()
    await f.user.click(within(shelf("Finished")).getByRole("button", { name: /Open again/ }))
    expect((await waitForSent("project_unarchive")).body).toEqual({ id })
    await live(f, () => expect(rowNamed(/^Poster, /)).toBeTruthy())
    await friday.c("project_archive", { id })
    await live(f, () => expect(within(shelf("Finished")).getByText("Poster")).toBeTruthy())
    await f.user.click(within(shelf("Finished")).getByRole("button", { name: "Delete Poster" }))
    await f.user.click(within(shelf("Finished")).getByRole("button", { name: "Delete it" }))
    expect((await waitForSent("project_delete")).body).toEqual({ id })
  })

  it("opens a big to-do on the To-do page, as the drawer does", async () => {
    const made = await friday.c<{ result: { item: Item } }>("add", { title: "Research paper", preset: "Assignment", due: "2026-12-28T23:59", duration_min: 360 })
    const f = await page()
    await live(f, () => expect(rowNamed(/^Research paper, /)).toBeTruthy())
    await f.user.click(rowNamed(/^Research paper, /))
    await waitFor(() => expect(window.location.hash).toBe(`#/todo?item=${made.result.item.id}`))
  })

  it("shows a project's notes beside its name, its milestones on its bar, and sets how early it finishes and its pace", async () => {
    const made = await friday.c<{ result: { item: Item } }>("add", { title: "Lab report", preset: "Project", due: "2026-12-18T17:00", duration_min: 600, notes: "Ask Dr. Park about the error bars\nUse the second data set" })
    const id = made.result.item.id
    await friday.c("add", { title: "Analysis", parent_id: id, duration_min: 240, due: "2026-12-08T17:00" })
    const f = await page()
    const row = await waitFor(() => rowNamed(/^Lab report, /))
    expect(within(row).getByRole("note", { name: /Notes: Ask Dr. Park about the error bars Use the second data set/ })).toBeTruthy()
    expect(row.querySelector("[data-milestone]")?.getAttribute("title")).toMatch(/^Analysis, due (Mon|Tue|Wed|Thu|Fri|Sat|Sun) 8$/)
    expect(row.querySelector("[data-aim]")).toBeNull()
    await f.user.click(row)
    const options = await screen.findByRole("region", { name: "Notes and options" })
    expect((within(options).getByRole("textbox", { name: "Notes" }) as HTMLTextAreaElement).value).toBe("Ask Dr. Park about the error bars\nUse the second data set")
    expect(within(options).getByRole("button", { name: "Finish early: No: it can take until its due" })).toBeTruthy()
    await choose(f.user, options, "Finish early", /^3 days early/)
    expect(await within(options).findByRole("button", { name: /^Finish early: 3 days early, by (Mon|Tue|Wed|Thu|Fri|Sat|Sun) 15$/ })).toBeTruthy() // at once
    expect(within(options).getByText("A rule you'll find in Rules")).toBeTruthy()
    expect((await waitForSent("project_set")).body).toEqual({ id, early_days: 3 })
    expect(within(options).getByRole("button", { name: "Pace: Not set" })).toBeTruthy()
    sent.length = 0
    await choose(f.user, options, "Pace", /^Front-load it/)
    expect(await within(options).findByRole("button", { name: "Pace: Front-load it" })).toBeTruthy()
    expect((await waitForSent("project_set")).body).toEqual({ id, pacing: "front" })
    await waitFor(async () => {
      const rules = await friday.q<{ name: string; sentence: string }[]>("rules")
      expect(rules.find((r) => r.name === `you:project:${id}:early`)?.sentence).toBe("Finish Lab report 3 days early")
    })
    await f.user.click(screen.getByRole("button", { name: /^Projects & exams$/ }))
    await live(f, () => expect(rowNamed(/^Lab report, /).querySelector("[data-aim]")).toBeTruthy())
  })
})
