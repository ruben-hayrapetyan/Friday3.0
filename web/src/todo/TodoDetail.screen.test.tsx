// One task's detail beside the To-do list: its tag, kind and due from their pickers, how firm the deadline is,
// whether it's pointless late or runs by itself, the estimate, time to get there, how much is done, time logged
// without the timer, Start, Done, See on plan, and Delete (one of a repeat, or every one).
import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Item } from "@/api/client"
import { friday, openFriday, waitForSent } from "@/test/friday"

// A real server, replanning after each change: a moment longer than the default second to answer.
configure({ asyncUtilTimeout: 5000 })

const items = () => friday.q<Item[]>("items", { status: "all" })
const itemNamed = async (title: string) => (await items()).find((i) => i.title === title && i.status === "todo") as Item

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
    const { user, aside } = await detailOf("CHEM 2090 lab report 6")
    expect(within(aside).getByText("CHEM 2090 lab report 6")).toBeTruthy()
    expect(within(aside).getByText("4h to do")).toBeTruthy()
    expect(within(aside).getByText("4h left")).toBeTruthy()
    expect(within(aside).getByRole("slider", { name: "How much is done" }).getAttribute("aria-valuenow")).toBe("0")
    await user.click(within(aside).getByRole("button", { name: "Close" }))
    await waitFor(() => expect(screen.queryByText("Planned sessions")).toBeNull())
    expect(window.location.hash).not.toContain("item=")
  })

  it("changes the tag and the kind from their pickers", async () => {
    const { user, aside, item } = await detailOf("MATH 1910 Written HW 10")
    await user.click(within(aside).getByRole("button", { name: "MATH 1910" }))
    await user.click(within(aside).getByRole("button", { name: "Rocketry" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, area: "Rocketry" })
    await user.click(await within(aside).findByRole("button", { name: "Assignment" }))
    await user.click(within(aside).getByRole("button", { name: "Errand" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, preset: "Errand" })
    await waitFor(async () => expect((await itemNamed("MATH 1910 Written HW 10")).preset).toBe("Errand"))
  })

  it("moves the due with a quick pick, keeping its time of day", async () => {
    const { user, aside, item } = await detailOf("MATH 1910 Written HW 11")
    await user.click(within(aside).getByRole("button", { name: /^Fri 4 Dec|11:59pm/ }))
    expect(within(aside).getByText(/^Now: Due/)).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "In a week" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toEqual({ id: item.id, due: expect.stringMatching(/T23:59$/) })
    await user.click(within(aside).getByRole("button", { name: "No due date" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, due: null })
  })

  it("sets how firm the deadline is, whether it's pointless late, and whether it runs by itself", async () => {
    const { user, aside, item } = await detailOf("PHYS 1112 Mastering Physics 11")
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
  })

  it("says exam prep is pointless late by default", async () => {
    const { aside } = await detailOf("Prep: MATH 1910 Prelim 2")
    expect(within(aside).getByText(/As for all exam prep\. Never planned after it's due\./)).toBeTruthy()
    expect(within(aside).getByRole("button", { name: "⏳ Pointless" }).getAttribute("aria-pressed")).toBe("true")
  })

  it("steps the estimate up and down, saved once the presses stop, or sets it from the picker", async () => {
    const { user, aside, item } = await detailOf("MATH 1910 WebWork 11")
    await user.click(within(aside).getByRole("button", { name: "More: 1h 45m" }))
    await user.click(within(aside).getByRole("button", { name: "More: 2h" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toEqual({ id: item.id, duration_min: 120 })
    await waitFor(() => expect(within(aside).getByRole("button", { name: "Less: 1h 45m" })).toBeTruthy(), { timeout: 5000 })
    await user.click(within(aside).getByRole("button", { name: "Less: 1h 45m" }))
    await waitFor(async () => expect((await itemNamed("MATH 1910 WebWork 11")).duration_min).toBe(105), { timeout: 5000 })
    await user.click(within(aside).getByRole("button", { name: "Set" }))
    await user.click(within(aside).getByRole("button", { name: "3h" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, duration_min: 180 })
  })

  it("keeps time free around it to get there and back", async () => {
    const { user, aside, item } = await detailOf("MATH 1910 Written HW 9")
    expect(within(aside).getByText("Work can sit right up against it.")).toBeTruthy()
    await user.click(within(aside).getByRole("button", { name: "15 min" }))
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, buffer_before_min: 15, buffer_after_min: 15 })
    expect(await within(aside).findByText("15 min kept free before and after, to get there and back.")).toBeTruthy()
    await user.click(within(aside).getAllByRole("button", { name: "None" }).at(-1) as HTMLElement) // the deadline has a None too
    expect((await waitForSent("edit")).body).toEqual({ id: item.id, buffer_before_min: null, buffer_after_min: null })
  })

  it("says how much is done with the keyboard, and Start over counts none of it", async () => {
    const { user, aside, item } = await detailOf("FWS essay draft")
    expect(within(aside).getByText("3h 15m of 4h")).toBeTruthy()
    expect(within(aside).getByText("45m left · 3h 15m done")).toBeTruthy()
    expect(within(aside).getByRole("button", { name: /Resume/ })).toBeTruthy()
    const slider = within(aside).getByRole("slider", { name: "How much is done" })
    slider.focus()
    await user.keyboard("{ArrowLeft}")
    const sent = await waitForSent("progress")
    expect(sent.body).toEqual({ id: item.id, share: 0.75 })
    await user.keyboard("{ArrowRight}")
    expect((await waitForSent("progress")).body).toMatchObject({ id: item.id })
    await user.keyboard("{Home}")
    expect((await waitForSent("progress")).body).toEqual({ id: item.id, share: 0 })
    await user.keyboard("x") // not a key it takes
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
    await friday.c("progress", { id: (await itemNamed("FWS essay draft")).id, share: 0.5 })
    const { user, aside, item } = await detailOf("FWS essay draft")
    await user.click(await within(aside).findByRole("button", { name: "Start over" }))
    expect((await waitForSent("progress")).body).toEqual({ id: item.id, share: 0 })
  })

  it("logs time worked without the timer, and Cancel closes it", async () => {
    const { user, aside, item } = await detailOf("PHYS 1112 Mastering Physics 12")
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
    const { user, aside, item } = await detailOf("PHYS 1112 Mastering Physics 12")
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

  it("starts the timer on it, then times another alongside", async () => {
    const first = await detailOf("MATH 1910 WebWork 10")
    await first.user.click(within(first.aside).getByRole("button", { name: /Start now/ }))
    expect((await waitForSent("start")).body).toEqual({ id: first.item.id })
    await waitFor(() => expect(within(first.aside).queryByRole("button", { name: /Start now/ })).toBeNull(), { timeout: 5000 })
    first.unmount()
    const second = await detailOf("MATH 1910 Written HW 10")
    await second.user.click(await within(second.aside).findByRole("button", { name: /Start alongside/ }, { timeout: 5000 }))
    expect((await waitForSent("start")).body).toEqual({ id: second.item.id, alongside: true })
    await friday.c("stop", {})
  })

  it("marks it done and opens it again", async () => {
    const { user, aside, item } = await detailOf("PHYS 1112 Mastering Physics 10")
    await user.click(within(aside).getByRole("button", { name: "Mark done" }))
    expect((await waitForSent("done")).body).toEqual({ id: item.id })
    await user.click(await within(aside).findByRole("button", { name: "Open again" }, { timeout: 5000 }))
    expect((await waitForSent("reopen")).body).toEqual({ id: item.id })
  })

  it("shows a planned session on the plan", async () => {
    const { user, aside } = await detailOf("CHEM 2090 lab report 6")
    await user.click(within(aside).getByRole("button", { name: "See on plan" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("opens a session's own day on the plan from its line", async () => {
    const { user, aside } = await detailOf("CHEM 2090 lab report 6")
    const session = within(aside).getAllByRole("button").find((b) => /Planned · Friday decides|Pinned|Locked|Tentative/.test(b.textContent ?? ""))
    expect(session).toBeTruthy()
    await user.click(session as HTMLElement)
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("deletes a task that doesn't repeat at once", async () => {
    const { user, aside, item } = await detailOf("MATH 1910 Written HW 9")
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
    await user.click(options.find((o) => /At least/.test(o.textContent ?? "")) as HTMLElement)
    expect((await waitForSent("series_spacing")).body).toMatchObject({ days: expect.any(Number) })
  })
})
