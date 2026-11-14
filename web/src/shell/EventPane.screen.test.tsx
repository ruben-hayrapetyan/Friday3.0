// The event drawer (COMBINED.md 12): a new event drafted from the menu or a double-click, its title, day and times,
// all day, a repeat, where, the calendar, a color and notes, sent as one `add`; an event opened again, saved with
// `edit`, a repeat asking which times, and deleting one, this one or every one.
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

const host = (action: string) => act(() => void window.dispatchEvent(new CustomEvent("friday:host", { detail: { action } })))
const field = (name: string) => screen.getByRole("textbox", { name }) as HTMLInputElement

/** A day this many days on, "YYYY-MM-DD", local. */
function dayOn(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** A time box, retyped the way you'd say it, and left. */
async function retime(user: Awaited<ReturnType<typeof openFriday>>["user"], name: string, typed: string) {
  const box = field(name)
  await user.clear(box)
  await user.type(box, typed)
  await user.tab()
}

/** The drawer opened on an event found with search, as you'd find one. */
async function openEvent(user: Awaited<ReturnType<typeof openFriday>>["user"], title: string) {
  await user.keyboard("{Meta>}k{/Meta}")
  await user.type(await screen.findByRole("textbox", { name: "Search" }), title)
  const dialog = screen.getByRole("dialog", { name: "Search" })
  await within(dialog).findByText("Events", {}, { timeout: 5000 })
  await user.click(within(dialog).getAllByRole("button", { name: new RegExp(`^${title}`) })[0])
  await waitFor(() => expect(field("Title").value).toBe(title))
}

type Item = { id: number; title: string; start: string | null; end: string | null; notes: string; color: string | null; location: string | null; series_id: number | null; status: string }
/** The events whose titles have these words, as search finds them. */
const events = (text: string) => friday.q<Item[]>("events", { text, limit: "20" })

describe("a new event", () => {
  it("opens with its title focused, a draft an hour long, and Add waits for a title", async () => {
    await openFriday("/")
    await host("newEvent")
    expect(await screen.findByText("New event")).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(field("Title")))
    expect(screen.getByText(/· 1 h$/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Add" }).hasAttribute("disabled")).toBe(true)
    expect(screen.getByRole("combobox", { name: "Calendar" })).toBeTruthy()
    expect(screen.getByRole("radio", { name: "Automatic" }).getAttribute("aria-checked")).toBe("true")
    expect(screen.getByText("⌘↩ saves · Esc closes")).toBeTruthy()
  })

  it("is added with everything you gave it: title, day, times, where, color and notes", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await screen.findByText("New event")
    const day = dayOn(3)
    await user.type(field("Title"), "Coffee with Sam")
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: day } })
    await retime(user, "Starts", "3pm")
    await retime(user, "Ends", "4:30pm")
    expect(screen.getByText(/3pm–4:30pm · 1 h 30 min/)).toBeTruthy()
    await user.type(field("Where"), "Libe Café")
    await user.click(screen.getByRole("radio", { name: "Cerulean" }))
    expect(screen.getByRole("radio", { name: "Cerulean" }).getAttribute("aria-checked")).toBe("true")
    expect(screen.getAllByText("Cerulean").length).toBeGreaterThan(0)
    await user.type(screen.getByRole("textbox", { name: "Notes" }), "Bring the problem set")
    expect(screen.getByText("Do I have time for this?")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add" }))
    const sent = await waitForSent("add")
    expect(sent.body).toMatchObject({ title: "Coffee with Sam", start: `${day}T15:00`, end: `${day}T16:30`, color: "blue", notes: "Bring the problem set", location: "Libe Café", when: "fixed", blocks_time: true })
    await waitFor(() => expect(screen.queryByText("New event")).toBeNull())
    expect(await screen.findByText("Added Coffee with Sam")).toBeTruthy()
    await waitFor(async () => expect((await events("Coffee with Sam")).find((i) => i.title === "Coffee with Sam")?.start).toBe(`${day}T15:00`))
  })

  it("says whether you have time for it, quickly and then exactly", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Long hike")
    expect(await screen.findByText("Checking whether you have time…")).toBeTruthy()
    const exactly = await screen.findByRole("button", { name: "Check exactly" }, { timeout: 8000 })
    await user.click(exactly)
    await waitFor(() => expect(screen.queryByRole("button", { name: /Check exactly|Planning it/ })).toBeNull(), { timeout: 20_000 })
  })

  it("an end before its start runs past midnight", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Late show")
    const day = dayOn(4)
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: day } })
    await retime(user, "Starts", "11pm")
    await retime(user, "Ends", "1am")
    expect(screen.getByText(/11pm–1am · 2 h/)).toBeTruthy()
    await user.keyboard("{Meta>}{Enter}{/Meta}")
    const sent = await waitForSent("add")
    expect(sent.body).toMatchObject({ title: "Late show", start: `${day}T23:00`, end: `${dayOn(5)}T01:00` })
  })

  it("all day, runs from one day to another, and keeps no time from work", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Family visit")
    const from = dayOn(6)
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: from } })
    await user.click(screen.getByRole("switch", { name: "All day" }))
    expect(screen.getByRole("switch", { name: "All day" }).getAttribute("aria-checked")).toBe("true")
    expect(screen.queryByRole("textbox", { name: "Starts" })).toBeNull()
    expect(screen.getByText(/, all day$/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Last day"), { target: { value: dayOn(7) } })
    expect(screen.getByText(/ to .*, all day$/)).toBeTruthy()
    expect(screen.queryByText("Do I have time for this?")).toBeNull()
    await user.click(screen.getByRole("button", { name: "Add" }))
    const sent = await waitForSent("add")
    expect(sent.body).toMatchObject({ title: "Family visit", start: `${from}T00:00`, end: `${dayOn(8)}T00:00`, blocks_time: false })
  })

  it("all day switched off again goes back to nine to ten", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await screen.findByText("New event")
    await user.click(screen.getByRole("switch", { name: "All day" }))
    await user.click(screen.getByRole("switch", { name: "All day" }))
    expect(screen.getByRole("textbox", { name: "Starts" })).toBeTruthy()
    expect(screen.getByText(/9am–10am · 1 h/)).toBeTruthy()
  })

  it("repeats every week on its day, a certain few days, or a number of times", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Choir")
    const day = dayOn(2)
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: day } })
    const weekday = new Date(`${day}T12:00:00`).toLocaleString("en-US", { weekday: "long" })
    const code = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"][new Date(`${day}T12:00:00`).getDay()]
    await user.click(screen.getByRole("button", { name: "Repeats" }))
    const list = screen.getByRole("listbox", { name: "Repeats" })
    for (const label of ["Doesn't repeat", "Every day", `Every week on ${weekday}`, `Every other ${weekday}`, "Every weekday (Mon–Fri)", "Certain days…"]) expect(within(list).getByRole("option", { name: label })).toBeTruthy()
    await user.click(within(list).getByRole("option", { name: `Every week on ${weekday}` }))
    expect(screen.getByText(new RegExp(`every week on ${weekday}$`))).toBeTruthy()
    // a certain few days: its own day, and another
    await user.click(screen.getByRole("button", { name: "Repeats" }))
    await user.click(screen.getByRole("option", { name: "Certain days…" }))
    const days = screen.getByRole("group", { name: "On these days" })
    expect(within(days).getByRole("button", { name: code }).getAttribute("aria-pressed")).toBe("true")
    const other = code === "SA" ? "SU" : "SA"
    await user.click(within(days).getByRole("button", { name: other }))
    expect(within(days).getByRole("button", { name: other }).getAttribute("aria-pressed")).toBe("true")
    // taking its last day off leaves the one that's left
    await user.click(within(days).getByRole("button", { name: other }))
    await user.click(within(days).getByRole("button", { name: code }))
    expect(within(days).getByRole("button", { name: code }).getAttribute("aria-pressed")).toBe("true")
    await user.click(within(days).getByRole("button", { name: other }))
    // ends after ten times, then twelve
    await user.click(screen.getByRole("button", { name: "After" }))
    const times = screen.getByRole("spinbutton", { name: "Times" }) as HTMLInputElement
    expect(times.value).toBe("10")
    fireEvent.change(times, { target: { value: "12" } })
    expect(screen.getByText(/, 12 times$/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Add" }))
    const sent = await waitForSent("add")
    const order = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    const byday = [code, other].sort((a, b) => order.indexOf(a) - order.indexOf(b)).join(",")
    expect((sent.body as { every: string }).every).toBe(`rrule:FREQ=WEEKLY;BYDAY=${byday};COUNT=12`)
    await waitFor(() => expect(screen.queryByText("New event")).toBeNull())
  })

  it("never repeating again, after picking one", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Dentist")
    await user.click(screen.getByRole("button", { name: "Repeats" }))
    await user.click(screen.getByRole("option", { name: "Every day" }))
    await user.click(screen.getByRole("button", { name: "Never" }))
    await user.click(screen.getByRole("button", { name: "Repeats" }))
    await user.click(screen.getByRole("option", { name: "Doesn't repeat" }))
    expect(screen.queryByRole("button", { name: "Never" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByText("New event")).toBeNull())
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull()
  })

  it("Escape closes the drawer without adding anything, and Return in the title adds it", async () => {
    const { user } = await openFriday("/")
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Never mind")
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByText("New event")).toBeNull())
    await host("newEvent")
    await user.type(await screen.findByRole("textbox", { name: "Title" }), "Call home{Enter}")
    expect((await waitForSent("add")).body).toMatchObject({ title: "Call home", when: "fixed" })
  })

  it("can be started with a double-click on empty time on the calendar", async () => {
    // happy-dom can't say what's under the pointer; nothing is, here
    if (typeof document.elementsFromPoint !== "function") Object.assign(document, { elementsFromPoint: () => [] })
    const { user } = await openFriday("/")
    const column = await waitFor(() => {
      const found = document.querySelector<HTMLElement>("[data-top-min]")
      expect(found).not.toBeNull()
      return found!
    }, { timeout: 10_000 })
    await user.dblClick(column)
    expect((await screen.findAllByText("New event")).length).toBeGreaterThan(0)
    expect(screen.getByRole("textbox", { name: "Title" })).toBeTruthy()
  })
})

