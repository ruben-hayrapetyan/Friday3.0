// A project is judged by its steps, over Alex's sample with the client's project added (13 Nov: "CDJ Article isn't
// planned before it's due" in the plan's header, though its three steps were planned on the calendar days before its
// due; and a step's card said "Assignment · Draft" with nothing saying whose step it was). The header's pill, a
// step's card, the To-do page's rows and detail, and the drawer's rows.
import { cleanup, configure, screen, waitFor, within } from "@testing-library/react"
import { beforeAll, describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { addDays } from "@/lib/time"
import { friday, openFriday } from "@/test/friday"

configure({ asyncUtilTimeout: 10_000 })

type Status = Schemas["StatusOut"]
type Plan = Schemas["PlanOut"]
type Project = Schemas["ProjectOut"]

const PROJECT = "CDJ Article"
const STEPS = [
  ["Outline the article", 60],
  ["Draft the article", 180],
  ["Revise the article", 135],
] as const
let project = 0
const steps: Record<string, number> = {}
let today = ""

async function until<T>(read: () => Promise<T>, ok: (value: T) => boolean, seconds = 90): Promise<T> {
  const end = Date.now() + seconds * 1000
  for (;;) {
    const value = await read()
    if (ok(value) || Date.now() > end) return value
    await new Promise((r) => setTimeout(r, 500))
  }
}

beforeAll(async () => {
  today = (await friday.q<Schemas["CalendarOut"]>("calendar", { start: "2026-01-01", days: "1" })).today
  // As the client made it: a project due in four days at 5pm, its steps added on its page, each after the one before.
  const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: PROJECT, preset: "Project", due: `${addDays(today, 4)}T17:00`, duration_min: 375 })
  project = made.result.item.id
  for (const [title, minutes] of STEPS) {
    steps[title] = (await friday.c<{ result: { item: { id: number } } }>("add", { title, parent_id: project, duration_min: minutes })).result.item.id
  }
  await friday.c("depend", { item_id: steps["Draft the article"], depends_on_id: steps["Outline the article"] })
  await friday.c("depend", { item_id: steps["Revise the article"], depends_on_id: steps["Draft the article"] })
  const planned = await until(
    async () => ({ status: await friday.q<Status>("status"), projects: await friday.q<Project[]>("projects") }),
    ({ status, projects }) => status.plan_generation === status.generation && projects.some((p) => p.item.id === project && p.status === "on_track"),
  )
  // the steps planned in time: what the client saw on the calendar and on the Projects page
  expect(planned.projects.find((p) => p.item.id === project)?.status).toBe("on_track")
}, 120_000)

describe("a project whose steps are planned before its due", () => {
  it("isn't in the plan header's warnings", async () => {
    const { user } = await openFriday("/")
    await waitFor(() => expect(document.querySelector('[data-tour="calendar"] [data-block-key]')).not.toBeNull(), { timeout: 15_000 })
    // the pill shows only when something needs you; when it does, neither it nor its list may name the project
    // (it read "CDJ Article isn't planned before it's due")
    const pill = document.querySelector<HTMLButtonElement>('[data-tour="attention"]')
    if (pill) {
      expect(pill.title).not.toMatch(PROJECT)
      await user.click(pill)
      expect((pill.parentElement as HTMLElement).textContent).not.toMatch(PROJECT)
    }
    expect(screen.queryByText(new RegExp(`${PROJECT} isn't planned`))).toBeNull()
    const status = await friday.q<Status>("status")
    expect([...(status.late_items ?? []), ...(status.slipping ?? [])].map((i) => i.item_id)).not.toContain(project)
  })
})

