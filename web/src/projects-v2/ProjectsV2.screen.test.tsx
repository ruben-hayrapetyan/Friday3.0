// Black box: the new Projects & exams page (/projects-v2) over Alex's sample, a real server behind it. Its way in from
// the current page; the deadline shelf (exams and projects as rows on six weeks, the next step ticked in place, a row
// opened as Friday opens it); an ongoing project made, opened, its options each saying their value, paused and
// resumed, deleted; a project archived to Finished, opened again, and deleted there.
import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { friday, openFriday, waitForSent } from "@/test/friday"

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

  it("opens an exam in place, with its address, and goes back", async () => {
    const f = await page()
    const [exam] = await friday.q<{ item: Item }[]>("exams")
    await f.user.click(await within(shelf("With a deadline")).findByRole("button", { name: new RegExp(`^${exam.item.title}, `) }))
    await waitFor(() => expect(window.location.hash).toBe(`#/projects-v2?exam=${exam.item.id}`))
    await f.user.click(await screen.findByRole("button", { name: /All projects & exams/ }))
    await waitFor(() => expect(window.location.hash).toBe("#/projects-v2"))
  })

  it("makes an ongoing project, opens it, and says each option's value", async () => {
    const f = await page()
    await f.user.click(screen.getByRole("button", { name: "New ongoing project" }))
    const dialog = await screen.findByRole("dialog", { name: "New ongoing project" })
    await f.user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Guitar practice")
    await f.user.click(within(dialog).getByRole("button", { name: "More hours" }))
    expect(within(dialog).getByText("4 h")).toBeTruthy()
    await f.user.click(within(dialog).getByRole("button", { name: "Create ongoing project" }))
    expect((await waitForSent("ongoing_add")).body).toEqual({ title: "Guitar practice", hours_per_week: 4, area: null })
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/projects-v2\?ongoing=\d+$/))
    expect(await screen.findByText("Guitar practice")).toBeTruthy()
    expect(screen.getByText("Whenever it fits")).toBeTruthy()
    await f.user.click(within(screen.getByRole("group", { name: "Days a week" })).getByRole("button", { name: "2" }))
    expect(await screen.findByText("2 days a week, about 2h each")).toBeTruthy() // at once, before the server answers
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ rhythm_days: 2 })
    expect(screen.getByText("Half: half of what's missed comes into next week")).toBeTruthy()
    await f.user.click(within(screen.getByRole("group", { name: "Priority" })).getByRole("button", { name: "High" }))
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ priority: 4 })
    await live(f, () => expect(screen.getByText(/^High: /)).toBeTruthy())
  })

  it("shows the ongoing project on its shelf, pauses it until a date, and resumes it", async () => {
    const f = await page()
    const card = await within(shelf("Ongoing")).findByRole("button", { name: "Guitar practice" })
    expect(within(card).getByRole("img", { name: /Worked on 0 of the last 56 days/ })).toBeTruthy()
    expect(within(card).getByText(/of 4h this week/)).toBeTruthy()
    await f.user.click(card)
    await f.user.click(await screen.findByRole("button", { name: /^In two weeks/ }))
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ paused_until: expect.stringMatching(/^\d{4}-\d\d-\d\d$/) })
    expect(await screen.findByText(/^Paused until /)).toBeTruthy()
    await f.user.click(screen.getByRole("button", { name: /Resume/ }))
    expect((await waitForSent("ongoing_set")).body).toMatchObject({ paused_until: "" })
    expect(await screen.findByRole("button", { name: /^Pause$/ })).toBeTruthy()
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
})
