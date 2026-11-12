// Settings → Calendars (COMBINED.md 17, 19, 28, 59, 60): what counts as busy, the time kept free around events, each
// calendar planned around, just shown or hidden and its pigment, the Mac's calendars, where new events go, and the
// categories with their filter; and the calendar lists in Integrations (Google's, read per event or as a kind; the
// Mac's, by account). Alex reads seven Google calendars through the demo's stand-in; the Mac's calendars, which only
// the Mac app sends, are answered here.

import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"
import { answer, answered } from "./screen.test.helpers"

type Settings = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
const settings = () => friday.q<Settings>("settings")

const undo: (() => void)[] = []
afterEach(() => {
  while (undo.length) undo.pop()!()
})

const field = (name: string) => screen.getByText(name, { selector: "span" }).closest(".fr-stack") as HTMLElement


const MAC = [
  { id: "mac-home", name: "Home", primary: false, on: true, kind: "auto", trusted: false, last_sync: "2026-11-11T08:00", error: null, writable: true, editable: false, account: "iCloud", also_google: false, color: null },
  { id: "mac-birthdays", name: "Birthdays", primary: false, on: false, kind: "auto", trusted: false, last_sync: null, error: null, writable: false, editable: false, account: "iCloud", also_google: false, color: null },
  { id: "mac-gmail", name: "aj452@cornell.edu", primary: false, on: false, kind: "auto", trusted: false, last_sync: null, error: null, writable: true, editable: false, account: "aj452@gmail.com", also_google: true, color: null },
]

describe("what counts as busy", () => {
  it("counts reminders, free events and what the filter hides, each when you say", async () => {
    const { user } = await openFriday("/settings/calendars")
    const reminders = await screen.findByRole("switch", { name: "Reminders that something is due" })
    expect(within(field("What counts as busy")).getAllByText(/^Left out · /)).toHaveLength(3)
    expect(screen.getByText("Left out · Set a filter under Categories")).toBeTruthy()
    await user.click(reminders)
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { count_filtered: false, count_free: false, count_reminders: true } })
    await user.click(screen.getByRole("switch", { name: "Events marked free" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { count_free: true } })
    await user.click(screen.getByRole("switch", { name: "Events the filter hides" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { count_filtered: true } })
  })
})

