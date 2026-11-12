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
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 9", "MATH 1910 Written HW 10"])
    await user.click(within(bar).getByRole("button", { name: "Done" }))
    const bodies = await sentEach("done", 2)
    expect(bodies.map((b) => b.id).sort()).toEqual([(await itemNamed("MATH 1910 Written HW 9")).id, (await itemNamed("MATH 1910 Written HW 10")).id].sort())
    expect(await said("Marked 2 tasks done. ⌘Z undoes it")).toBeTruthy()
    expect(screen.queryByRole("toolbar")).toBeNull()
    await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1) as HTMLElement)
    await sentEach("undo", 2)
    await waitFor(async () => expect((await itemNamed("MATH 1910 Written HW 9")).status).toBe("todo"), { timeout: 5000 })
  })

  it("opens done ones again together", async () => {
    await friday.c("done", { id: (await itemNamed("PHYS 1112 Mastering Physics 11")).id })
    await friday.c("done", { id: (await itemNamed("PHYS 1112 Mastering Physics 12")).id })
    const { user } = await openFriday("/todo")
    await user.click(screen.getByRole("button", { name: "View options" }))
    await user.click(screen.getByRole("button", { name: "Show done" }))
    await user.click(screen.getByRole("button", { name: "View options" }))
    const bar = await pick(user, ["PHYS 1112 Mastering Physics 11", "PHYS 1112 Mastering Physics 12"])
    await user.click(within(bar).getByRole("button", { name: "Open again" }))
    expect(await sentEach("reopen", 2)).toHaveLength(2)
    expect(await said("Opened 2 tasks again. ⌘Z undoes it")).toBeTruthy()
  })

  it("moves their due, or takes it off", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 WebWork 10", "MATH 1910 WebWork 11"])
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
  })

  it("gives each a little more or less time, or all of them one length", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["CHEM 2090 lab report 6", "MATH 1910 Written HW 11"])
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    expect(within(bar).getByText("Each its own")).toBeTruthy()
    await user.click(within(bar).getByRole("button", { name: "+30m" }))
    const more = await sentEach("edit", 2)
    expect(more.map((b) => b.duration_min).sort()).toEqual([150, 270])
    expect(await said("Gave 2 tasks 30m more. ⌘Z undoes it")).toBeTruthy()
    // The list read again before the next nudge, which starts from what it shows.
    await within(await row("CHEM 2090 lab report 6")).findByText("4h 30m", {}, { timeout: 8000 })
    await within(await row("MATH 1910 Written HW 11")).findByText("2h 30m", {}, { timeout: 8000 })
    sent.length = 0
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    await user.click(within(bar).getByRole("button", { name: "−15m" }))
    expect((await sentEach("edit", 2)).map((b) => b.duration_min).sort()).toEqual([135, 255])
    expect(await said("Took 2 tasks 15m off. ⌘Z undoes it")).toBeTruthy()
    await within(await row("CHEM 2090 lab report 6")).findByText("4h 15m", {}, { timeout: 8000 })
    await within(await row("MATH 1910 Written HW 11")).findByText("2h 15m", {}, { timeout: 8000 })
    sent.length = 0
    await user.click(within(bar).getByRole("button", { name: "Estimate" }))
    await user.click(within(bar).getByRole("button", { name: "1h" }))
    expect((await sentEach("edit", 2)).map((b) => b.duration_min)).toEqual([60, 60])
    expect(await said("2 tasks expected to take 1h. ⌘Z undoes it")).toBeTruthy()
  })

  it("tags them, or takes the tag off", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 8", "CHEM 2090 lab report 6"])
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
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 8", "CHEM 2090 lab report 6"])
    await user.click(within(bar).getByRole("button", { name: "Kind" }))
    await user.click(within(bar).getByRole("button", { name: "Errand" }))
    for (const b of await sentEach("edit", 2)) expect(b.preset).toBe("Errand")
    expect(await said("Made 2 tasks Errand. ⌘Z undoes it")).toBeTruthy()
  })

  it("sets the rest of a task's detail for all of them, each choice lit when they share it", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 8", "FWS essay draft"])
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
    expect(over).toEqual([{ id: (await itemNamed("FWS essay draft")).id, share: 0 }])
    expect(await said("Started 1 task over. ⌘Z undoes it")).toBeTruthy()
  })

  it("closes an open menu with Escape and keeps what's picked", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 8", "CHEM 2090 lab report 6"])
    await user.click(within(bar).getByRole("button", { name: "Kind" }))
    expect(within(bar).getByRole("button", { name: "Kind" }).getAttribute("aria-expanded")).toBe("true")
    await user.keyboard("{Escape}")
    expect(screen.getByRole("toolbar", { name: "2 tasks picked" })).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull())
  })

  it("moves them to Long term and back", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 11", "MATH 1910 WebWork 11"])
    await user.click(within(bar).getByRole("button", { name: "To Long term" }))
    for (const b of await sentEach("edit", 2)) expect(b.long_term).toBe(true)
    expect(await said("Moved 2 tasks to Long term. ⌘Z undoes it")).toBeTruthy()
    expect(screen.queryByRole("toolbar")).toBeNull()
    sent.length = 0
    await user.click(within(screen.getByRole("group", { name: "List" })).getByRole("button", { name: "Long term" }))
    const back = await pick(user, ["MATH 1910 Written HW 11", "MATH 1910 WebWork 11"])
    await user.click(within(back).getByRole("button", { name: "To Short term" }))
    for (const b of await sentEach("edit", 2)) expect(b.long_term).toBe(false)
    expect(await said("Moved 2 tasks to Short term. ⌘Z undoes it")).toBeTruthy()
  })

  it("deletes them together", async () => {
    const { user } = await openFriday("/todo")
    const bar = await pick(user, ["MATH 1910 Written HW 9", "MATH 1910 Written HW 10"])
    await user.click(within(bar).getByRole("button", { name: "Delete" }))
    expect(await sentEach("drop", 2)).toHaveLength(2)
    expect(await said("Deleted 2 tasks. ⌘Z undoes it")).toBeTruthy()
    await waitFor(() => expect(screen.queryByTitle(`MATH 1910 Written HW 9${TIP}`)).toBeNull())
  })
})
