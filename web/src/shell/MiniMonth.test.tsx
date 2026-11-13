// @vitest-environment happy-dom
// The sidebar's mini month follows the main calendar (the audit, 12 Nov: "mini month doesn't follow the main
// calendar"): moved to another week or month, the mini month shows that month; its own arrows still look around. No
// server here: the days aren't tinted, which isn't what's tested.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { followedMonth, MiniMonth } from "./MiniMonth"
import { type CalendarPlace, ShellProvider, useShell } from "./ShellContext"

vi.mock("@/theme/LookProvider", () => ({ useLook: () => ({ light: true, look: { showing: [], showFiltered: false } }) }))

const TODAY = "2026-11-12"

describe("the month it follows (followedMonth)", () => {
  it("is today's month while the calendar is on today", () => {
    expect(followedMonth({ view: 7, first: null }, TODAY)).toBe("2026-11-01")
    expect(followedMonth({ view: "month", first: null }, TODAY)).toBe("2026-11-01")
  })

  it("is the month of the day a day, three days or a week are centred on", () => {
    expect(followedMonth({ view: 7, first: "2026-12-03" }, TODAY)).toBe("2026-12-01")
    expect(followedMonth({ view: 3, first: "2026-10-31" }, TODAY)).toBe("2026-10-01")
    expect(followedMonth({ view: 1, first: "2027-01-01" }, TODAY)).toBe("2027-01-01")
  })

  it("is the month the month view shows", () => {
    expect(followedMonth({ view: "month", first: "2027-02-01" }, TODAY)).toBe("2027-02-01")
  })
})

let move: (place: CalendarPlace) => void = () => {}
function Mover() {
  move = useShell().setPlace
  return null
}

beforeEach(() => {
  window.innerWidth = 1440
  vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {})) // nothing answers: no tints
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ShellProvider today={TODAY}>
          <Mover />
          <MiniMonth />
        </ShellProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

const heading = () => document.querySelector(".fr-h")?.textContent

describe("the mini month, beside the calendar", () => {
  it("shows the month the calendar moves to, a week or a month at a time, and back to today", () => {
    open()
    expect(heading()).toBe("November 2026")
    act(() => move({ view: 7, first: "2026-12-03" }))
    expect(heading()).toBe("December 2026")
    act(() => move({ view: "month", first: "2027-01-01" }))
    expect(heading()).toBe("January 2027")
    act(() => move({ view: "month", first: null }))
    expect(heading()).toBe("November 2026")
  })

  it("still looks around with its own arrows, and follows the calendar again when it moves", async () => {
    const user = open()
    await user.click(screen.getByRole("button", { name: "Next month" }))
    await user.click(screen.getByRole("button", { name: "Next month" }))
    expect(heading()).toBe("January 2027")
    act(() => move({ view: 7, first: "2026-11-19" }))
    expect(heading()).toBe("November 2026")
  })

  it("stays on the month you looked at while the calendar stays in its month", async () => {
    const user = open()
    await user.click(screen.getByRole("button", { name: "Previous month" }))
    expect(heading()).toBe("October 2026")
    act(() => move({ view: 7, first: null })) // the same place again: nothing moved
    expect(heading()).toBe("October 2026")
  })
})
