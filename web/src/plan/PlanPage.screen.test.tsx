// The Plan page over Alex's three lived-in weeks: the header (the range, the views, the arrows and keys, Show, the
// Plan menu, what needs you), and the grid (blocks, events, dues, whole days, the timer, typing a time, picking
// several). The real clock runs, so a test looks a week ahead for blocks still to come, and asserts what's there and
// what was sent, never a date.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { addDays, pageStart } from "@/lib/time"
import { rangeTitle } from "./PlanPage"
import { friday, openFriday, waitForSent } from "@/test/friday"

type Plan = Schemas["PlanOut"]
type Calendar = Schemas["CalendarOut"]

const view = () => screen.getByRole("group", { name: "View" })
const pressed = () => within(view()).getAllByRole("button").find((b) => b.getAttribute("aria-pressed") === "true")?.textContent
const backToToday = () => screen.getByTitle("Back to today")
const today = async () => (await friday.q<Calendar>("calendar", { start: "2026-01-01", days: "1" })).today

/** The plan a week on, once Friday has finished replanning: every block there is still to come. */
async function nextWeek() {
  await statusWhen((s) => s.plan_generation === s.generation)
  const first = addDays(await today(), 4)
  const plan = await friday.q<Plan>("plan", { start: `${first}T00:00`, end: `${addDays(first, 7)}T00:00` })
  return { first, plan, tasks: plan.blocks.filter((b) => b.key.startsWith("T") && !b.state && b.preset === "Assignment") }
}

/** The box of a block or event on the calendar, by its key. */
const box = (key: string) => document.querySelector<HTMLElement>(`[data-block-key="${CSS.escape(key)}"]`)
async function findBox(key: string) {
  await waitFor(() => expect(box(key)).not.toBeNull(), { timeout: 10_000 })
  return box(key) as HTMLElement
}

/** The grid, once the week's plan has come. */
async function gridReady() {
  await waitFor(() => expect(document.querySelector('[data-tour="calendar"] [data-block-key]')).not.toBeNull(), { timeout: 15_000 })
}

/** Friday's status once `ready` holds, as the server says it (the page asks for it when it opens). */
async function statusWhen(ready: (s: Schemas["StatusOut"]) => boolean) {
  let status = await friday.q<Schemas["StatusOut"]>("status")
  const until = Date.now() + 60_000
  while (!ready(status) && Date.now() < until) {
    await new Promise((r) => setTimeout(r, 500))
    status = await friday.q<Schemas["StatusOut"]>("status")
  }
  return status
}

async function openOnNextWeek() {
  const opened = await openFriday("/")
  await opened.user.click(screen.getByRole("button", { name: "Next" }))
  await gridReady()
  return opened
}