describe("a step's card", () => {
  it("says which project it's a step of, with its project's due, and opens the project", async () => {
    const plan = await friday.q<Plan>("plan", { start: `${today}T00:00`, end: `${addDays(today, 7)}T00:00` })
    const block = plan.blocks.find((b) => b.item_id === steps["Draft the article"]) as Plan["blocks"][number]
    expect(block).toBeTruthy()
    cleanup()
    const { user } = await openFriday("/")
    // the week around today shows three days either side: a step four days on is a page later
    const ahead = Math.floor((Date.parse(`${block.start.slice(0, 10)}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`) + 3 * 86_400_000) / (7 * 86_400_000))
    for (let n = 0; n < ahead; n++) await user.click(screen.getByRole("button", { name: "Next" }))
    const box = () => document.querySelector<HTMLElement>(`[data-block-key="${CSS.escape(block.key)}"]`)
    await waitFor(() => expect(box()).not.toBeNull(), { timeout: 15_000 })
    await user.click(box() as HTMLElement)
    const card = await waitFor(() => document.querySelector<HTMLElement>("aside.fr-block-card") as HTMLElement)
    const link = await within(card).findByRole("button", { name: `Step of ${PROJECT}` })
    expect(await within(card).findByText(/, with its project$/)).toBeTruthy() // its due is its project's
    expect(within(card).getByText("Hard deadline")).toBeTruthy()
    await user.click(link)
    await waitFor(() => expect(window.location.hash).toBe(`#/projects?id=${project}`))
    expect(await screen.findByText(/^0 of 3 steps done/)).toBeTruthy()
    expect(screen.getByRole("button", { name: /^Due: (?!No due date)/ })).toBeTruthy() // its due, in its row
  })
})

describe("the To-do list", () => {
  it("lists the steps under the project's name, not the project as a to-do, and the detail opens it", async () => {
    // 17 Nov, proposal (h): a project made of steps isn't worked on directly, so it isn't a row; its steps are
    cleanup()
    const { user } = await openFriday("/todo")
    const row = (title: string) => screen.findByTitle(`${title}: click for everything about it, double-click the title to rename`, {}, { timeout: 10_000 })
    for (const [title] of STEPS) await row(title)
    expect(screen.queryByTitle(`${PROJECT}: click for everything about it, double-click the title to rename`)).toBeNull()
    const heading = (await screen.findAllByTitle(new RegExp(`^Open ${PROJECT}:`), {}, { timeout: 10_000 }))[0]
    // under its heading a step doesn't say its project's name again (it cut a phone's row short)
    for (const [title] of STEPS) expect(within(await row(title)).queryByTitle(`A step of ${PROJECT}`)).toBeNull()
    await user.click(heading)
    await waitFor(() => expect(window.location.hash).toBe(`#/projects?id=${project}`))
    await openFriday("/todo")
    await user.click(await row("Draft the article"))
    const detail = (await screen.findByRole("button", { name: `Step of ${PROJECT}` })).closest("aside") as HTMLElement
    expect(within(detail).getByText(/, with its project$/)).toBeTruthy()
    expect(within(detail).getByText(/^Its project's for now: hard/)).toBeTruthy()
    await user.click(within(detail).getByRole("button", { name: `Step of ${PROJECT}` }))
    await waitFor(() => expect(window.location.hash).toBe(`#/projects?id=${project}`))
  })

  it("in the drawer, says when the project's steps are planned and whose each step is", async () => {
    cleanup()
    const { user } = await openFriday("/")
    await user.click(await screen.findByRole("button", { name: "To-do list" }))
    const aside = (await screen.findByPlaceholderText("Add a to-do")).closest("aside") as HTMLElement
    await user.click(within(aside).getByRole("button", { name: "When" }))
    // a row by its title (its title's line ends with it; a step's second line names the project first)
    const rowOf = async (title: string) =>
      (await within(aside).findAllByText((_, el) => el?.tagName === "SPAN" && (el.textContent ?? "").trim() === title && !!el.closest('[role="button"]'), {}, { timeout: 10_000 }))[0].closest('[role="button"]') as HTMLElement
    expect((await rowOf("Draft the article")).textContent).toMatch(`${PROJECT} · `)
    expect(within(aside).getAllByTitle(new RegExp(`^Open ${PROJECT}:`)).length).toBeGreaterThan(0) // its name over its steps
    expect(within(aside).queryAllByText((_, el) => el?.tagName === "SPAN" && (el.textContent ?? "").trim() === PROJECT && !!el.closest('[role="button"][title*="click"]'))).toHaveLength(0)
  })
})
