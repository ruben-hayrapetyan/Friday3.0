// @vitest-environment happy-dom
// 17 Nov, a client's notes: "text wrap issues (due to overlapping things?)": a lab, 2:30–4:25pm, its long location
// wrapped down under a meal eaten at 3:45 and a running timer drawn over it. Its words now stop above the first thing
// over it. The grid on a page with no server: the plan and the calendar are given.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Block, Item, Schemas } from "@/api/client"
import { setDayStart } from "@/lib/dayStart"
import { ShellProvider } from "@/shell/ShellContext"
import { LookProvider } from "@/theme/LookProvider"
import { Grid } from "./Grid"
import { detailLines, roomAbove } from "./lines"
import { PX } from "./Pieces"

const DAY = "2026-11-18"
const calendar = { now: `${DAY}T09:00`, today: DAY, axis_start_min: 450, axis_end_min: 1425, days: [{ date: DAY, cap_hours: 8, pace: null, bedtime: `${DAY}T23:30`, core: `${DAY}T23:45`, wake: "2026-11-19T07:30" }], dues: [] } as unknown as Schemas["CalendarOut"]
const LAB = { id: 7, title: "AEP 1100 Lab", when: "fixed", start: `${DAY}T14:30`, end: `${DAY}T16:25`, location: "Physical Sciences Building 131, 245 Feeney Wy, Ithaca, NY 14853, USA", event_kind: "class", status: "todo", tags: [] } as unknown as Item
const snack = { key: "T41", item_id: 41, title: "Snack", start: `${DAY}T15:45`, end: `${DAY}T16:00`, cost: {} } as Block

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 18, 9, 0))
  setDayStart("04:00")
  window.innerWidth = 1440
  vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}))
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function open(blocks: Block[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const plan = { plan_id: 1, blocks, fixed: [LAB], day_hours: {}, sessions: [] } as unknown as Schemas["PlanOut"]
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LookProvider>
          <ShellProvider today={DAY}>
            <Grid dates={[DAY]} calendar={calendar} plan={plan} marginRight={0} />
          </ShellProvider>
        </LookProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return document.querySelector<HTMLElement>(`[data-key="F${LAB.id}"] [data-lines]`) ?? document.querySelector<HTMLElement>("[data-lines]")
}

describe("an event's words with something drawn over it", () => {
  it("stop above it: the lines that fit before 3:45, not the whole box's", () => {
    const details = open([snack]) as HTMLElement
    const fits = detailLines(75 * PX - 2, 1) // 2:30 to 3:45
    expect(Number(details.dataset.lines)).toBe(fits)
    expect(fits).toBeLessThan(detailLines(115 * PX - 2, 1))
  })
  it("take the whole box when nothing is over it", () => {
    const details = open([]) as HTMLElement
    expect(Number(details.dataset.lines)).toBe(detailLines(115 * PX - 2, 1))
  })
})

describe("roomAbove", () => {
  const box = { top: 100, height: 115, column: 0, columns: 1 }
  it("is the minutes before the first thing over the box, in its width", () => {
    expect(roomAbove(box, [{ top: 175, from: 0, to: 1 }, { top: 190, from: 0, to: 1 }])).toBe(75)
  })
  it("ignores what's beside it, before it or after it, and keeps its first 15 minutes", () => {
    expect(roomAbove({ ...box, column: 0, columns: 2 }, [{ top: 175, from: 0.5, to: 1 }])).toBe(115)
    expect(roomAbove(box, [{ top: 90, from: 0, to: 1 }, { top: 215, from: 0, to: 1 }])).toBe(115)
    expect(roomAbove(box, [{ top: 105, from: 0, to: 1 }])).toBe(15)
  })
})