describe("the header", () => {
  it("opens on the week around today and steps a week at a time, back to today", async () => {
    const { user } = await openFriday("/")
    expect(pressed()).toBe("Week")
    expect(backToToday().textContent).toBe("This week")
    await user.click(screen.getByRole("button", { name: "Next" }))
    expect(backToToday().textContent).toBe("Today")
    await user.click(screen.getByRole("button", { name: "Previous" }))
    await user.click(screen.getByRole("button", { name: "Previous" }))
    expect(backToToday().textContent).toBe("Today")
    await user.click(backToToday())
    expect(backToToday().textContent).toBe("This week")
  })

  it("shows a day, three days, a week or a month, from the buttons", async () => {
    const { user } = await openFriday("/")
    await user.click(within(view()).getByRole("button", { name: "Day" }))
    expect(pressed()).toBe("Day")
    expect(backToToday().textContent).toBe("Today")
    // the day view's side panel: the day in numbers, its blocks in order, and what's due soon
    expect(await screen.findByText("In order")).toBeTruthy()
    expect(screen.getByText("Due in the next 3 days")).toBeTruthy()
    for (const stat of ["focused", "blocks", "room left"]) expect(screen.getByText(stat)).toBeTruthy()
    await user.click(within(view()).getByRole("button", { name: "3 days" }))
    expect(backToToday().textContent).toBe("Around today")
    await user.click(within(view()).getByRole("button", { name: "Month" }))
    expect(backToToday().textContent).toBe("This month")
    for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) expect(screen.getAllByText(day).length).toBeGreaterThan(0)
    await user.click(within(view()).getByRole("button", { name: "Week" }))
    expect(backToToday().textContent).toBe("This week")
  })

  it("keeps the day you're looking at when a View button changes the view", async () => {
    // the audit, 12 Nov: "View buttons jump to today"
    const { user } = await openFriday("/")
    const day = addDays(await today(), 14)
    await user.click(screen.getByRole("button", { name: "Next" }))
    await user.click(screen.getByRole("button", { name: "Next" }))
    const title = () => document.querySelector('[data-testid="day-arrows"]')!.parentElement!.querySelector(".fr-h")!.textContent
    const titled = (view: 1 | 3 | 7) => [rangeTitle(pageStart(day, view), view), rangeTitle(pageStart(day, view), view, true)]
    for (const [name, view] of [["Day", 1], ["3 days", 3], ["Week", 7]] as const) {
      await user.click(within(screen.getByRole("group", { name: "View" })).getByRole("button", { name }))
      expect(pressed()).toBe(name)
      expect(titled(view)).toContain(title())
    }
    await user.click(within(view()).getByRole("button", { name: "Month" }))
    expect(title()).toBe(rangeTitle(`${day.slice(0, 7)}-01`, "month"))
    await user.click(backToToday())
    expect(backToToday().textContent).toBe("This month")
  })

  it("answers the keys: d, 3, w and m for the views, [ and ] to step", async () => {
    const { user } = await openFriday("/")
    await user.keyboard("d")
    expect(pressed()).toBe("Day")
    await user.keyboard("3")
    expect(pressed()).toBe("3 days")
    await user.keyboard("m")
    expect(pressed()).toBe("Month")
    await user.keyboard("]")
    expect(backToToday().textContent).toBe("Today")
    await user.keyboard("[[")
    expect(backToToday().textContent).toBe("This month")
    await user.click(backToToday())
    await user.keyboard("w")
    expect(pressed()).toBe("Week")
    expect(backToToday().textContent).toBe("This week")
    await user.keyboard("]")
    expect(backToToday().textContent).toBe("Today")
  })

  it("comes back from this month to the week, three days or day around today, by key", async () => {
    // the audit, 12 Nov: m then w showed the week around the 1st of the month, not the week you were on
    const { user } = await openFriday("/")
    for (const [key, view, said] of [["w", "Week", "This week"], ["3", "3 days", "Around today"], ["d", "Day", "Today"]]) {
      await user.keyboard("m")
      expect(backToToday().textContent).toBe("This month")
      await user.keyboard(key)
      expect(pressed()).toBe(view)
      expect(backToToday().textContent).toBe(said)
      if (view === "Day") expect(screen.getAllByText(new RegExp(`^${Number((await today()).slice(8, 10))}$`)).length).toBeGreaterThan(0)
    }
  })

  it("opens a month's day in the day view, and its events in the card", async () => {
    const { user } = await openFriday("/")
    await user.click(within(view()).getByRole("button", { name: "Month" }))
    const date = addDays(await today(), 1)
    const cell = await waitFor(() => {
      const found = document.querySelector<HTMLElement>(`div[data-drop-day="${date}"]`)
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    // a day with more than fits says how many more
    await waitFor(() => expect(screen.getAllByText(/^\d+ more$/).length).toBeGreaterThan(0))
    // an event in the month opens in the card, not the day
    const event = await waitFor(() => {
      const found = document.querySelector<HTMLElement>(`[data-drop-day] [data-block-key^="F"]`)
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    await user.click(event)
    expect(await screen.findByText("Fixed time")).toBeTruthy()
    expect(pressed()).toBe("Month")
    await user.click(screen.getByRole("button", { name: "Close" }))
    fireEvent.click(cell)
    await waitFor(() => expect(pressed()).toBe("Day"))
    expect(await screen.findByText("In order")).toBeTruthy()
  })

  it("opens the day's deadlines from a month's day", async () => {
    const { user } = await openFriday("/")
    await user.click(within(view()).getByRole("button", { name: "Month" }))
    const dues = (await friday.q<Calendar>("calendar", { start: await today(), days: "14" })).dues
    const first = dues[0]
    const count = await screen.findAllByRole("button", { name: new RegExp(`due: .*${first.title}`) })
    await user.click(count[0])
    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: new RegExp(first.title) }))
    // the due, in the card, and the month stays
    expect(await screen.findByText(/^Due /)).toBeTruthy()
    expect(pressed()).toBe("Month")
  })

  it("lists the day's blocks in order beside the day view, each opening its card", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getByRole("button", { name: "Next" }))
    await user.keyboard("d")
    const inOrder = (await screen.findByText("In order", {}, { timeout: 10_000 })).parentElement as HTMLElement
    const rows = within(inOrder).getAllByRole("button")
    expect(rows.length).toBeGreaterThan(0)
    const planned = rows.find((r) => /Planned$/.test(r.textContent ?? "")) as HTMLElement
    await user.click(planned)
    expect(await screen.findByText("Planned · Friday decides")).toBeTruthy()
  })

  it("opens search, the to-do drawer and the Inbox's decisions from its buttons", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getByRole("button", { name: "Search (⌘K)" }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    const drawer = screen.getByRole("button", { name: "To-do list" })
    // the drawer's list of to-dos, with Alex's problem sets in it
    await user.click(drawer)
    expect(await screen.findByRole("button", { name: "Open full to-do" })).toBeTruthy()
    await user.click(drawer)
  })
})

