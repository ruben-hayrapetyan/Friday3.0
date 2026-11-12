// Settings' sections other than the integrations and the calendars: the page itself (its sections, the one it opens
// at, Setup's answers one at a time, Back to plan), Appearance, Tags/Kinds, Schedule, Repeating, Shortcuts
// and Advanced, each driven as you would and checked by what it sent and what Friday then holds. Alex's sample; the
// server's live updates are stood in for by asking again (`client.invalidateQueries()`), as their stream would.

import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { friday, openFriday, sent, waitForSent } from "@/test/friday"
import { answer, answered, done } from "./screen.test.helpers"

type Settings = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
const settings = () => friday.q<Settings>("settings")
const look = () => JSON.parse(window.localStorage.getItem("friday-look-v8") ?? "{}")
const css = (name: string) => document.documentElement.style.getPropertyValue(name)

const undo: (() => void)[] = []
afterEach(() => {
  while (undo.length) undo.pop()!()
})

/** The setting's row (its name, note and controls), by its name. */
const field = (name: string) => screen.getByText(name, { selector: "span" }).closest(".fr-stack") as HTMLElement


describe("the settings page", () => {
  it("opens at Integrations the first time, then at the section you were last in", async () => {
    const { user, unmount } = await openFriday("/settings")
    expect(await screen.findByText("Bring in your calendars, to-dos, deadlines and mail. Open a box to connect it.")).toBeTruthy()
    expect(window.location.hash).toBe("#/settings/integrations")
    await user.click(screen.getByRole("link", { name: "Schedule" }))
    expect(await screen.findByText("The shape of a normal day. Friday plans inside these limits.")).toBeTruthy()
    expect(window.localStorage.getItem("friday.settings.section")).toBe("schedule")
    unmount()
    await openFriday("/settings")
    await waitFor(() => expect(window.location.hash).toBe("#/settings/schedule"))
  })

  it("lists every section, and goes back to the plan", async () => {
    const { user } = await openFriday("/settings/shortcuts")
    const nav = screen.getByText("Appearance").closest("nav")!
    const sections = within(nav).getAllByRole("link").map((a) => a.textContent)
    expect(sections).toEqual(["Appearance", "Calendars", "Tags/Kinds", "Schedule", "Repeating", "Integrations", "Phone", "Tokens", "Shortcuts", "Updates", "Advanced"])
    expect(screen.getByText("Changes apply right away")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Back to plan" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("an unknown section opens the last one instead", async () => {
    await openFriday("/settings/nowhere")
    await waitFor(() => expect(window.location.hash).toBe("#/settings/integrations"))
  })

  it("changes one of Setup's answers on its own, or all of them in order", async () => {
    const { user, unmount } = await openFriday("/settings/shortcuts")
    const change = screen.getByRole("button", { name: "Change a Setup answer" })
    expect(change.getAttribute("aria-expanded")).toBe("false")
    await user.click(change)
    const menu = screen.getByRole("menu")
    expect(within(menu).getAllByRole("menuitem").map((m) => m.textContent)).toContain("When you get up")
    await user.click(within(menu).getByRole("menuitem", { name: "When you get up" }))
    expect(screen.queryByRole("menu")).toBeNull()
    expect(await screen.findByRole("dialog")).toBeTruthy()
    unmount()
    const again = await openFriday("/settings/shortcuts")
    await again.user.click(screen.getByRole("button", { name: "Change a Setup answer" }))
    await again.user.click(screen.getByRole("menuitem", { name: "All of Setup’s questions, in order" }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
  })

  it("says which settings friday.toml sets, read-only here", async () => {
    const status = await friday.q<Record<string, unknown>>("status")
    undo.push(answer("status", () => ({ json: { ...status, config_keys: ["gcal", "llm"] } })))
    await openFriday("/settings/shortcuts")
    expect(await screen.findByText("Set in friday.toml, so read-only here: gcal, llm.")).toBeTruthy()
  })
})

describe("Appearance", () => {
  it("switches the theme, kept on this device and painted at once", async () => {
    const { user } = await openFriday("/settings/appearance")
    const theme = screen.getByRole("group", { name: "Theme" })
    expect(within(theme).getByRole("button", { name: "Match system" }).getAttribute("aria-pressed")).toBe("true")
    await user.click(within(theme).getByRole("button", { name: "Light" }))
    expect(look().theme).toBe("Light")
    expect(css("--color-bg")).toBe("#eceee9")
    expect(document.documentElement.style.colorScheme).toBe("light")
    expect(screen.getByText("Switch to dark to see it.")).toBeTruthy()
    await user.click(within(theme).getByRole("button", { name: "Dark" }))
    expect(css("--color-bg")).toBe("#0f1113")
    expect(screen.queryByText("Switch to dark to see it.")).toBeNull()
  })

  it("changes the ink by a swatch or the hue slider", async () => {
    const { user } = await openFriday("/settings/appearance")
    const before = css("--color-accent")
    await user.click(screen.getByRole("button", { name: "Hue 90" }))
    expect(look().accentHue).toBe(90)
    expect(css("--color-accent")).not.toBe(before)
    expect(screen.getByText(/, hue 90°$/)).toBeTruthy()
    fireEvent.change(screen.getByRole("slider", { name: "Accent hue" }), { target: { value: "200" } })
    expect(look().accentHue).toBe(200)
    expect(screen.getByText(/, hue 200°$/)).toBeTruthy()
  })

  it("chooses the calendar's hours, deadlines, blocks, glow, panels and Now bar", async () => {
    const { user } = await openFriday("/settings/appearance")
    const pick = async (group: string, choice: string) => {
      const g = screen.getByRole("group", { name: group })
      await user.click(within(g).getByRole("button", { name: choice }))
      expect(within(g).getByRole("button", { name: choice }).getAttribute("aria-pressed")).toBe("true")
    }
    await user.click(within(screen.getByRole("group", { name: "Theme" })).getByRole("button", { name: "Dark" }))
    await pick("Hours shown", "All 24 hours")
    await pick("Deadlines", "To-do lane")
    await pick("Calendar blocks", "Solid")
    await pick("Glow", "Today + more")
    expect(css("--g-now")).toBe("1")
    await pick("Glow", "Today")
    expect([css("--g-today"), css("--g-now")]).toEqual(["1", "0"])
    for (const chrome of ["Shadow", "Tonal", "Flat", "Outline"]) {
      await pick("Floating panels", chrome)
      expect(look().chrome).toBe(chrome)
    }
    expect(css("--fr-float-sh")).toContain("0 0 0 1px")
    await pick("Now bar", "Minimal")
    expect(look()).toMatchObject({ hours: "All day", deadlines: "Lanes", blocks: "Solid", glow: "Today", dockStyle: "Minimal" })
  })

  it("chooses the heading face and its weight", async () => {
    const { user } = await openFriday("/settings/appearance")
    const face = screen.getByRole("group", { name: "Heading face" })
    const weight = screen.getByRole("group", { name: "Heading weight" })
    await user.click(within(face).getByRole("button", { name: "Archivo" }))
    expect(css("--fr-head")).toContain("Archivo")
    expect(css("--fr-head-w")).toBe("700")
    await user.click(within(weight).getByRole("button", { name: "Black" }))
    expect(css("--fr-head-w")).toBe("900")
    await user.click(within(face).getByRole("button", { name: "Inter" }))
    expect(css("--fr-head-w")).toBe("800")
    expect(css("--fr-head-ls")).toBe("-0.03em")
    await user.click(within(face).getByRole("button", { name: "Serif" }))
    expect(css("--fr-head-w")).toBe("700")
  })

  it("resets everything to the default look", async () => {
    const { user } = await openFriday("/settings/appearance")
    await user.click(screen.getByRole("button", { name: "Hue 0" }))
    await user.click(within(screen.getByRole("group", { name: "Calendar blocks" })).getByRole("button", { name: "Solid" }))
    expect(look()).toMatchObject({ accentHue: 0, blocks: "Solid" })
    await user.click(screen.getByRole("button", { name: "Reset to default" }))
    expect(look()).toMatchObject({ theme: "Match system", accentHue: 255, blocks: "Soft", chrome: "Outline" })
    expect(within(screen.getByRole("group", { name: "Calendar blocks" })).getByRole("button", { name: "Soft" }).getAttribute("aria-pressed")).toBe("true")
  })
})

describe("Tags/Kinds", () => {
  const tagRow = (name: string) => (screen.getAllByRole("textbox", { name: "Tag name" }) as HTMLInputElement[]).find((t) => t.value === name)!.closest(".fr-row") as HTMLElement

  it("lists the tags with their hours this week, and renames one", async () => {
    const { user, client } = await openFriday("/settings/tags")
    const names = (await screen.findAllByRole("textbox", { name: "Tag name" })) as HTMLInputElement[]
    expect(names.map((n) => n.value)).toEqual(["CHEM 2090", "ENGL 1170", "MATH 1910", "PHYS 1112", "Rocketry"])
    expect(within(tagRow("CHEM 2090")).getByText(/^[\d.]+ h this week$/)).toBeTruthy()
    const rocketry = names[4]
    await user.clear(rocketry)
    await user.type(rocketry, "Rocketry team{Enter}")
    expect((await waitForSent("area_edit")).body).toEqual({ id: 1, name: "Rocketry team" })
    await answered(client)
    await waitFor(async () => expect((await friday.q<{ name: string }[]>("areas")).map((a) => a.name)).toContain("Rocketry team"))
  })

  it("paints a tag, archives one, and gives one a buffer of its own", async () => {
    const { user, client } = await openFriday("/settings/tags")
    const chem = await waitFor(() => tagRow("CHEM 2090"))
    await user.click(within(chem).getByRole("button", { name: "Verdigris" }))
    expect((await waitForSent("area_edit")).body).toEqual({ id: 2, color: "green" })
    await user.click(within(chem).getByRole("button", { name: "Grey" }))
    expect((await waitForSent("area_edit")).body).toEqual({ id: 2, color: "n" })
    await user.click(within(chem).getByRole("button", { name: "15 min" }))
    const rules = (await waitForSent("settings_set")).body as { key: string; value: { type: string; params: Record<string, unknown> }[] }
    expect(rules.key).toBe("rules")
    expect(rules.value.find((r) => r.type === "buffer")!.params).toEqual({ minutes: "0m", by_area: { "CHEM 2090": "15m" }, by_preset: {} })
    await answered(client)
    await waitFor(() => expect(within(tagRow("CHEM 2090")).getByRole("button", { name: "15 min" }).getAttribute("aria-pressed")).toBe("true"))
    await user.click(within(tagRow("CHEM 2090")).getByRole("button", { name: "Default" }))
    const back = (await waitForSent("settings_set")).body as typeof rules
    expect(back.value.find((r) => r.type === "buffer")!.params.by_area).toEqual({})
    sent.length = 0
    await user.click(within(tagRow("ENGL 1170")).getByRole("button", { name: "Archive" }))
    expect((await waitForSent("area_edit")).body).toEqual({ id: 3, archived: true })
    await waitFor(async () => expect((await friday.q<{ id: number; archived: boolean }[]>("areas")).find((a) => a.id === 3)?.archived).toBe(true))
  })

  it("adds a tag in the next paint, and deals every tag its paint again", async () => {
    const { user } = await openFriday("/settings/tags")
    await screen.findAllByRole("textbox", { name: "Tag name" })
    const count = screen.getAllByRole("textbox", { name: "Tag name" }).length
    await user.click(screen.getByRole("button", { name: "Add tag" }))
    expect((await waitForSent("area_add")).body).toEqual({ name: `Tag ${count + 1}`, color: ["blue", "orange", "green", "violet", "yellow", "pink", "sapgreen", "purple", "graphite"][count % 9] })
    sent.length = 0
    await user.click(screen.getByRole("button", { name: "Auto-assign colors" }))
    await waitFor(() => expect(sent.filter((s) => s.name === "area_edit").length).toBeGreaterThanOrEqual(count))
    expect(sent.find((s) => s.name === "area_edit")!.body).toEqual({ id: 2, color: "blue" })
  })

  it("puts kinds in priority order and gives a kind a buffer", async () => {
    const { user } = await openFriday("/settings/tags")
    expect(await screen.findByText("Kinds, in priority order")).toBeTruthy()
    const ups = await screen.findAllByRole("button", { name: "Move up" })
    expect((ups[0] as HTMLButtonElement).disabled).toBe(true)
    await user.click(ups[1])
    const order = (await waitForSent("settings_set")).body as { key: string; value: string[] }
    expect(order.key).toBe("kind_order")
    expect(order.value.slice(0, 2)).toEqual(["Work task", "Task"])
    const downs = screen.getAllByRole("button", { name: "Move down" })
    expect((downs.at(-1) as HTMLButtonElement).disabled).toBe(true)
    const reading = screen.getByText("Reading", { selector: "span" }).closest(".fr-row") as HTMLElement
    await user.click(within(reading).getByRole("button", { name: "30 min" }))
    const rules = (await waitForSent("settings_set")).body as { value: { type: string; params: { by_preset: Record<string, string> } }[] }
    expect(rules.value.find((r) => r.type === "buffer")!.params.by_preset).toEqual({ Reading: "30m" })
  })

  it("switches school off and short term first on", async () => {
    const { user } = await openFriday("/settings/tags")
    const school = await screen.findByRole("switch", { name: "I'm in school" })
    expect(school.getAttribute("aria-checked")).toBe("true")
    await user.click(school)
    expect((await waitForSent("settings_set")).body).toEqual({ key: "school", value: false })
    await user.click(screen.getByRole("switch", { name: "Short term before long term" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "short_term_first", value: true })
    await waitFor(async () => expect((await settings()).short_term_first).toBe(true))
    await friday.c("settings_set", { key: "school", value: true })
  })

  it("adds a kind that works like another, and deletes one, moving what it holds", async () => {
    const { user, client } = await openFriday("/settings/tags")
    const name = await screen.findByPlaceholderText("New kind, e.g. Lab report")
    const add = screen.getByRole("button", { name: "Add kind" }) as HTMLButtonElement
    expect(add.disabled).toBe(true)
    await user.type(name, "Lab report")
    await user.click(screen.getByRole("button", { name: "Starts as a copy of" }))
    await user.click(await screen.findByRole("option", { name: "Reading" }))
    await user.click(add)
    expect((await waitForSent("kind_add")).body).toEqual({ name: "Lab report", like: "Reading" })
    await waitFor(async () => expect(Object.keys((await settings()).presets)).toContain("Lab report"))
    await client.invalidateQueries()
    // the kinds calendars and mail are read into can't be deleted
    expect(screen.queryByRole("button", { name: "Delete Assignment" })).toBeNull()
    await user.click(await screen.findByRole("button", { name: "Delete Lab report" }))
    expect(screen.getByText("Delete Lab report. Anything of this kind becomes")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Move its items to" }))
    await user.click(screen.getByRole("option", { name: "Assignment" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect((await waitForSent("kind_remove")).body).toEqual({ name: "Lab report", move_to: "Assignment" })
    await waitFor(async () => expect(Object.keys((await settings()).presets)).not.toContain("Lab report"))
  })

  it("closes the delete question on Cancel", async () => {
    const { user } = await openFriday("/settings/tags")
    await user.click(await screen.findByRole("button", { name: "Delete Chore" }))
    expect(screen.getByText("Delete Chore. Anything of this kind becomes")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByText("Delete Chore. Anything of this kind becomes")).toBeNull()
  })
})

describe("Schedule", () => {
  it("sets when the day starts and bedtime for every day", async () => {
    const { user } = await openFriday("/settings/schedule")
    const wake = within(await waitFor(() => field("Day starts"))).getByRole("combobox")
    expect((wake as HTMLSelectElement).value).toBe("07:30")
    await user.selectOptions(wake, "08:00")
    const sleep = (await waitForSent("settings_set")).body as { key: string; value: Record<string, { wake: string }> }
    expect(sleep.key).toBe("sleep")
    expect(Object.values(sleep.value).map((n) => n.wake)).toEqual(Array(7).fill("08:00"))
    await user.selectOptions(within(field("Bedtime")).getByRole("combobox"), "00:00")
    const bed = (await waitForSent("settings_set")).body as { value: Record<string, { bedtime: string }> }
    expect(bed.value.sun.bedtime).toBe("00:00")
  })

  it("sets the margin past bedtime, the buffer, the daily limit and the default pace", async () => {
    const { user } = await openFriday("/settings/schedule")
    await user.click(within(await waitFor(() => field("Past bedtime, if a deadline needs it"))).getByRole("button", { name: "1h 30m" }))
    expect(((await waitForSent("settings_set")).body as { value: Record<string, { margin_min: number }> }).value.wed.margin_min).toBe(90)
    await user.click(within(field("Buffer between blocks")).getByRole("button", { name: "15 min" }))
    const rules = (await waitForSent("settings_set")).body as { key: string; value: { type: string; params: { minutes: string } }[] }
    expect(rules.value.find((r) => r.type === "buffer")!.params.minutes).toBe("15m")
    fireEvent.change(screen.getByRole("slider", { name: "Daily limit" }), { target: { value: "8.5" } })
    expect((await waitForSent("settings_set")).body).toEqual({ key: "daily_cap", value: { mon: 8.5, tue: 8.5, wed: 8.5, thu: 8.5, fri: 8.5, sat: 8.5, sun: 8.5 } })
    await user.click(await within(field("Default pace")).findByRole("button", { name: "Easy" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "pace", value: { default: "Easy" } })
    await user.click(within(field("Buffer between blocks")).getByRole("button", { name: /→$/ }))
    await waitFor(() => expect(window.location.hash).toBe("#/settings/tags"))
  })

  it("sets the week's first day, missed blocks, sittings and the morning brief", async () => {
    const { user, client } = await openFriday("/settings/schedule")
    await user.click(within(await waitFor(() => field("Week starts on"))).getByRole("button", { name: "Sunday" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "time", value: { week_start: "sun" } })
    const missed = field("When a block passes and you didn’t time it or mark it")
    expect(within(missed).getByText(/Friday counts it as done, and the Inbox asks how much you actually did/)).toBeTruthy()
    await user.click(within(missed).getByRole("button", { name: "Plan it again" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "planner", value: { assume_unreviewed: "not_done" } })
    await answered(client)
    expect(await screen.findByText(/Friday plans the work again and the Inbox doesn’t ask/)).toBeTruthy()
    await user.click(within(field("Sittings")).getByRole("button", { name: "In one go" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "sittings", value: { one_go: true, factor: 3 } })
    await user.click(within(field("Morning brief")).getByRole("button", { name: "Don't" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "notify", value: { morning_brief: false } })
  })

  it("switches on tracking sleep and meals, with the way to Insights", async () => {
    const { user, client } = await openFriday("/settings/schedule")
    const sleep = await screen.findByRole("switch", { name: "Track my sleep" })
    expect(within(field("Track my sleep")).getByText("Off")).toBeTruthy()
    await user.click(sleep)
    expect((await waitForSent("settings_set")).body).toEqual({ key: "sleep_tracking", value: { on: true, min_nights: 4, morning_hours: 4 } })
    await user.click(screen.getByRole("switch", { name: "Track my meals" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "meal_tracking", value: { on: true, min_days: 4 } })
    await answered(client)
    await user.click(await screen.findByRole("button", { name: "Log or fix a meal in Insights → Meals" }))
    await waitFor(() => expect(window.location.hash).toBe("#/insights?tab=meals"))
  })

  it("sets bedtimes, wake times and limits day by day", async () => {
    const thursday = (await settings()).sleep.thu.bedtime
    const { user } = await openFriday("/settings/schedule")
    await user.click(await screen.findByRole("button", { name: "Set each day" }))
    const fri = screen.getByRole("textbox", { name: "fri bedtime" }) as HTMLInputElement
    await user.clear(fri)
    await user.type(fri, "1am")
    await user.tab()
    const night = (await waitForSent("settings_set")).body as { key: string; value: Record<string, { bedtime: string }> }
    expect(night.key).toBe("sleep")
    expect(night.value.fri.bedtime).toBe("01:00")
    expect(night.value.thu.bedtime).toBe(thursday) // the other days as they were
    const limits = screen.getAllByRole("spinbutton")
    fireEvent.change(limits[limits.length - 1], { target: { value: "6" } })
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "daily_cap", value: { sun: 6 } })
    await user.click(screen.getByRole("button", { name: "Hide" }))
    expect(screen.queryByRole("textbox", { name: "fri bedtime" })).toBeNull()
  })
})

describe("Repeating", () => {
  const line = (title: string) => screen.getByRole("button", { name: title }).closest(".fr-row") as HTMLElement

  it("groups what comes back: your habits, and what your calendars bring", async () => {
    await openFriday("/settings/repeating")
    expect(await screen.findByText("Habits and routines")).toBeTruthy()
    expect(screen.getByText("From your calendars and feeds")).toBeTruthy()
    expect(screen.queryByText("Classes and commitments")).toBeNull()
    const gym = line("gym")
    expect(within(gym).getByText("Added by you")).toBeTruthy()
    const lab = line("CHEM 2090 Lab")
    expect(within(lab).getByText("From Cornell Classes; times follow the calendar")).toBeTruthy()
    expect(within(lab).queryByRole("button", { name: "Delete CHEM 2090 Lab" })).toBeNull()
  })

  it("keeps a habit's times apart and changes its tag", async () => {
    const { user } = await openFriday("/settings/repeating")
    await screen.findByText("Habits and routines")
    await user.click(within(line("Laundry")).getByRole("button", { name: "Days between Laundry" }))
    await user.click(screen.getByRole("option", { name: "At least 7 days apart" }))
    expect((await waitForSent("series_spacing")).body).toEqual({ id: 13, days: 7 })
    expect(await screen.findByText("Laundry: at least 7 days apart")).toBeTruthy()
    await user.click(within(line("gym")).getByRole("button", { name: "Tag for gym" }))
    await user.click(screen.getByRole("option", { name: "MATH 1910" }))
    expect((await waitForSent("series_edit")).body).toEqual({ id: 12, area: "MATH 1910" })
  })

  it("stops a repeat, starts it again, and deletes one", async () => {
    const { user, client } = await openFriday("/settings/repeating")
    await screen.findByText("Habits and routines")
    await user.click(within(line("Breakfast")).getByRole("switch", { name: "Stop Breakfast" }))
    expect((await waitForSent("series_stop")).body).toEqual({ id: 11 })
    await answered(client)
    await user.click(await screen.findByRole("switch", { name: "Start Breakfast" }))
    expect((await waitForSent("series_resume")).body).toEqual({ id: 11 })
    await user.click(within(line("Dinner")).getByRole("button", { name: "Delete Dinner" }))
    expect((await waitForSent("series_delete")).body).toEqual({ id: 10 })
    await waitFor(async () => expect((await friday.q<{ id: number }[]>("series_list")).some((s) => s.id === 10)).toBe(false))
  })

  it("opens a habit in the to-do and a class over the calendar", async () => {
    const { user, unmount } = await openFriday("/settings/repeating")
    await user.click(await screen.findByRole("button", { name: "gym" }))
    await waitFor(() => expect(window.location.hash).toMatch(/^#\/todo\?item=\d+&found=1$/))
    unmount()
    const again = await openFriday("/settings/repeating")
    await again.user.click(await screen.findByRole("button", { name: "CHEM 2090 Lab" }))
    await waitFor(() => expect(window.location.hash).toBe("#/"))
  })

  it("offers the repeating events found in your calendars, each to bring in as one repeat", async () => {
    const found = [
      { batch: "b1", title: "Bio study group", pattern: "Every Tuesday, 6pm", calendar: "Personal", count: 8, kind: "Event", tag: "BIO 1010" },
      { batch: "b2", title: "Run club", pattern: "Every Saturday, 9am", calendar: "Clubs", count: 5, kind: "Event", tag: null },
    ]
    undo.push(answer("calendar_repeats", () => ({ json: found })))
    undo.push(answer("repeats_import", () => done({ message: "Imported 1 repeat" })))
    const { user } = await openFriday("/settings/repeating")
    expect(await screen.findByText("2 repeating events in your Google calendars")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Import all 2" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Include Run club" }))
    expect(screen.getByRole("button", { name: "Import 1" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Tag for Bio study group" }))
    await user.click(screen.getByRole("option", { name: "No tag" }))
    await user.click(screen.getByRole("button", { name: "Kind for Bio study group" }))
    await user.click(await screen.findByRole("option", { name: "Class" }))
    await user.click(screen.getByRole("button", { name: "Import 1" }))
    expect((await waitForSent("repeats_import")).body).toEqual({ repeats: [{ batch: "b1", area: null, kind: "Class" }] })
    await user.click(screen.getByRole("button", { name: "Not now" }))
    expect(screen.queryByText("2 repeating events in your Google calendars")).toBeNull()
    expect(window.localStorage.getItem("friday.repeats.notNow")).toBe("b1,b2")
  })
})

describe("About you, now notes on the Rules page", () => {
  it("its old address opens Rules, where a note is kept from the box and forgotten from its row", async () => {
    const { user, client } = await openFriday("/settings/about")
    await waitFor(() => expect(window.location.hash).toContain("/rules"))
    expect(await screen.findByText(/None yet\. Type one in the box above and press Keep as a note/)).toBeTruthy()
    const box = screen.getByRole("textbox", { name: "New rule" })
    const keep = screen.getByRole("button", { name: "Keep as a note" }) as HTMLButtonElement
    expect(keep.disabled).toBe(true)
    await user.type(box, "  Lab reports take me about 2 hours  ")
    await user.click(keep)
    expect((await waitForSent("settings_set")).body).toEqual({ key: "notes", value: ["Lab reports take me about 2 hours"] })
    expect((box as HTMLInputElement).value).toBe("")
    await answered(client)
    expect(await screen.findByText("Lab reports take me about 2 hours")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Forget: Lab reports take me about 2 hours" }))
    expect((await waitForSent("settings_set")).body).toEqual({ key: "notes", value: [] })
  })
})

describe("Shortcuts", () => {
  it("lists what the keyboard does", async () => {
    await openFriday("/settings/shortcuts")
    expect(screen.getByText("Everything on the plan works from the keyboard.")).toBeTruthy()
    const undoRow = screen.getByText("Undo").closest(".fr-row") as HTMLElement
    expect(Array.from(undoRow.querySelectorAll("kbd")).map((k) => k.textContent)).toEqual(["⌘", "Z"])
    expect(screen.getByText("Accept, edit or reject in the Inbox")).toBeTruthy()
  })
})

describe("Advanced", () => {
  it("saves the dials in use as a pace, changes a dial, and deletes a pace", async () => {
    const paces = await friday.q<{ default: string; now_label: string; now_dials: Record<string, number>; paces: Record<string, Record<string, number>> }>("paces")
    const { user, client } = await openFriday("/settings/advanced")
    expect(await screen.findByText("Saved paces")).toBeTruthy()
    expect(await screen.findByText("· default")).toBeTruthy()
    const save = screen.getByRole("button", { name: "Save the dials in use" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    await user.type(screen.getByPlaceholderText("New pace, e.g. Exam week"), "Exam week")
    await user.click(save)
    const saved = (await waitForSent("pace_save")).body as Record<string, unknown>
    expect(Object.keys(saved).sort()).toEqual(["capacity", "growth", "name", "rest", "spread"])
    expect(saved.name).toBe("Exam week")
    // the default pace and the one in use can't be deleted
    expect(screen.queryByRole("button", { name: `Delete ${paces.default}` })).toBeNull()
    expect(screen.queryByRole("button", { name: `Delete ${paces.now_label}` })).toBeNull()
    // one that's neither the default nor, by its dials, the pace in use now
    const now = JSON.stringify(paces.now_dials)
    const other = Object.keys(paces.paces).find((p) => p !== paces.default && p !== paces.now_label && JSON.stringify(paces.paces[p]) !== now)!
    const row = screen.getByText(other).parentElement as HTMLElement
    const capacity = row.querySelector('input[type="range"]') as HTMLInputElement
    fireEvent.change(capacity, { target: { value: "1.4" } })
    fireEvent.mouseUp(capacity)
    expect((await waitForSent("pace_save")).body).toEqual({ name: other, capacity: 1.4 })
    await answered(client) // saved before it's deleted
    await user.click(screen.getByRole("button", { name: `Delete ${other}` }))
    expect((await waitForSent("pace_delete")).body).toEqual({ name: other })
    await waitFor(async () => expect(Object.keys((await friday.q<typeof paces>("paces")).paces)).not.toContain(other))
  })

  it("says the plugins loaded, and lists what Friday learns and every setting", async () => {
    await openFriday("/settings/advanced")
    expect(await screen.findByText("Every plugin in ~/.config/friday/rules/ loaded.")).toBeTruthy()
    expect(screen.getByText("Learning")).toBeTruthy()
    expect(screen.getByText("Every setting")).toBeTruthy()
  })

  it("says when plugins are off, and a plugin's problem", async () => {
    const real = await settings()
    undo.push(answer("settings", () => ({ json: { ...real, server: { ...real.server, allow_plugins: false } } })))
    const { unmount } = await openFriday("/settings/advanced")
    expect(await screen.findByText("Plugins are off (server.allow_plugins).")).toBeTruthy()
    unmount()
    undo.pop()!()
    const status = await friday.q<Record<string, unknown>>("status")
    undo.push(answer("status", () => ({ json: { ...status, problems: ["plugin lab.py: SyntaxError on line 3"] } })))
    await openFriday("/settings/advanced")
    expect(await screen.findByText("plugin lab.py: SyntaxError on line 3")).toBeTruthy()
  })
})
