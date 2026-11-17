// Several tasks changed together from the bar that shows when you pick more than one on the To-do page: done or open
// again, the due, the estimate, the tag, the kind, Short or Long term, the rest of a task's detail, and delete. Each
// change is made task by task, said once, and undone together.
import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { friday, openFriday, sent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

const TIP = ": click for everything about it, double-click the title to rename"
const row = (title: string) => screen.findByTitle(`${title}${TIP}`, {}, { timeout: 10_000 })
const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title) as Item
/** The open assignments in Short term, soonest due first, each its own title: which are still open moves with the
 * planner too (17 Nov: with work going in as soon as there's time, Alex finished HW 10 and WebWork 10 and 11 early). */
const openAssignments = async () => {
  const list = async () => {
    const open = (await items()).filter((i) => i.status === "todo" && i.preset === "Assignment" && !i.long_term)
    return open
      .filter((i) => open.filter((o) => o.title === i.title).length === 1)
      .sort((a, b) => (a.due ?? "~").localeCompare(b.due ?? "~") || a.id - b.id)
      .map((i) => i.title)
  }
  // a few spares through the API when the sample has finished all but one or two, each due on a day of its own
  const open = await list()
  if (open.length >= 4) return open
  for (let k = open.length; k < 4; k++) await friday.c("add", { title: `Spare problem set ${++spares}`, preset: "Assignment", area: "MATH 1910", due: `${ymd(4 + spares)}T23:59`, duration_min: 120, firmness: "hard" })
  return list()
}
let spares = 0
/** A day as the API writes it, `days` from today on the page's clock (the server's): "2026-11-13". */
const ymd = (days: number) => {
  const d = new Date(Date.now() + days * 86_400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
type User = Awaited<ReturnType<typeof openFriday>>["user"]

/** Picks the tasks titled so: a click on the first, ⌘-click on the rest. */
async function pick(user: User, titles: string[]) {
  await user.click(await row(titles[0]))
  await user.keyboard("{Meta>}")
  for (const t of titles.slice(1)) await user.click(await row(t))
  await user.keyboard("{/Meta}")
  return screen.findByRole("toolbar", { name: `${titles.length} tasks picked` })
}

/** The toast a change is said in, once all of its steps are back. */
const said = (text: string) => screen.findByText(text, {}, { timeout: 8000 })

/** The bodies of each `name` sent, once there are `n`. */
async function sentEach(name: string, n: number) {
  await waitFor(() => expect(sent.filter((s) => s.name === name).length).toBeGreaterThanOrEqual(n), { timeout: 5000 })
  return sent.filter((s) => s.name === name).map((s) => s.body as Record<string, unknown>)
}

describe("the bar for several tasks", () => {
  it("marks them done together, and one Undo opens them all again", async () => {
    const [a, b] = await openAssignments()
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Done" }))
    const bodies = await sentEach("done", 2)
    expect(bodies.map((x) => x.id).sort()).toEqual([(await itemNamed(a)).id, (await itemNamed(b)).id].sort())
    expect(await said("Marked 2 tasks done. ⌘Z undoes it")).toBeTruthy()
    expect(screen.queryByRole("toolbar")).toBeNull()
    await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
    await sentEach("undo", 2)
    await waitFor(async () => expect([(await itemNamed(a)).status, (await itemNamed(b)).status]).toEqual(["todo", "todo"]), { timeout: 5000 })
  })

  it("opens done ones again together", async () => {
    const [a, b] = (await openAssignments()).slice(-2)
    for (const t of [a, b]) await friday.c("done", { id: (await itemNamed(t)).id })
    sent.length = 0 // those were the test's, not the page's
    const { user } = await openFriday("/todo")
    await user.click(screen.getByRole("button", { name: "View options" }))
    await user.click(screen.getByRole("button", { name: "Show done" }))
    await user.click(screen.getByRole("button", { name: "View options" }))
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Open again" }))
    expect((await sentEach("reopen", 2)).map((x) => x.id).sort()).toEqual([(await itemNamed(a)).id, (await itemNamed(b)).id].sort())
    expect(await said("Opened 2 tasks again. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect([(await itemNamed(a)).status, (await itemNamed(b)).status]).toEqual(["todo", "todo"]))
  })

  it("moves their due, or takes it off", async () => {
    // two due on different days
    const open = await Promise.all((await openAssignments()).map(itemNamed))
    const a = open[0]
    const b = open.find((i) => i.due?.slice(0, 10) !== a.due?.slice(0, 10)) as Item
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a.title, b.title])
    await user.click(within(bar).getByRole("button", { name: "Due" }))
    // They differ, so no due is lit.
    await user.click(within(bar).getByRole("button", { name: "Tomorrow" }))
    const bodies = await sentEach("edit", 2)
    for (const b of bodies) expect(b.due).toMatch(/T23:59$/)
    expect(await said("Moved the due of 2 tasks. ⌘Z undoes it")).toBeTruthy()
    // The bar stays for the next change.
    await user.click(within(screen.getByRole("toolbar")).getByRole("button", { name: "Due" }))
    await user.click(within(screen.getByRole("toolbar")).getByRole("button", { name: "No due date" }))
    expect(await said("Took the due off 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect([(await itemNamed(a.title)).due, (await itemNamed(b.title)).due]).toEqual([null, null]))
    for (const i of [a, b]) await friday.c("edit", { id: i.id, due: i.due }) // their own dues again, for the tests after
  })

  it("gives each a little more or less time, or all of them one length", async () => {
    // two open assignments made 4h and 2h, none of either done, so each row shows its whole length: which are open,
    // how long and how far along depends on the day the sample is lived to
    const [long, short] = (await Promise.all((await openAssignments()).slice(0, 2).map(itemNamed))).map((i, n) => ({ ...i, to: n ? 120 : 240 }))
    for (const t of [long, short]) {
      await friday.c("edit", { id: t.id, duration_min: t.to })
      await friday.c("progress", { id: t.id, share: 0 })
    }
    sent.length = 0 // those were the test's, not the page's
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [long.title, short.title])
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    expect(within(bar).getByText("Each its own")).toBeTruthy()
    await user.click(within(bar).getByRole("button", { name: "+30m" }))
    const more = await sentEach("edit", 2)
    expect(more.map((b) => b.duration_min).sort()).toEqual([150, 270])
    expect(await said("Gave 2 tasks 30m more. ⌘Z undoes it")).toBeTruthy()
    // The list read again before the next nudge, which starts from what it shows.
    await within(await row(long.title)).findByText("4h 30m", {}, { timeout: 8000 })
    await within(await row(short.title)).findByText("2h 30m", {}, { timeout: 8000 })
    sent.length = 0
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    await user.click(within(bar).getByRole("button", { name: "−15m" }))
    expect((await sentEach("edit", 2)).map((b) => b.duration_min).sort()).toEqual([135, 255])
    expect(await said("Took 2 tasks 15m off. ⌘Z undoes it")).toBeTruthy()
    await within(await row(long.title)).findByText("4h 15m", {}, { timeout: 8000 })
    await within(await row(short.title)).findByText("2h 15m", {}, { timeout: 8000 })
    sent.length = 0
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    await user.click(within(bar).getByRole("button", { name: "1h" }))
    expect((await sentEach("edit", 2)).map((b) => b.duration_min)).toEqual([60, 60])
    expect(await said("2 tasks expected to take 1h. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect([(await itemNamed(long.title)).duration_min, (await itemNamed(short.title)).duration_min]).toEqual([60, 60]))
    for (const t of [long, short]) await friday.c("edit", { id: t.id, duration_min: t.duration_min }) // their own lengths again
  })

  it("tags them, or takes the tag off", async () => {
    const [a, b] = await openAssignments()
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Tag" }))
    await user.click(within(bar).getByRole("button", { name: "Rocketry" }))
    for (const b of await sentEach("edit", 2)) expect(b.area).toBe("Rocketry")
    expect(await said("Tagged 2 tasks Rocketry. ⌘Z undoes it")).toBeTruthy()
    sent.length = 0
    await user.click(within(bar).getByRole("button", { name: "Tag" }))
    await user.click(within(bar).getByRole("button", { name: "No tag" }))
    for (const b of await sentEach("edit", 2)) expect(b.area).toBeNull()
    expect(await said("Took the tag off 2 tasks. ⌘Z undoes it")).toBeTruthy()
  })

  it("makes them another kind", async () => {
    const [a, b] = await openAssignments()
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Kind" }))
    await user.click(within(bar).getByRole("button", { name: "Errand" }))
    for (const x of await sentEach("edit", 2)) expect(x.preset).toBe("Errand")
    expect(await said("Made 2 tasks Errand. ⌘Z undoes it")).toBeTruthy()
    await waitFor(async () => expect([(await itemNamed(a)).preset, (await itemNamed(b)).preset]).toEqual(["Errand", "Errand"]))
    for (const t of [a, b]) await friday.c("edit", { id: (await itemNamed(t)).id, preset: "Assignment" }) // assignments again, for the tests after
  })

  it("sets the rest of a task's detail for all of them, each choice lit when they share it", async () => {
    // two with hard deadlines; how much the sample did depends on the day it's lived to: none of one, some of the other
    const hard = (await Promise.all((await openAssignments()).map(itemNamed))).filter((i) => i.firmness === "hard")
    const [hw, begun] = hard.map((i) => i.title)
    await friday.c("progress", { id: (await itemNamed(hw)).id, share: 0 })
    await friday.c("progress", { id: (await itemNamed(begun)).id, share: 0.3125 })
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [hw, begun])
    const more = async () => {
      sent.length = 0
      await user.click(within(bar).getByRole("button", { name: "More" }))
    }
    await more()
    expect(within(bar).getByRole("button", { name: "Hard" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(within(bar).getByRole("button", { name: "Soft" }))
    for (const b of await sentEach("edit", 2)) expect(b.firmness).toBe("soft")
    expect(await said("Made the deadline soft for 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "⏳ Pointless" }))
    for (const b of await sentEach("edit", 2)) expect(b.expires).toBe(true)
    expect(await said("2 tasks never planned after their due. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "Still worth doing" }))
    expect(await said("2 tasks planned late if they can't be on time. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "Runs by itself" }))
    for (const b of await sentEach("edit", 2)) expect(b.background).toBe(true)
    expect(await said("2 tasks run by themselves. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "You work on it" }))
    expect(await said("2 tasks need you the whole time. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "10 min" }))
    for (const b of await sentEach("edit", 2)) expect(b).toMatchObject({ buffer_before_min: 10, buffer_after_min: 10 })
    expect(await said("10 min kept free around 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getAllByRole("button", { name: "None" }).at(-1) as HTMLElement)
    expect(await said("Nothing kept free around 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "Might not happen" }))
    for (const b of await sentEach("edit", 2)) expect(b.certainty).toBe("tentative")
    expect(await said("2 tasks planned loosely. ⌘Z undoes it")).toBeTruthy()
    await more()
    await user.click(within(bar).getByRole("button", { name: "Planned as usual" }))
    expect(await said("2 tasks planned as usual. ⌘Z undoes it")).toBeTruthy()
    // Only the one with work done starts over.
    await more()
    expect(within(bar).getByText("1 task with work done: count none of it, and Friday plans all of it again.")).toBeTruthy()
    await user.click(within(bar).getByRole("button", { name: "Start over" }))
    const over = await sentEach("progress", 1)
    expect(over).toEqual([{ id: (await itemNamed(begun)).id, share: 0 }])
    expect(await said("Started 1 task over. ⌘Z undoes it")).toBeTruthy()
  })

  it("closes an open menu with Escape and keeps what's picked", async () => {
    const [a, b] = await openAssignments()
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Kind" }))
    expect(within(bar).getByRole("button", { name: "Kind" }).getAttribute("aria-expanded")).toBe("true")
    await user.keyboard("{Escape}")
    expect(screen.getByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull())
  })

  it("moves them to Long term and back", async () => {
    const [a, b] = (await openAssignments()).slice(-2)
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "To Long term" }))
    for (const b of await sentEach("edit", 2)) expect(b.long_term).toBe(true)
    expect(await said("Moved 2 tasks to Long term. ⌘Z undoes it")).toBeTruthy()
    expect(screen.queryByRole("toolbar")).toBeNull()
    sent.length = 0
    await user.click(within(screen.getByRole("group", { name: "List" })).getByRole("button", { name: "Long term" }))
    const back = await pick(user, [a, b])
    await user.click(within(back).getByRole("button", { name: "To Short term" }))
    for (const b of await sentEach("edit", 2)) expect(b.long_term).toBe(false)
    expect(await said("Moved 2 tasks to Short term. ⌘Z undoes it")).toBeTruthy()
  })

  it("deletes them together", async () => {
    const [a, b] = await openAssignments()
    const { user } = await openFriday("/todo")
    const bar = await pick(user, [a, b])
    await user.click(within(bar).getByRole("button", { name: "Delete" }))
    expect((await sentEach("drop", 2)).map((x) => x.id).sort()).toEqual([(await itemNamed(a)).id, (await itemNamed(b)).id].sort())
    expect(await said("Deleted 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await waitFor(() => expect(screen.queryByTitle(`${a}${TIP}`)).toBeNull())
    expect(screen.queryByTitle(`${b}${TIP}`)).toBeNull()
  })
})