describe("Show", () => {
  it("draws Friday's past plan, or only when you worked, saved in settings", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getByRole("button", { name: "Show" }))
    const past = screen.getByRole("switch", { name: "Show Friday's past plan" })
    expect(past.getAttribute("aria-checked")).toBe("true")
    await user.click(past)
    const sent = await waitForSent("settings_set")
    expect(sent.body).toMatchObject({ key: "calendar_look", value: { show_past_plan: false } })
    await waitFor(async () => expect((await friday.q<{ calendar_look: { show_past_plan: boolean } }>("settings")).calendar_look.show_past_plan).toBe(false), { timeout: 10_000 })
    // off it stays, opened again, until switched on
    cleanup()
    const again = await openFriday("/")
    await again.user.click(screen.getByRole("button", { name: "Show" }))
    await waitFor(() => expect(screen.getByRole("switch", { name: "Show Friday's past plan" }).getAttribute("aria-checked")).toBe("false"))
    await again.user.click(screen.getByRole("switch", { name: "Show Friday's past plan" }))
    await waitFor(async () => expect((await waitForSent("settings_set")).body).toMatchObject({ value: { show_past_plan: true } }), { timeout: 10_000 })
    await waitFor(async () => expect((await friday.q<{ calendar_look: { show_past_plan: boolean } }>("settings")).calendar_look.show_past_plan).toBe(true), { timeout: 10_000 })
  })

  it("keeps a calendar with a button off the grid until it's switched on, by the menu or ⌥⌘1", async () => {
    const settings = await friday.q<{ calendar_look: Record<string, unknown> }>("settings")
    await friday.c("settings_set", { key: "calendar_look", value: { ...settings.calendar_look, toolbar: ["Cornell Classes"] } })
    const { user } = await openOnNextWeek()
    const lectures = () => [...document.querySelectorAll('[data-block-key^="F"]')].filter((e) => e.textContent?.startsWith("MATH 1910 Lecture"))
    expect(lectures()).toHaveLength(0)
    await user.click(screen.getByRole("button", { name: "Show" }))
    await user.click(screen.getByRole("switch", { name: "Show Cornell Classes" }))
    await waitFor(() => expect(lectures().length).toBeGreaterThan(0))
    expect(screen.getByText("⌥⌘1")).toBeTruthy()
    fireEvent.keyDown(window, { key: "1", code: "Digit1", altKey: true, metaKey: true })
    await waitFor(() => expect(lectures()).toHaveLength(0))
    fireEvent.keyDown(window, { key: "2", code: "Digit2", altKey: true, metaKey: true }) // no second calendar: nothing
    fireEvent.keyDown(window, { key: "1", code: "Digit1", altKey: true, metaKey: true })
    await waitFor(() => expect(lectures().length).toBeGreaterThan(0))
    await friday.c("settings_set", { key: "calendar_look", value: { ...settings.calendar_look, toolbar: [] } })
  })
})

describe("the Plan menu", () => {
  const row = async (user: Awaited<ReturnType<typeof openFriday>>["user"], label: RegExp) => {
    await user.click(screen.getByRole("button", { name: "Plan" }))
    await user.click(screen.getByRole("button", { name: label }))
  }

  it("says the pace it's at, and opens Pace and Shove", async () => {
    const { user } = await openFriday("/")
    await user.click(screen.getByRole("button", { name: "Plan" }))
    const pace = await screen.findByRole("button", { name: /^Pace/ })
    await waitFor(() => expect(pace.textContent).toMatch("Normal"))
    await user.click(pace)
    expect(await screen.findByText(/Easy/)).toBeTruthy()
    await row(user, /^Shove/)
    expect((await screen.findAllByText(/shove/i)).length).toBeGreaterThan(0)
  })

  it("opens the morning brief, what changed and Ask", async () => {
    const { user } = await openFriday("/")
    for (const label of [/^Morning brief/, /^What changed/, /^Ask /]) {
      await row(user, label)
      expect(await screen.findByRole("dialog")).toBeTruthy()
      await user.keyboard("{Escape}")
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    }
  })

  it("starts What if, framing the week until it's left", async () => {
    const { user } = await openFriday("/")
    await gridReady()
    await row(user, /^What if/)
    await waitFor(() => expect(document.querySelector<HTMLElement>('[data-tour="calendar"]')?.style.boxShadow).toMatch(/inset/))
    const leave = await screen.findAllByRole("button", { name: /Leave|Stop|Done|Discard|Cancel/ })
    await user.click(leave[0])
    await waitFor(() => expect(document.querySelector<HTMLElement>('[data-tour="calendar"]')?.style.boxShadow ?? "").not.toMatch(/inset/))
  })

  it("plans other ways, one at a time, and stops when asked", async () => {
    const { user } = await openFriday("/")
    await row(user, /^Other ways/)
    const dialog = await screen.findByRole("dialog", { name: "Other ways" })
    expect(within(dialog).getByRole("status").textContent).toMatch(/Planning your week two more ways/)
    expect(within(dialog).getAllByTestId("way-planning").length).toBe(2)
    await user.click(within(dialog).getByRole("button", { name: "Stop" }))
    expect(within(dialog).getByRole("status").textContent).toMatch(/^Stopped/)
    expect(within(dialog).getByRole("button", { name: /Plan again/ })).toBeTruthy()
    await user.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(screen.queryByRole("dialog", { name: "Other ways" })).toBeNull()
  })
})

