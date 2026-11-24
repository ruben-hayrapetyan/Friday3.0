// @vitest-environment happy-dom
// The calendar split at midnight (15 Nov, the user's "Split at midnight"): what's between midnight and your day start
// shows under the next date's column; a block over midnight is two linked pieces, each opening the same thing; the
// hours open at 12am only when something's in the night's small hours; the day headers count hours by date; today's
// column and the now line follow the calendar's date at 12:30am, while the planning day is still the day before. The
// grid on a page with no server: the plan and the calendar are given.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Block, Schemas } from "@/api/client"
import { setDayStart } from "@/lib/dayStart"
import { addDays } from "@/lib/time"
import { ShellProvider, useShell } from "@/shell/ShellContext"
import { LookProvider } from "@/theme/LookProvider"
import { Grid } from "./Grid"

const DATES = ["2026-11-13", "2026-11-14", "2026-11-15"]
const night = (date: string) => ({ date, cap_hours: 1, pace: null, bedtime: `${date}T23:30`, core: `${date}T23:45`, wake: `${addDays(date, 1)}T07:30` })
const calendar = { now: "2026-11-15T00:30", today: "2026-11-14", axis_start_min: 450, axis_end_min: 1425, days: DATES.map(night), dues: [] } as Schemas["CalendarOut"]
const block = (key: string, title: string, start: string, end: string): Block => ({ key, item_id: Number(key.slice(1, 3)), title, start, end, cost: {} }) as Block
const plan = (blocks: Block[], hours = {}) => ({ plan_id: 1, blocks, fixed: [], day_hours: hours, sessions: [] }) as Schemas["PlanOut"]

let shell: ReturnType<typeof useShell>
function Spy() {
  shell = useShell()
  return null
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 15, 0, 30)) // 12:30am on the 15th: the 14th's planning day until 4am
  setDayStart("04:00")
  window.innerWidth = 1440
  vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {})) // nothing answers
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function open(blocks: Block[], hours: Record<string, number> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LookProvider>
          <ShellProvider today="2026-11-14">
            <Spy />
            <Grid dates={DATES} calendar={calendar} plan={plan(blocks, hours)} marginRight={0} />
          </ShellProvider>
        </LookProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const columnOf = (el: Element) => (el.closest("[data-top-min]") as HTMLElement).dataset.topMin as string
const dateOf = (el: Element) => new Date(Number(columnOf(el)) * 60000).toISOString().slice(0, 10)
const pieces = (key: string) => [...document.querySelectorAll(`[data-block-key="${key}"]`)]

describe("the calendar split at midnight", () => {
  it("draws a block over midnight as two pieces, by date, each opening the same block", () => {
    open([block("T11@2026-11-13T23:00", "Essay", "2026-11-13T23:00", "2026-11-14T01:00")])
    const [evening, night] = pieces("T11@2026-11-13T23:00")
    expect([dateOf(evening), dateOf(night)]).toEqual(["2026-11-13", "2026-11-14"])
    act(() => (evening as HTMLElement).click())
    expect(shell.selected?.key).toBe("T11@2026-11-13T23:00")
    act(() => shell.select(null))
    act(() => (night as HTMLElement).click())
    expect(shell.selected?.key).toBe("T11@2026-11-13T23:00")
  })

  it("shows what's between midnight and the day start under the next date, the hours opening at 12am for it", () => {
    open([block("T12@2026-11-14T01:00", "Reading", "2026-11-14T01:00", "2026-11-14T02:00")])
    const [only] = pieces("T12@2026-11-14T01:00")
    expect(dateOf(only)).toBe("2026-11-14") // not the foot of the 13th's column
    expect(Number(columnOf(only)) % 1440).toBe(0) // the columns open at 12am
    expect(screen.getAllByText("12am").length).toBeGreaterThan(0)
  })

  it("opens the columns as usual when nothing is in the night's small hours", () => {
    vi.setSystemTime(new Date(2026, 10, 14, 14, 0)) // the afternoon: the now line asks for nothing early either
    open([block("T13@2026-11-14T09:00", "Lab", "2026-11-14T09:00", "2026-11-14T10:00")])
    expect(Number(columnOf(pieces("T13@2026-11-14T09:00")[0])) % 1440).toBe(450) // 7:30am, the usual start
    expect(screen.queryByText("12am")).toBeNull()
  })

  it("says each date's hours in its header as the server counts them: work over midnight on each side of it", () => {
    // 23:00–01:30 with 1h a day: 1h on the 13th, none over; 1.5h on the 14th, half an hour over. The header reads the
    // server's `day_hours` (23 Nov: worked out here, it disagreed with the Plan page's note and the day panel).
    open([block("T11@2026-11-13T23:00", "Essay", "2026-11-13T23:00", "2026-11-14T01:30")], { "2026-11-13": 1, "2026-11-14": 1.5 })
    const [over] = screen.getAllByText(/h over$/)
    expect(over.textContent).toBe("0.5 h over")
    expect(over.closest("[data-drop-day]")?.getAttribute("data-drop-day")).toBe("2026-11-14")
  })

  it("draws the night's sleep as two pieces by date, the small hours at the top of the next date's column", () => {
    open([]) // 12:30am: the columns open at 12am for the now line
    const bands = (date: string) =>
      [...document.querySelectorAll<HTMLElement>("[data-night]")].filter((d) => dateOf(d) === date)
    const kinds = bands("2026-11-15").map((d) => [d.dataset.night, d.style.top])
    expect(kinds).toContainEqual(["core", "0px"]) // the 14th's night from midnight, at the top of the 15th's column
    expect(kinds.filter(([kind]) => kind === "margin")).toHaveLength(1) // and the 15th's own, from 11:30pm
  })

  it("puts today's column and the now line on the calendar's date at 12:30am", () => {
    open([])
    const line = [...document.querySelectorAll<HTMLElement>("[data-top-min] > div")].find((d) => d.style.height === "2px" && d.style.background === "var(--fr-now)")
    expect(line && dateOf(line)).toBe("2026-11-15")
    const header = screen.getByText("15").parentElement?.parentElement as HTMLElement
    expect(header.lastElementChild?.getAttribute("style") ?? "").toContain("var(--color-accent)") // today's underline
  })
})