describe("time around events", () => {
  it("sets the same time before and after every event, or kind by kind", async () => {
    const { user, client } = await openFriday("/settings/calendars")
    const around = await waitFor(() => field("Time around events"))
    for (const chip of ["None", "10 min", "15 min", "30 min"]) expect(within(around).getByRole("button", { name: chip }).getAttribute("aria-pressed")).toBe("false")
    await user.click(within(around).getByRole("button", { name: "15 min" }))
    const all = (await waitForSent("settings_set")).body as { key: string; value: Record<string, { before_min: number; after_min: number }> }
    expect(all).toEqual({ key: "event_kinds", value: { class: { before_min: 15, after_min: 15 }, meeting: { before_min: 15, after_min: 15 }, exam: { before_min: 15, after_min: 15 }, other: { before_min: 15, after_min: 15 } } })
    await answered(client)
    await waitFor(() => expect(within(field("Time around events")).getByRole("button", { name: "15 min" }).getAttribute("aria-pressed")).toBe("true"))
    await user.click(within(field("Time around events")).getByRole("button", { name: "Before exams" }))
    await user.click(screen.getByRole("option", { name: "45 min" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "event_kinds", value: { exam: { before_min: 45, after_min: 15 } } })
    await user.click(within(field("Time around events")).getByRole("button", { name: "After everything else" }))
    await user.click(screen.getByRole("option", { name: "None" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "event_kinds", value: { other: { before_min: 15, after_min: 0 } } })
  })
})

describe("your calendars", () => {
  it("plans around a calendar, just shows it, or hides it, and keeps work off a hidden one", async () => {
    const { user, client } = await openFriday("/settings/calendars")
    const canvas = await screen.findByRole("group", { name: "Canvas on your calendar" })
    expect(within(canvas).getByRole("button", { name: "Plan around it" }).getAttribute("aria-pressed")).toBe("true")
    expect(screen.getAllByText("Shown; Friday keeps work off its events").length).toBe(7)
    await user.click(within(canvas).getByRole("button", { name: "Just show it" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { calendars: expect.objectContaining({ Canvas: false, Work: true }) } })
    await answered(client)
    expect(await screen.findByText("Shown dashed; Friday may plan work over it")).toBeTruthy()
    sent.length = 0
    await user.click(within(screen.getByRole("group", { name: "Clubs on your calendar" })).getByRole("button", { name: "Hide" }))
    await waitFor(() => expect(sent.filter((s) => s.name === "settings_set")).toHaveLength(2))
    expect(sent.map((s) => s.body)).toEqual([
      { key: "calendar_look", value: { colors: {}, toolbar: ["Clubs"], show_past_plan: true } },
      { key: "busy", value: expect.objectContaining({ calendars: expect.objectContaining({ Canvas: false, Clubs: false }) }) },
    ])
    await answered(client)
    expect(await screen.findByText("Hidden until you switch it on under Show")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Keep work off it anyway" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { calendars: expect.objectContaining({ Canvas: false, Clubs: true }) } })
    await answered(client)
    expect(await screen.findByText("Hidden, but Friday still keeps work off its events")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Let work go over it" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "busy", value: { calendars: expect.objectContaining({ Clubs: false }) } })
  })

  it("gives a calendar a pigment, and takes it off again", async () => {
    const { user, client } = await openFriday("/settings/calendars")
    const row = (await screen.findByRole("group", { name: "Work on your calendar" })).closest(".fr-row") as HTMLElement
    await user.click(within(row).getByRole("button", { name: "No pigment" }))
    await user.click(within(row).getByRole("option", { name: "Cerulean" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "calendar_look", value: { colors: { Work: "blue" } } })
    await answered(client)
    await waitFor(() => expect(within(row).getByRole("button", { name: "Cerulean" })).toBeTruthy())
    await user.click(within(row).getByRole("button", { name: "Cerulean" }))
    expect(within(row).getByRole("option", { name: "Cerulean" }).getAttribute("aria-selected")).toBe("true")
    await user.click(within(row).getByRole("option", { name: "No pigment" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "calendar_look", value: { colors: {} } })
  })

  it("puts new events on a calendar you choose, and Friday's events already made there too", async () => {
    const { user, client } = await openFriday("/settings/calendars")
    const to = (await screen.findByRole("combobox", { name: "New events go to" })) as HTMLSelectElement
    expect(to.value).toBe("")
    expect(screen.queryByRole("button", { name: "Put Friday’s events on it" })).toBeNull()
    await waitFor(() => expect(within(to).getAllByRole("option").length).toBeGreaterThan(1))
    const homework = within(to).getAllByRole("option").find((o) => o.textContent!.startsWith("Homework")) as HTMLOptionElement
    expect(homework, within(to).getAllByRole("option").map((o) => o.textContent).join(" | ")).toBeTruthy()
    await user.selectOptions(to, homework)
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gcal", value: { new_events_to: homework.value } })
    await answered(client)
    await user.click(await screen.findByRole("button", { name: "Put Friday’s events on it" }))
    await waitForSent("events_to_calendar")
    await user.selectOptions(screen.getByRole("combobox", { name: "New events go to" }), "")
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "gcal", value: { new_events_to: null } })
  })

  it("says the Mac's calendars come from the Mac app, and lists them once it sends them", async () => {
    const { unmount } = await openFriday("/settings/calendars")
    expect(await screen.findByText(/^These appear once the Mac app runs and may read your calendars/)).toBeTruthy()
    unmount()
    undo.push(answer("mac_calendars", () => ({ json: MAC })))
    const { user } = await openFriday("/settings/calendars")
    const mac = await waitFor(() => field("This Mac’s calendars"))
    await user.click(await within(mac).findByRole("button", { name: /^On this Mac 1 of 3 read: Home/ }))
    expect(within(mac).getByText("Not read: Friday reads it from Google")).toBeTruthy()
    expect(within(mac).getAllByText(/^Read /).length).toBeGreaterThan(0)
    expect(within(mac).getByText(/Calendars Friday already gets from Google, subscriptions and birthdays start off/)).toBeTruthy()
    await user.click(within(mac).getByRole("switch", { name: "Read Birthdays" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "mac-birthdays", on: true, mac: true })
    // off, and not one Friday may change: its switches do nothing
    sent.length = 0
    await user.click(within(mac).getByRole("switch", { name: "Birthdays straight to the plan" }))
    await user.click(within(mac).getByRole("switch", { name: "Save changes to Birthdays" }))
    expect(sent.filter((s) => s.name === "calendar_set")).toHaveLength(0)
    await user.click(within(mac).getByRole("switch", { name: "Save changes to Home" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "mac-home", editable: true, mac: true })
    // the Mac's Home is one more calendar to plan around, and to send new events to
    expect(screen.getByRole("group", { name: "Home on your calendar" })).toBeTruthy()
    expect(within(screen.getByRole("combobox", { name: "New events go to" })).getByRole("option", { name: "Home · iCloud, through this Mac" })).toBeTruthy()
  })
})

describe("Google's calendars, in its box", () => {
  it("reads a calendar's events as one kind, and saves changes back to it or not", async () => {
    const { user } = await openFriday("/settings/integrations")
    await user.click(await screen.findByRole("button", { name: /^Google Calendar, / }))
    const dialog = screen.getByRole("dialog", { name: "Google Calendar" })
    await user.click(await within(dialog).findByRole("button", { name: /^Calendars \d+ of \d+ read/ }))
    await user.click(within(dialog).getByRole("button", { name: "How Homework is read" }))
    await user.click(within(dialog).getByRole("option", { name: "Assignment" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "homework@g", kind: "Assignment", mac: false })
    await user.click(within(dialog).getByRole("switch", { name: "Save changes to Homework" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "homework@g", editable: false, mac: false })
    await user.click(within(dialog).getByRole("switch", { name: "Read Personal" }))
    expect((await waitForSent("calendar_set")).body).toEqual({ id: "personal@g", on: false, mac: false })
  })
})

describe("the Mac's calendars, in their box", () => {
  it("lists them by account, what's left off as a count, and where to choose which count", async () => {
    undo.push(answer("mac_calendars", () => ({ json: MAC })))
    const { user } = await openFriday("/settings/integrations")
    await user.click(await screen.findByRole("button", { name: "Calendars on this Mac, Reading 1" }))
    const dialog = screen.getByRole("dialog", { name: "Calendars on this Mac" })
    expect(within(dialog).getByText("Reading 1")).toBeTruthy()
    expect(within(dialog).getByText("iCloud")).toBeTruthy()
    expect(within(dialog).getByText(/Birthdays left off/)).toBeTruthy()
    expect(within(dialog).getByRole("link", { name: "Add an account to this Mac…" }).getAttribute("href")).toContain("Internet-Accounts")
    await user.click(within(dialog).getByRole("button", { name: "Choose which calendars count" }))
    await waitFor(() => expect(window.location.hash).toBe("#/settings/calendars"))
  })
})

describe("categories", () => {
  const names = () => (screen.getAllByRole("textbox", { name: "Category name" }) as HTMLInputElement[]).map((i) => i.value)

  it("edits a category, offering Save and Undo while it differs, and won't save a broken pattern", async () => {
    const { user } = await openFriday("/settings/calendars")
    await waitFor(() => expect(names()).toEqual(["Exam", "Travel", "Meeting", "Social", "Exercise", "Work", "Class"]))
    expect(screen.queryByRole("button", { name: "Save categories" })).toBeNull()
    const travel = screen.getAllByRole("textbox", { name: "Category name" })[1]
    await user.clear(travel)
    await user.type(travel, "Trips")
    expect(screen.getByRole("button", { name: "Save categories" })).toBeTruthy()
    // a category being edited isn't merged until it's saved
    expect(screen.queryByRole("button", { name: "Merge Trips into" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Undo changes" }))
    expect(names()[1]).toBe("Travel")
    const pattern = screen.getByRole("textbox", { name: "Exam: always when its title has" })
    await user.type(pattern, "(")
    expect((screen.getByRole("button", { name: "Save categories" }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getByRole("button", { name: "Undo changes" }))
  })

  it("adds, moves and deletes categories, adds a filter with what it never hides, and saves them together", async () => {
    const { user } = await openFriday("/settings/calendars")
    await waitFor(() => expect(names()).toHaveLength(7))
    await user.click(screen.getByRole("button", { name: "Add a category" }))
    expect(names().at(-1)).toBe("New category")
    const added = screen.getAllByRole("textbox", { name: "Category name" }).at(-1)!
    await user.clear(added)
    await user.type(added, "Volunteering")
    await user.type(screen.getByRole("textbox", { name: "Volunteering: always when its title has" }), "volunteer")
    await user.click(screen.getAllByRole("button", { name: "Earlier" }).at(-1)!)
    expect(names().slice(-2)).toEqual(["Volunteering", "Class"])
    expect((screen.getAllByRole("button", { name: "Earlier" })[0] as HTMLButtonElement).disabled).toBe(true)
    await user.click(screen.getAllByRole("button", { name: "Later" })[0])
    expect(names().slice(0, 2)).toEqual(["Travel", "Exam"])
    await user.click(screen.getByRole("button", { name: "Delete Exercise" }))
    expect(names()).not.toContain("Exercise")
    await user.click(screen.getByRole("button", { name: "Add a filter" }))
    expect((screen.getByRole("textbox", { name: "Filter label" }) as HTMLInputElement).value).toBe("Office hours")
    expect((screen.getByRole("textbox", { name: "Filter pattern" }) as HTMLInputElement).value).toBe("office hours|drop.?in")
    await user.click(screen.getByRole("checkbox", { name: "Meeting" }))
    await user.click(screen.getByRole("button", { name: "Save categories" }))
    const saved = (await waitForSent("settings_set")).body as { key: string; value: { categories: { name: string; pattern: string }[]; filter: unknown } }
    expect(saved.key).toBe("categories")
    expect(saved.value.categories.map((c) => c.name)).toEqual(["Travel", "Exam", "Meeting", "Social", "Work", "Volunteering", "Class"])
    expect(saved.value.categories.find((c) => c.name === "Volunteering")).toMatchObject({ pattern: "volunteer", color: "graphite" })
    expect(saved.value.filter).toEqual({ label: "Office hours", pattern: "office hours|drop.?in", except_: ["meeting"] })
    await waitFor(async () => expect((await settings()).categories.filter?.label).toBe("Office hours"))
  })

  it("names the filter in what counts as busy, and takes the filter off", async () => {
    const { user } = await openFriday("/settings/calendars")
    expect(await screen.findByRole("switch", { name: "Office hours" })).toBeTruthy()
    expect(screen.getByText(/^(Counted as busy|Left out) · What the categories’ filter hides$/)).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Remove" }))
    await user.click(screen.getByRole("button", { name: "Save categories" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "categories", value: { filter: null } })
  })

  it("merges one category into another", async () => {
    const { user } = await openFriday("/settings/calendars")
    await user.click(await screen.findByRole("button", { name: "Merge Social into" }))
    await user.click(screen.getByRole("option", { name: "Travel" }))
    expect((await waitForSent("category_merge")).body).toEqual({ name: "Social", into: "Travel" })
    await waitFor(async () => expect((await settings()).categories.categories.map((c: { name: string }) => c.name)).not.toContain("Social"))
  })
})