describe("other ways, found", () => {
  // Each way is half a minute of planning on the server; here the two come at once, made from the plan a week on (the
  // rest of the page, and picking one, are the server's own).
  it("shows each way as a card, lays one over the calendar, and picks it", async () => {
    const { tasks } = await nextWeek()
    const later = (b: Schemas["BlockOut"], by: number) => {
      const start = new Date(Date.parse(`${b.start}:00Z`) + by * 60_000).toISOString().slice(0, 16)
      const end = new Date(Date.parse(`${b.end}:00Z`) + by * 60_000).toISOString().slice(0, 16)
      return { ...b, key: `T${b.item_id}@${start}`, start, end }
    }
    const way = (seed: number) => ({
      weights: { spread: seed },
      seed,
      summary: seed === 1 ? "Problem sets earlier in the day" : "More, shorter sittings",
      blocks: tasks.slice(0, 2).map((b) => later(b, seed * 60)),
      hours: 12 + seed,
      sessions: 6 + seed,
      late: seed === 2 ? { 566: 1.5 } : {},
      rule_totals: { spread: 100 * seed },
      signature: `way-${seed}`,
    })
    const real = window.fetch
    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
      if (!url.includes("/api/q/other_way")) return real(input, init)
      const seed = Number(new URL(url, window.location.href).searchParams.get("seed"))
      return new Response(JSON.stringify({ way: way(seed), tries: 6, wanted: 2 }), { headers: { "content-type": "application/json" } })
    }) as typeof fetch
    globalThis.fetch = window.fetch
    try {
      const { user } = await openOnNextWeek()
      const open = async () => {
        await user.click(screen.getByRole("button", { name: "Plan" }))
        await user.click(screen.getByRole("button", { name: /^Other ways/ }))
        return screen.findByRole("dialog", { name: "Other ways" })
      }
      let dialog = await open()
      // stopped a minute ago (by the test before), what was found stays until planned again
      const again = within(dialog).queryByRole("button", { name: /Plan again/ })
      if (again) await user.click(again)
      expect(await within(dialog).findByText("Problem sets earlier in the day")).toBeTruthy()
      expect(await within(dialog).findByText("More, shorter sittings")).toBeTruthy()
      expect(within(dialog).getByRole("status").textContent).toMatch(/^The same work, planned differently/)
      expect(within(dialog).getByText("1 late")).toBeTruthy()
      expect(within(dialog).getByText("nothing late")).toBeTruthy()
      expect(within(dialog).getAllByLabelText("The next seven days")).toHaveLength(2)
      await user.click(within(dialog).getAllByRole("button", { name: /Preview/ })[0])
      expect(screen.queryByRole("dialog", { name: "Other ways" })).toBeNull()
      const banner = await screen.findByText("Previewing")
      expect(banner.parentElement?.textContent).toMatch("Problem sets earlier in the day")
      // the way's blocks, dashed over the calendar where they differ
      await waitFor(() => expect(screen.getAllByText(tasks[0].title).length).toBeGreaterThan(1))
      await user.click(screen.getByRole("button", { name: "Stop previewing" }))
      expect(screen.queryByText("Previewing")).toBeNull()
      dialog = await open()
      await user.click(within(dialog).getAllByRole("button", { name: /Preview/ })[1])
      await screen.findByText("Previewing")
      await user.click(screen.getByRole("button", { name: "Back to the options" }))
      dialog = await screen.findByRole("dialog", { name: "Other ways" })
      await user.click(within(dialog).getAllByRole("button", { name: /Pick this/ })[1])
      expect((await waitForSent("other_way_pick")).body).toEqual({ weights: { spread: 2 }, seed: 2, rule_totals: { spread: 200 } })
    } finally {
      window.fetch = real
      globalThis.fetch = real
    }
  })
})

