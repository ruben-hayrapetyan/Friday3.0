// One task's detail beside the To-do list: its tag, kind and due from their pickers, how firm the deadline is,
// whether it's pointless late or runs by itself, the estimate, time to get there, how much is done, time logged
// without the timer, Start, Done, See on plan, and Delete (one of a repeat, or every one).
import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { dur } from "@/lib/format"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title && i.status === "todo") as Item

/** Open assignments in Short term with a tag, soonest due first, each its own title: which the sample's three weeks
 * finish early moves with the planner (17 Nov: with work going in as soon as there's time, HW 10 and WebWork 10 and
 * 11 were done). `fresh`: none of it done yet, so its detail says Start now rather than Resume. */
async function openAssignments(fresh = false) {
  const open = (await items()).filter((i) => i.status === "todo" && i.preset === "Assignment" && !i.long_term && i.area && (!fresh || !i.done_min))
  return open.filter((i) => open.filter((o) => o.title === i.title).length === 1).sort((a, b) => (a.due ?? "~").localeCompare(b.due ?? "~") || a.id - b.id)
}

/** A day as the API writes it, `days` from today on the page's clock (the server's): "2026-11-13". */
const ymd = (days: number) => {
  const d = new Date(Date.now() + days * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

let spares = 0
/** The `n`th of the open assignments above, soonest due first; when the sample has finished all but a few, spares
 * are added through the API, so no test here waits on which homework the simulation happened to leave open. */
async function assignment(n: number): Promise<Item> {
  let open = await openAssignments()
  if (open.length > n) return open[n]
  for (let k = open.length; k <= n; k++) await friday.c("add", { title: `Spare problem set ${++spares}`, preset: "Assignment", area: "MATH 1910", due: `${ymd(4 + spares)}T23:59`, duration_min: 120 })
  open = await openAssignments()
  return open[n]
}

/** An open assignment with a session planned from now on, by its title. */
async function plannedAssignment(): Promise<string> {
  const { now, today } = await friday.q<{ now: string; today: string }>("calendar", { start: "2026-01-01", days: "1" })
  let id: number | undefined
  await waitFor(
    async () => {
      const plan = await friday.q<{ blocks: { item_id: number; key: string; preset?: string | null; start: string }[] }>("plan", { start: `${today}T00:00`, end: `${ymd(14)}T00:00` })
      const open = new Set((await openAssignments()).map((i) => i.id))
      id = plan.blocks.find((b) => b.key.startsWith("T") && b.start >= now && open.has(b.item_id))?.item_id
      expect(id).toBeTruthy()
    },
    { timeout: 30_000, interval: 500 },
  )
  return (await items()).find((i) => i.id === id)?.title as string
}

/** The To-do page with task `title` open beside the list. */
async function detailOf(title: string) {
  const item = await itemNamed(title)
  const f = await openFriday(`/todo?item=${item.id}`)
  await screen.findByText("Planned sessions", {}, { timeout: 10_000 })
  const aside = screen.getByText("Planned sessions").closest("aside") as HTMLElement
  return { ...f, item, aside }
}

describe("a task's detail", () => {
  it("shows the task, what's left and its planned sessions, and Close puts it away", async () => {
    // how much the sample did depends on the day it's lived to: none of it, so all of it is left
    const task = await assignment(0)
    await friday.c("progress", { id: task.id, share: 0 })
    const { user, aside } = await detailOf(task.title)
    expect(within(aside).getByText(task.title)).toBeTruthy()
    expect(within(aside).getByText(`${dur(task.duration_min as number)} to do`)).toBeTruthy()
    expect(within(aside).getByText(`${dur(task.duration_min as number)} left`)).toBeTruthy()
    expect(within(aside).getByRole("slider", { name: "How much is done" }).getAttribute("aria-valuenow")).toBe("0")
    await user.click(within(aside).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
    expect(window.location.hash).not.toContain("item=")
  })

  it("changes the tag and the kind from their pickers", async () => {
    await assignment(1)
    const [task] = (await openAssignments()).filter((i) => i.area !== "Rocketry").slice(-1)
    const { user, aside, item } = await detailOf(task.title)
    await user.click(within(aside).getByRole("button", { name: task.area as string }))
    await user.click(within(aside).getByRole("button", { name: "Rocketry" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, area: "Rocketry" })
    await user.click(await within(aside).findByRole("button", { name: "Assignment" }))
    await user.click(within(aside).getByRole("button", { name: "Errand" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, preset: "Errand" })
    await waitFor(async () => expect(await itemNamed(task.title)).toMatchObject({ area: "Rocketry", preset: "Errand" }))
    await friday.c("edit", { id: item.id, area: task.area, preset: task.preset }) // as it was, for the tests after
  })

  it("moves the due with a quick pick, keeping its time of day", async () => {
    // one due at the end of a day still to come (one gone by says "(in -1 days)": see dueSummary)
    await assignment(2)
    const task = (await openAssignments()).find((i) => i.due?.endsWith("T23:59") && i.due >= `${ymd(0)}T23:59`) as Item
    const { user, aside, item } = await detailOf(task.title)
    await user.click(within(aside).getByRole("button", { name: /11:59pm/ }))
    expect(within(aside).getByText(/^Due \w{3} \d+ \w{3}, .* \((today|tomorrow|in \d+ days)\)$/)).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "In a week" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toEqual({ id: item.id, due: expect.stringMatching(/T23:59$/) })
    await user.click(within(aside).getByRole("button", { name: "No due date" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, due: null })
    await waitFor(async () => expect((await items()).find((i) => i.id === item.id)?.due).toBeNull())
    await friday.c("edit", { id: item.id, due: task.due }) // its own due again, for the tests after
  })

  it("sets how firm the deadline is, whether it's pointless late, and whether it runs by itself", async () => {
    // an assignment of its own, with a hard deadline: this one ends up soft, pointless late and running by itself
    const made = await friday.c<{ result: { item: Item } }>("add", { title: "Firm worksheet", preset: "Assignment", area: "PHYS 1112", due: `${ymd(6)}T08:00`, duration_min: 60, firmness: "hard" })
    const { user, aside, item } = await detailOf(made.result.item.title)
    await user.click(within(aside).getByRole("button", { name: "Soft" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, firmness: "soft" })
    expect(within(aside).getByText(/Planned late if it can't be on time\.|later it's done/)).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "⏳ Pointless" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, expires: true })
    expect(await within(aside).findByText(/Your choice for this one\. Never planned after it's due\./)).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "Still worth doing" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, expires: false })
    expect(within(aside).getByText("Off: you work on it the whole time.")).toBeTruthy()
    await user.click(within(aside).getByRole("switch", { name: "Runs by itself" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, background: true })
    expect(await within(aside).findByText(/Friday holds 15 minutes to start it/)).toBeTruthy()
    await friday.c("drop", { id: item.id })
  })

  it("says exam prep is pointless late by default", async () => {
    // the sample's open exam prep, or some of its own if all of it is done
    const prep =
      (await items()).find((i) => i.status === "todo" && i.preset === "Exam prep" && i.expires === null) ??
      (await friday.c<{ result: { item: Item } }>("add", { title: "Prep: practice quiz", preset: "Exam prep", due: `${ymd(5)}T19:00`, duration_min: 60 })).result.item
    const { aside } = await detailOf(prep.title)
    expect(within(aside).getByText(/As for all exam prep\. Never planned after it's due\./)).toBeTruthy()
    expect(within(aside).getByRole("button", { name: "⏳ Pointless" }).getAttribute("aria-pressed")).toBe("true")
  })

  it("steps the estimate up and down, saved once the presses stop, or sets it from the picker", async () => {
    // an hour and a half to start from, whatever its own estimate is
    const [task] = (await openAssignments()).slice(-1)
    await friday.c("edit", { id: task.id, duration_min: 90 })
    sent.length = 0 // that edit was the test's, not the page's
    const { user, aside, item } = await detailOf(task.title)
    await user.click(within(aside).getByRole("button", { name: "More: 1h 45m" }))
    await user.click(within(aside).getByRole("button", { name: "More: 2h" }))
    const saved = await waitForSent("edit")
    expect(saved.body).toEqual({ id: item.id, duration_min: 120 })
    await waitFor(() => expect(within(aside).getByRole("button", { name: "Less: 1h 45m" })).toBeTruthy(), { timeout: 5000 })
    await user.click(within(aside).getByRole("button", { name: "Less: 1h 45m" }))
    await waitFor(async () => expect((await itemNamed(task.title)).duration_min).toBe(105), { timeout: 5000 })
    await user.click(within(aside).getByRole("button", { name: "Set" }))
    await user.click(within(aside).getByRole("button", { name: "3h" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, duration_min: 180 })
    await waitFor(async () => expect((await itemNamed(task.title)).duration_min).toBe(180))
    await friday.c("edit", { id: item.id, duration_min: task.duration_min }) // its own estimate again
  })

  it("keeps time free around it to get there and back", async () => {
    const task = await assignment(0)
    const { user, aside, item } = await detailOf(task.title)
    expect(within(aside).getByText("Work can sit right up against it.")).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "15 min" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, buffer_before_min: 15, buffer_after_min: 15 })
    expect(await within(aside).findByText("15 min kept free before and after, to get there and back.")).toBeTruthy()
    await user.click(within(aside).getAllByRole("button", { name: "None" }).at(-1) as HTMLElement) // the deadline has a None too
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, buffer_before_min: null, buffer_after_min: null })
  })

  it("says how much is done with the keyboard, and Start over counts none of it", async () => {
    // how long it is and how much the sample did depend on the day it's lived to: set to 1h 15m of 4h
    const task = await assignment(1)
    await friday.c("edit", { id: task.id, duration_min: 240 })
    await friday.c("progress", { id: task.id, share: 0.3125 })
    sent.length = 0 // those were the test's, not the page's
    const { user, aside, item } = await detailOf(task.title)
    expect(within(aside).getByText("1h 15m of 4h")).toBeTruthy()
    expect(within(aside).getByText("2h 45m left · 1h 15m done")).toBeTruthy()
    expect(within(aside).getByRole("button", { name: /Resume/ })).toBeTruthy()
    const slider = within(aside).getByRole("slider", { name: "How much is done" })
    slider.focus()
    await user.keyboard("{ArrowLeft}")
    const moved = await waitForSent("progress")
    expect(moved.body).toEqual({ id: item.id, share: 0.25 })
    await user.keyboard("{ArrowRight}")
    expect((await waitForSent("progress")).body).toMatchObject({ id: item.id })
    await user.keyboard("{Home}")
    expect((await waitForSent("progress")).body).toEqual({ id: item.id, share: 0 })
    await user.keyboard("x") // not a key it takes
    await friday.c("edit", { id: item.id, duration_min: task.duration_min }) // its own length again
  })

  it("says how much is done with a click along the bar", async () => {
    // a task of its own, open whatever day the sample was lived to
    await friday.c("add", { title: "Bar reading", preset: "Reading", duration_min: 120 })
    const { user, aside, item } = await detailOf("Bar reading")
    const slider = within(aside).getByRole("slider", { name: "How much is done" })
    // happy-dom lays nothing out: the bar is given a width, as a browser would.
    slider.getBoundingClientRect = () => ({ left: 100, width: 200, top: 0, height: 10, right: 300, bottom: 10, x: 100, y: 0, toJSON: () => ({}) })
    await user.pointer({ keys: "[MouseLeft]", target: slider, coords: { clientX: 150 } })
    expect((await waitForSent("progress")).body).toEqual({ id: item.id, share: 0.25 })
  })

  it("starts the task over from its detail", async () => {
    const task = await assignment(1)
    await friday.c("progress", { id: task.id, share: 0.5 })
    sent.length = 0 // that was the test's, not the page's
    const { user, aside, item } = await detailOf(task.title)
    await user.click(await within(aside).findByRole("button", { name: "Start over" }))
    expect((await waitForSent("progress")).body).toEqual({ id: item.id, share: 0 })
  })

  it("logs time worked without the timer, and Cancel closes it", async () => {
    const { user, aside, item } = await detailOf((await assignment(2)).title)
    await user.click(within(aside).getByRole("button", { name: "Log time" }))
    let group = within(aside).getByRole("group", { name: "Time you worked" })
    await user.click(within(group).getByRole("button", { name: "Cancel" }))
    expect(within(aside).queryByRole("group", { name: "Time you worked" })).toBeNull()
    await user.click(within(aside).getByRole("button", { name: "Log time" }))
    group = within(aside).getByRole("group", { name: "Time you worked" })
    await user.click(within(group).getByRole("button", { name: "Day" }))
    await user.click(within(group).getByRole("option", { name: "Yesterday" }))
    expect(within(group).getByText("1h")).toBeTruthy()
    await user.click(within(group).getByRole("button", { name: "Log it" }))
    const sent = await waitForSent("log")
    expect(sent.body).toEqual({ id: item.id, start: expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/), end: expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/) })
    await waitFor(() => expect(within(aside).queryByRole("group", { name: "Time you worked" })).toBeNull())
  })

  it("logs the times typed, saved with Enter", async () => {
    const { user, aside, item } = await detailOf((await assignment(2)).title)
    await user.click(within(aside).getByRole("button", { name: "Log time" }))
    const group = within(aside).getByRole("group", { name: "Time you worked" })
    await user.clear(within(group).getByRole("textbox", { name: "Started" }))
    await user.keyboard("2pm")
    await user.tab()
    await user.clear(within(group).getByRole("textbox", { name: "Stopped" }))
    await user.keyboard("3:30pm{Enter}")
    const sent = await waitForSent("log")
    expect(sent.body).toEqual({ id: item.id, start: expect.stringMatching(/T14:00$/), end: expect.stringMatching(/T15:30$/) })
  })

  it("logs it once with Enter on Log it, and Enter on Cancel logs nothing", async () => {
    const { user, aside } = await detailOf((await assignment(3)).title)
    await user.click(within(aside).getByRole("button", { name: "Log time" }))
    let group = within(aside).getByRole("group", { name: "Time you worked" })
    within(group).getByRole("button", { name: "Cancel" }).focus()
    await user.keyboard("{Enter}")
    expect(within(aside).queryByRole("group", { name: "Time you worked" })).toBeNull()
    await user.click(within(aside).getByRole("button", { name: "Log time" }))
    group = within(aside).getByRole("group", { name: "Time you worked" })
    within(group).getByRole("button", { name: "Log it" }).focus()
    await user.keyboard("{Enter}")
    await waitForSent("log")
    await waitFor(() => expect(within(aside).queryByRole("group", { name: "Time you worked" })).toBeNull())
    expect(sent.filter((s) => s.name === "log")).toHaveLength(1)
  })

  it("starts the timer on it, then times another alongside", async () => {
    // two with nothing done yet (their detail says Start now, not Resume), neither what's on now
    await assignment(2)
    const now = await friday.q<{ current: { item_id: number } | null }>("now")
    const [a, b] = (await openAssignments()).filter((i) => i.id !== now.current?.item_id)
    for (const i of [a, b]) if (i.done_min) await friday.c("progress", { id: i.id, share: 0 })
    sent.length = 0 // those were the test's, not the page's
    const first = await detailOf(a.title)
    await first.user.click(within(first.aside).getByRole("button", { name: /Start now/ }))
    expect((await waitForSent("start")).body).toEqual({ id: first.item.id })
    await waitFor(() => expect(within(first.aside).queryByRole("button", { name: /Start now/ })).toBeNull(), { timeout: 5000 })
    first.unmount()
    const second = await detailOf(b.title)
    await second.user.click(await within(second.aside).findByRole("button", { name: /Start alongside/ }, { timeout: 5000 }))
    expect((await waitForSent("start")).body).toEqual({ id: second.item.id, alongside: true })
    await friday.c("stop", {})
  })

  it("marks it done and opens it again", async () => {
    const { user, aside, item } = await detailOf((await assignment(0)).title)
    await user.click(within(aside).getByRole("button", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: item.id })
    await user.click(await within(aside).findByRole("button", { name: "Open again" }, { timeout: 5000 }))
    expect((await waitForSent("reopen")).body).toEqual({ id: item.id })
  })

  it("shows a planned session on the plan", async () => {
    const { user, aside } = await detailOf(await plannedAssignment())
    await user.click(within(aside).getByRole("button", { name: "See on plan" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("opens a session's own day on the plan from its line", async () => {
    const { user, aside } = await detailOf(await plannedAssignment())
    const session = within(aside).getAllByRole("button").find((b) => /Planned · Friday decides|Pinned|Locked|Tentative/.test(b.textContent ?? ""))
    expect(session).toBeTruthy()
    await user.click(session as HTMLElement)
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("deletes a task that doesn't repeat at once", async () => {
    const { user, aside, item } = await detailOf((await assignment(0)).title)
    await user.click(within(aside).getByRole("button", { name: "Delete" }))
    expect((await waitForSent("drop")).body).toEqual({ id: item.id })
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
  })

  it("asks of a repeating task whether to delete this one or every one", async () => {
    const one = await detailOf("Laundry")
    expect(await within(one.aside).findByRole("button", { name: /^Days between Laundry/ }, { timeout: 5000 })).toBeTruthy()
    await one.user.click(within(one.aside).getByRole("button", { name: "Delete" }))
    await one.user.click(within(one.aside).getByRole("button", { name: "Just this one" }))
    expect((await waitForSent("drop")).body).toEqual({ id: one.item.id })
    one.unmount()
    const all = await detailOf("gym")
    await all.user.click(within(all.aside).getByRole("button", { name: "Delete" }))
    await all.user.click(within(all.aside).getByRole("button", { name: "Every one" }))
    expect((await waitForSent("series_delete")).body).toEqual({ id: all.item.series_id })
  })

  it("keeps a repeating task's times apart", async () => {
    const { user, aside } = await detailOf("Laundry")
    const menu = await within(aside).findByRole("button", { name: "Days between Laundry" }, { timeout: 5000 })
    await user.click(menu)
    const options = within(aside).getAllByRole("option")
    await user.click(options.find((o) => /at least/.test(o.textContent ?? "")) as HTMLElement)
    expect((await waitForSent("series_spacing")).body).toMatchObject({ days: expect.any(Number) })
  })
})
