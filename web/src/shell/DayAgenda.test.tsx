// @vitest-environment happy-dom
// The sidebar agenda's Today is the calendar's date, turning at midnight (15 Nov: "Split at midnight"), as the
// calendar's columns are: at 12:30am on the 15th it shows the 15th, though the planning day is still the 14th. No
// server here: what it asks for is what's checked.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { LookProvider } from "@/theme/LookProvider"
import { DayAgenda } from "./DayAgenda"
import { ShellProvider } from "./ShellContext"

let asked: string[] = []
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 15, 0, 30))
  asked = []
  vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    asked.push(`${String(input)} ${String(init?.body ?? "")}`)
    return new Promise(() => {})
  })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("the agenda's Today", () => {
  it("is the calendar's date at 12:30am, not the planning day still running", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <LookProvider>
            <ShellProvider today="2026-11-14">
              <DayAgenda />
            </ShellProvider>
          </LookProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText("Today")).toBeTruthy()
    const plans = asked.filter((a) => a.includes("plan"))
    expect(plans.some((a) => a.includes("2026-11-15T00"))).toBe(true)
    expect(plans.some((a) => a.includes("2026-11-14T00"))).toBe(false)
  })
})