describe("what needs you", () => {
  it("says what will be late, lists it, and opens it or the options", async () => {
    const due = `${addDays(await today(), 1)}T10:00`
    await friday.c("add", { title: "Senior thesis, all of it", when: "window", due, amount: "fixed", duration_min: 3000, firmness: "hard" })
    await statusWhen((s) => (s.late_items ?? []).length > 0)
    const { user } = await openFriday("/")
    const pill = await screen.findByRole("button", { name: /will be late|things will be late/ }, { timeout: 20_000 })
    await user.click(pill)
    expect(pill.getAttribute("aria-expanded")).toBe("true")
    const list = pill.parentElement as HTMLElement
    // each thing that will be late, under the pill, with how late
    const item = (await within(list).findAllByRole("button", { name: /Senior thesis, all of it/ })).filter((b) => b !== pill)[0]
    expect(item.textContent).toMatch(/late/)
    await user.click(item)
    await waitFor(() => expect(window.location.hash).toMatch(/#\/todo\?item=\d+/))
    await user.click(screen.getByRole("link", { name: /^Plan/ }))
    const again = await screen.findByRole("button", { name: /will be late|things will be late/ }, { timeout: 10_000 })
    await user.click(again)
    await user.click(screen.getAllByRole("button", { name: "See options" })[0])
    expect(await screen.findByRole("dialog")).toBeTruthy()
  })

  it("closes its list on a press elsewhere", async () => {
    const { user } = await openFriday("/")
    const pill = await screen.findByRole("button", { name: /will be late|things will be late/ }, { timeout: 20_000 })
    await user.click(pill)
    expect(pill.getAttribute("aria-expanded")).toBe("true")
    await user.click(backToToday())
    expect(pill.getAttribute("aria-expanded")).toBe("false")
    const late = await friday.q<{ late_items: { item_id: number }[] }>("status")
    for (const i of late.late_items) await friday.c("drop", { id: i.item_id })
  })
})

describe("what needs you, softly", () => {
  it("says Friday is replanning, then what slips past its due, with the options", async () => {
    const due = `${addDays(await today(), 1)}T10:00`
    await friday.c("add", { title: "Reading response, long", when: "window", due, amount: "fixed", duration_min: 3000, firmness: "soft" })
    await openFriday("/")
    // the change is being planned: the dot, and the word with room for it
    expect(await screen.findByText("Replanning…", {}, { timeout: 4000 })).toBeTruthy()
    await statusWhen((s) => (s.slipping ?? []).length > 0 && s.plan_generation === s.generation)
    cleanup()
    const { user } = await openFriday("/")
    const pill = await screen.findByRole("button", { name: /past its due|before it's due|after it's due|past their due/ }, { timeout: 10_000 })
    await user.click(pill)
    const list = pill.parentElement as HTMLElement
    const item = (await within(list).findAllByRole("button", { name: /Reading response, long/ })).filter((b) => b !== pill)[0]
    expect(item.textContent).toMatch(/not planned|planned about/)
    await user.click(within(list).getAllByRole("button", { name: "See options" })[0])
    expect(await screen.findByRole("dialog")).toBeTruthy()
    const slipping = await friday.q<Schemas["StatusOut"]>("status")
    for (const i of slipping.slipping ?? []) await friday.c("drop", { id: i.item_id })
  })
})

describe("in a narrow window", () => {
  const page = () => (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM
  it("shows the week as its day, and keeps the views and Today in the Plan menu", async () => {
    const { user } = await openFriday("/")
    page().setViewport({ width: 560, height: 900 })
    try {
      await waitFor(() => expect(screen.queryByRole("group", { name: "View" })).toBeNull())
      await user.click(screen.getByRole("button", { name: "Plan" }))
      const views = screen.getByRole("group", { name: "View" })
      // no week: seven columns don't fit
      expect(within(views).queryByRole("button", { name: "Week" })).toBeNull()
      expect(within(views).getByRole("button", { name: "Day" }).getAttribute("aria-pressed")).toBe("true")
      await user.click(within(views).getByRole("button", { name: "3 days" }))
      expect(screen.queryByRole("group", { name: "View" })).toBeNull()
      await user.click(screen.getByRole("button", { name: "Plan" }))
      expect(within(screen.getByRole("group", { name: "View" })).getByRole("button", { name: "3 days" }).getAttribute("aria-pressed")).toBe("true")
      await user.click(screen.getByRole("button", { name: "Next" }))
      if (!screen.queryByRole("button", { name: "Today" })) await user.click(screen.getByRole("button", { name: "Plan" }))
      await user.click(screen.getByRole("button", { name: "Today" }))
      await gridReady()
    } finally {
      page().setViewport({ width: 1440, height: 900 })
    }
  })
})

describe("the grid", () => {
  it("opens a block's card on a click, or Return when it has the focus", async () => {
    const { tasks } = await nextWeek()
    const { user } = await openOnNextWeek()
    const block = await findBox(tasks[0].key)
    await user.click(block)
    expect(await screen.findByText("Planned · Friday decides")).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Close" }))
    expect(screen.queryByText("Planned · Friday decides")).toBeNull()
    fireEvent.keyDown(block, { key: "Enter" })
    expect(await screen.findByText("Planned · Friday decides")).toBeTruthy()
    // Escape lets it go
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByText("Planned · Friday decides")).toBeNull())
  })

  it("drafts a new event on a double-click in empty time", async () => {
    await openOnNextWeek()
    const column = document.querySelector<HTMLElement>("[data-top-min]") as HTMLElement
    fireEvent.doubleClick(column)
    // dashed on the grid until it's saved, and open in the drawer
    expect((await screen.findAllByText("New event")).length).toBeGreaterThan(0)
  })

  it("opens a block's task in the to-do on a double-click", async () => {
    const { tasks } = await nextWeek()
    await openOnNextWeek()
    fireEvent.doubleClick(await findBox(tasks[0].key))
    await waitFor(() => expect(window.location.hash).toBe(`#/todo?item=${tasks[0].item_id}&found=1`))
  })

  it("pins a block where its time is typed anew; Escape and an unreadable time leave it", async () => {
    const { tasks } = await nextWeek()
    const block = tasks.find((b) => b.end.slice(11) <= "20:00") ?? tasks[0]
    const { user } = await openOnNextWeek()
    const time = () => within(box(block.key) as HTMLElement).getByTitle("Double-click to change the time")
    await findBox(block.key)
    fireEvent.doubleClick(time())
    const field = await screen.findByRole("textbox", { name: "Time" })
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("textbox", { name: "Time" })).toBeNull()
    fireEvent.doubleClick(time())
    await user.clear(screen.getByRole("textbox", { name: "Time" }))
    await user.type(screen.getByRole("textbox", { name: "Time" }), "nonsense")
    expect(screen.getByRole("textbox", { name: "Time" }).getAttribute("aria-invalid")).toBe("true")
    await user.keyboard("{Enter}")
    expect(screen.getByRole("textbox", { name: "Time" })).toBeTruthy()
    expect(field).toBeTruthy()
    await user.clear(screen.getByRole("textbox", { name: "Time" }))
    // the same length, from 8pm
    await user.type(screen.getByRole("textbox", { name: "Time" }), "8pm{Enter}")
    const pin = await waitForSent("pin")
    expect(pin.body).toMatchObject({ id: block.item_id, start: `${block.start.slice(0, 10)}T20:00`, kind: "preferred", from_start: block.start })
  })

  it("changes a fixed-length task's length when its time is typed longer", async () => {
    const day = addDays(await today(), 6)
    const added = await friday.c<{ result: { item: { id: number } } }>("add", { title: "Lab notebook write-up", when: "window", release: `${day}T00:00`, due: `${day}T23:00`, amount: "fixed", duration_min: 60 })
    const { tasks } = await nextWeek()
    const block = tasks.find((b) => b.item_id === added.result.item.id) ?? (await nextWeek()).plan.blocks.find((b) => b.item_id === added.result.item.id) as Schemas["BlockOut"]
    const { user, client } = await openOnNextWeek()
    await findBox(block.key)
    // the length is the to-do's: known once the list has come
    await waitFor(() => expect(client.getQueryData<Schemas["ItemOut"][]>(["items"])?.some((i) => i.id === block.item_id)).toBe(true))
    fireEvent.doubleClick(within(box(block.key) as HTMLElement).getByTitle("Double-click to change the time"))
    const field = await screen.findByRole("textbox", { name: "Time" })
    await user.clear(field)
    await user.type(field, "6am-11:30am{Enter}")
    expect((await waitForSent("edit")).body).toMatchObject({ id: block.item_id })
    expect((await waitForSent("pin")).body).toMatchObject({ id: block.item_id, start: `${block.start.slice(0, 10)}T06:00`, end: `${block.start.slice(0, 10)}T11:30` })
  })

  it("saves an event's time typed anew to the event", async () => {
    const { plan } = await nextWeek()
    const lecture = plan.fixed.find((f) => f.title === "MATH 1910 Lecture") as Schemas["ItemOut"]
    const { user } = await openOnNextWeek()
    const event = await findBox(`F${lecture.id}`)
    fireEvent.doubleClick(within(event).getByTitle("Double-click to change the time"))
    const field = await screen.findByRole("textbox", { name: "Time" })
    await user.clear(field)
    await user.type(field, "10:30am-11:20am{Enter}")
    expect((await waitForSent("edit")).body).toMatchObject({ id: lecture.id, start: `${lecture.start?.slice(0, 10)}T10:30`, end: `${lecture.start?.slice(0, 10)}T11:20` })
  })

  it("moves the selected block a quarter hour with ↑ and ↓, and opens its task with Return", async () => {
    const { tasks } = await nextWeek()
    const block = tasks[tasks.length - 1]
    const { user } = await openOnNextWeek()
    await user.click(await findBox(block.key))
    await screen.findByText(/^Planned · |^Pinned here/)
    await user.keyboard("{ArrowUp}")
    const up = await waitForSent("pin")
    const earlier = new Date(Date.parse(`${block.start}:00Z`) - 15 * 60_000).toISOString().slice(0, 16)
    expect(up.body).toMatchObject({ id: block.item_id, start: earlier, from_start: block.start })
    ;(document.activeElement as HTMLElement | null)?.blur()
    await user.keyboard("{Enter}")
    await waitFor(() => expect(window.location.hash).toBe(`#/todo?item=${block.item_id}`))
  })

  it("picks the block selected first too, on the first ⌘-click", async () => {
    const { tasks } = await nextWeek()
    const [a, b] = tasks.filter((t, i, all) => all.findIndex((x) => x.item_id === t.item_id) === i)
    const { user } = await openOnNextWeek()
    await user.click(await findBox(a.key))
    await user.keyboard("{Meta>}")
    await user.click(await findBox(b.key))
    await user.keyboard("{/Meta}")
    expect(await screen.findByRole("toolbar", { name: "2 blocks picked" })).toBeTruthy()
  })

  it("picks several with ⌘-click, and the bar under the calendar acts on all of them", async () => {
    const { tasks, plan } = await nextWeek()
    const [a, b] = tasks.filter((t, i, all) => all.findIndex((x) => x.item_id === t.item_id) === i)
    const lecture = plan.fixed.find((f) => f.title === "CHEM 2090 Lecture") as Schemas["ItemOut"]
    const { user } = await openOnNextWeek()
    await user.keyboard("{Meta>}")
    await user.click(await findBox(a.key))
    await user.click(await findBox(b.key))
    await user.keyboard("{/Meta}")
    const bar = await screen.findByRole("toolbar", { name: "2 blocks picked" })
    expect(within(bar).getByText(/Esc to clear/)).toBeTruthy()
    await user.click(within(bar).getByRole("button", { name: "Pin" }))
    await user.click(screen.getByRole("button", { name: /^Keep them here/ }))
    const pin = await waitForSent("pin")
    expect([a.item_id, b.item_id]).toContain((pin.body as { id: number }).id)
    expect(pin.body).toMatchObject({ kind: "preferred" })
    // an event picked with them, then all let go with Escape
    fireEvent.click(await findBox(`F${lecture.id}`), { metaKey: true })
    expect(await screen.findByRole("toolbar", { name: "2 blocks, 1 event picked" })).toBeTruthy()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("toolbar", { name: /picked$/ })).toBeNull())
  })

  it("moves the picked blocks together with ↓", async () => {
    const { tasks } = await nextWeek()
    const [a, b] = tasks.filter((t, i, all) => all.findIndex((x) => x.item_id === t.item_id) === i).slice(-2)
    const { user } = await openOnNextWeek()
    fireEvent.click(await findBox(a.key), { metaKey: true })
    fireEvent.click(await findBox(b.key), { metaKey: true })
    const bar = await screen.findByRole("toolbar", { name: "2 blocks picked" })
    await user.keyboard("{ArrowDown}")
    const pin = await waitForSent("pin")
    expect([a.item_id, b.item_id]).toContain((pin.body as { id: number }).id)
    await user.click(within(bar).getByRole("button", { name: "Clear the picked tasks" }))
    expect(screen.queryByRole("toolbar", { name: /picked$/ })).toBeNull()
  })

  it("opens a day's deadlines from its header, each in the card", async () => {
    const { user } = await openFriday("/")
    await gridReady()
    const count = (await screen.findAllByRole("button", { name: /^\d+ due: / }))[0]
    await user.click(count)
    expect(count.getAttribute("aria-expanded")).toBe("true")
    await user.keyboard("{Escape}")
    expect(count.getAttribute("aria-expanded")).toBe("false")
    await user.click(count)
    const menu = screen.getByRole("menu")
    const first = within(menu).getAllByRole("menuitem")[0]
    const title = first.querySelector("span")?.textContent ?? ""
    await user.click(first)
    expect(screen.queryByRole("menu")).toBeNull()
    expect(await screen.findByText(/^Due /)).toBeTruthy()
    expect(screen.getAllByText(title).length).toBeGreaterThan(0)
  })

  it("shows a day's deadlines in a row under its date, ticked off or opened there, a busy day folded to three", async () => {
    window.localStorage.setItem("friday-look-v8", JSON.stringify({ deadlines: "Lanes" }))
    const day = addDays(await today(), 2)
    for (let n = 1; n <= 5; n++) await friday.c("add", { title: `Due row task ${n}`, due: `${day}T${String(9 + n).padStart(2, "0")}:00`, duration_min: 30 })
    const { user } = await openFriday("/")
    await gridReady()
    const row = await screen.findByLabelText("Due under the dates")
    const busy = await within(row).findByLabelText(`Due ${day}`)
    // three of the five, and the rest behind "+N more", which opens them all
    expect(within(busy).getAllByRole("checkbox").length).toBe(3)
    const more = within(busy).getByRole("button", { name: /^\+\d+ more$/ })
    await user.click(more)
    const all = within(busy).getByRole("dialog", { name: `Everything due ${day}` })
    for (let n = 1; n <= 5; n++) expect(within(all).getByText(`Due row task ${n}`)).toBeTruthy()
    // the row gives a title the room: no "end of day" there (the list says it)
    expect(within(busy).queryAllByText("end of day").filter((e) => !all.contains(e))).toHaveLength(0)
    await user.keyboard("{Escape}")
    expect(within(busy).queryByRole("dialog")).toBeNull()
    // opened from the row, and ticked off there
    await user.click(within(busy).getByRole("button", { name: "Due row task 1" }))
    await waitFor(() => expect(document.querySelector("aside.fr-block-card")?.textContent).toContain("Due row task 1"))
    await user.click(within(busy).getByRole("checkbox", { name: "Mark Due row task 1 done" }))
    expect((await waitForSent("done")).body).toMatchObject({ id: expect.any(Number) })
    // the hours keep their full width: no block or event is narrowed for it
    expect(document.querySelector('[style*="--lane"]')).toBeNull()
    // it steps aside while the to-do drawer is out
    await user.click(screen.getByRole("button", { name: "To-do list" }))
    await waitFor(() => expect(screen.queryByLabelText("Due under the dates")).toBeNull())
  })

  it("shows all 24 hours when asked, opening at the morning", async () => {
    window.localStorage.setItem("friday-look-v8", JSON.stringify({ hours: "All day" }))
    await openFriday("/")
    await gridReady()
    for (const hour of ["1am", "3am", "11pm"]) expect(screen.getAllByText(hour).length).toBeGreaterThan(0)
  })

  it("draws whole-day events as bars under the days, a pile of them folded, each opening its card", async () => {
    const day = addDays(await today(), 5)
    for (const title of ["Fall break", "Grandma's birthday", "Career fair", "Reading day"]) {
      await friday.c("add", { title, when: "fixed", start: `${day}T00:00`, end: `${addDays(day, title === "Fall break" ? 2 : 1)}T00:00` })
    }
    const { user } = await openOnNextWeek()
    const bar = await screen.findByRole("button", { name: "Fall break" }, { timeout: 10_000 })
    // three rows at most, the rest a count that opens them all
    const more = await screen.findByRole("button", { name: /^\+\d+ more$/ })
    await user.click(more)
    expect(await screen.findByRole("button", { name: "Reading day" })).toBeTruthy()
    await user.click(screen.getByRole("button", { name: "Show less" }))
    expect(screen.queryByRole("button", { name: "Show less" })).toBeNull()
    await user.click(bar)
    expect(await screen.findByText("Fixed time")).toBeTruthy()
  })

  it("draws what you're timing on today's column, from when you started", async () => {
    const { tasks } = await nextWeek()
    await friday.c("start", { id: tasks[0].item_id })
    await openFriday("/")
    await gridReady()
    expect(await screen.findByText(new RegExp(`^● ${tasks[0].title} · \\d`), {}, { timeout: 10_000 })).toBeTruthy()
    await friday.c("stop", {})
  })

  it("draws the past as it went: sittings you timed and work counted done", async () => {
    const look = (await friday.q<{ calendar_look: Record<string, unknown> }>("settings")).calendar_look
    if (look.show_past_plan === false) await friday.c("settings_set", { key: "calendar_look", value: { ...look, show_past_plan: true } })
    const { user } = await openFriday("/")
    await gridReady()
    const plan = await friday.q<Plan>("plan", { start: `${addDays(await today(), -3)}T00:00`, end: `${addDays(await today(), 4)}T00:00` })
    const long = (b: { start: string; end: string }) => Date.parse(`${b.end}:00Z`) - Date.parse(`${b.start}:00Z`) >= 30 * 60_000
    const sitting = (plan.sessions ?? []).find(long)
    const done = plan.blocks.find((b) => b.state === "done" && long(b))
    if (sitting) {
      const el = await findBox(sitting.key)
      expect(el.getAttribute("title")).toMatch(/^Timed /)
      await user.click(el)
      expect(await screen.findByText("Timed · when you worked on it")).toBeTruthy()
    }
    if (done) {
      await user.click(await findBox(done.key))
      expect(await screen.findByText("Past · counted as done")).toBeTruthy()
    }
    expect(sitting || done).toBeTruthy()
  })
})