describe("an event opened again", () => {
  it("saves a new title, time and notes with edit, and is deleted with Delete", async () => {
    const day = dayOn(5)
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Office hours visit", when: "fixed", start: `${day}T14:00`, end: `${day}T14:30` })
    const id = made.result.item.id
    const { user } = await openFriday("/")
    await openEvent(user, "Office hours visit")
    expect(screen.getByText("Event")).toBeTruthy()
    expect(screen.getByText("Only Friday")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Repeats" })).toBeTruthy() // made once in Friday: it can be made to repeat
    await user.clear(field("Title"))
    await user.type(field("Title"), "Office hours with Prof. Lee")
    await retime(user, "Ends", "3pm")
    await user.type(screen.getByRole("textbox", { name: "Notes" }), "Ask about the prelim")
    await user.click(screen.getByRole("button", { name: "Save" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ id, title: "Office hours with Prof. Lee", start: `${day}T14:00`, end: `${day}T15:00`, notes: "Ask about the prelim" })
    expect(sent.body).not.toHaveProperty("blocks_time") // all day didn't change: whether it keeps time isn't sent
    await waitFor(async () => expect((await events("Office hours")).find((i) => i.id === id)?.title).toBe("Office hours with Prof. Lee"))
    await openEvent(user, "Office hours with Prof. Lee")
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect((await waitForSent("drop")).body).toEqual({ id })
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull())
  })

  it("asks whether work may take its time, and saves your answer", async () => {
    const day = dayOn(6)
    await friday.c("add", { title: "Pottery class", when: "fixed", start: `${day}T18:00`, end: `${day}T19:00` })
    const { user, client } = await openFriday("/")
    await openEvent(user, "Pottery class")
    const choice = await screen.findByRole("group", { name: "Can work take Pottery class's time?" })
    expect(within(choice).getByRole("button", { name: "No" }).getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByText("Work keeps off it.")).toBeTruthy()
    await user.click(within(choice).getByRole("button", { name: "If I'm ahead" }))
    expect((await waitForSent("event_optional")).body).toEqual({ title: "Pottery class", mode: "ahead" })
    await waitFor(async () => expect((await friday.q<{ mode: string }>("event_mode", { title: "Pottery class" })).mode).toBe("ahead"))
    await user.click(within(screen.getByRole("group", { name: "Can work take Pottery class's time?" })).getByRole("button", { name: "If work needs it" }))
    expect((await waitForSent("event_optional")).body).toEqual({ title: "Pottery class", mode: "optional" })
    await waitFor(async () => expect((await friday.q<{ mode: string }>("event_mode", { title: "Pottery class" })).mode).toBe("optional"))
    // opened again, it says so, and asks whether you have time to go
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await client.invalidateQueries() // what Friday's live updates do in a browser
    await openEvent(user, "Pottery class")
    expect(await screen.findByText(/Friday uses its time only when work would be late otherwise/)).toBeTruthy()
    expect(await screen.findByText("Do I have time to go?")).toBeTruthy()
  })

  it("made to repeat from its own day and time", async () => {
    const day = dayOn(2)
    const made = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Lab meeting", when: "fixed", start: `${day}T16:00`, end: `${day}T17:00` })
    const { user } = await openFriday("/")
    await openEvent(user, "Lab meeting")
    await user.click(screen.getByRole("button", { name: "Repeats" }))
    await user.click(screen.getByRole("option", { name: "Every day" }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    await waitForSent("edit")
    expect((await waitForSent("repeat")).body).toEqual({ id: made.result.item.id, every: "rrule:FREQ=DAILY" })
    expect(await screen.findByText(/Repeats every day/)).toBeTruthy()
  })
})

describe("a repeating event", () => {
  it("asks which times a change is for: this time only, or this and later", async () => {
    const day = dayOn(1)
    const code = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"][new Date(`${day}T12:00:00`).getDay()]
    await friday.c("add", { title: "Swim practice", when: "fixed", start: `${day}T07:00`, end: `${day}T08:00`, every: `rrule:FREQ=WEEKLY;BYDAY=${code}` })
    const { user } = await openFriday("/")
    await openEvent(user, "Swim practice")
    expect(await screen.findByText("Saving asks: this time, or this and later.")).toBeTruthy()
    await user.clear(field("Notes"))
    await user.type(screen.getByRole("textbox", { name: "Notes" }), "Bring goggles")
    await user.click(screen.getByRole("button", { name: "Save" }))
    const which = screen.getByRole("group", { name: "Change which times" })
    expect(within(which).getByText("Change which times of Swim practice?")).toBeTruthy()
    await user.click(within(which).getByRole("button", { name: "Back" }))
    expect(screen.queryByRole("group", { name: "Change which times" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Save" }))
    await user.click(within(screen.getByRole("group", { name: "Change which times" })).getByRole("button", { name: "This and later times" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ notes: "Bring goggles", from_date: day })
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull())
  })

  it("this time only leaves the others as they were", async () => {
    const { user } = await openFriday("/")
    await openEvent(user, "Swim practice")
    await user.type(screen.getByRole("textbox", { name: "Where" }), "Teagle pool")
    await user.click(screen.getByRole("button", { name: "Save" }))
    await user.click(await screen.findByRole("button", { name: "This time only" }))
    const sent = await waitForSent("edit")
    expect(sent.body).toMatchObject({ location: "Teagle pool" })
    expect(sent.body).not.toHaveProperty("from_date")
  })

  it("a new way of repeating changes this time and the later ones, in one command", async () => {
    const { user } = await openFriday("/")
    await openEvent(user, "Swim practice")
    await user.click(await screen.findByRole("button", { name: "Repeats" }))
    await user.click(screen.getByRole("option", { name: "Every day" }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(screen.getByRole("button", { name: "This time only" }).hasAttribute("disabled")).toBe(true)
    await user.click(screen.getByRole("button", { name: "This and later times" }))
    const sent = await waitForSent("series_edit")
    expect(sent.body).toMatchObject({ every: "rrule:FREQ=DAILY", title: "Swim practice" })
  })

  it("deletes just this one, or every one", async () => {
    const day = dayOn(3)
    await friday.c("add", { title: "Reading group", when: "fixed", start: `${day}T12:00`, end: `${day}T13:00`, every: "rrule:FREQ=DAILY;COUNT=5" })
    const { user } = await openFriday("/")
    await openEvent(user, "Reading group")
    await user.click(screen.getByRole("button", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Just this one" }))
    await waitForSent("skip")
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull())
    await openEvent(user, "Reading group")
    await user.click(screen.getByRole("button", { name: "Delete" }))
    await user.click(field("Title"))
    await user.keyboard("{Escape}") // the question first: the drawer stays
    expect(screen.getByRole("textbox", { name: "Title" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Delete" }))
    await user.click(screen.getByRole("button", { name: "Every one" }))
    const sent = await waitForSent("series_delete")
    expect(sent.body).toHaveProperty("id")
    await waitFor(async () => expect((await events("Reading group")).filter((i) => i.title === "Reading group" && i.status === "todo")).toHaveLength(0))
  })
})
