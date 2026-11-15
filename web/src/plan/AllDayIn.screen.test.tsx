// A calendar's all-day event, as Friday reads it in (15 Nov: a client's Thanksgiving and own all-day events never
// showed), sits in the whole-day strip under the days, not over the hours: a holiday on a Mac calendar posted as the
// Mac app posts it, read by Friday's own sync, a file of its own so the new calendar reaches no other test.
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { addDays } from "@/lib/time"
import { friday, openFriday } from "@/test/friday"

type Calendar = Schemas["CalendarOut"]
type Plan = Schemas["PlanOut"]

describe("an all-day event from a calendar", () => {
  it("comes in on its own and shows in the whole-day strip, not on the hours", async () => {
    // Google's settings as a new user has them: the sample says all-day events in, which the default now does
    const { gcal } = await friday.q<{ gcal: Record<string, unknown> }>("settings")
    const { include_all_day: _said, ...defaults } = gcal
    await friday.c("settings_set", { key: "gcal", value: defaults })
    const today = (await friday.q<Calendar>("calendar", { start: "2026-01-01", days: "1" })).today
    const day = addDays(today, 1)
    const holidays = { id: "mac-holidays", name: "Holidays on the Mac", account: "iCloud", type: "subscription", color: "#3a5a8c" }
    const holiday = { id: "thanksgiving", calendar: holidays.id, title: "Thanksgiving", start: day, end: addDays(day, 1), all_day: true }
    const offset = (d: string) => `${d}T00:00:00-05:00`
    await friday.c("mac_sync", { calendars: [holidays], events: [holiday], since: offset(addDays(today, -1)), until: offset(addDays(today, 14)) })
    await friday.c("calendar_set", { id: holidays.id, mac: true, on: true, trusted: true })
    await waitFor(
      async () => {
        const { fixed } = await friday.q<Plan>("plan", { start: `${day}T00:00`, end: `${addDays(day, 1)}T00:00` })
        expect(fixed.map((f) => f.title)).toContain("Thanksgiving")
      },
      { timeout: 80_000, interval: 1000 },
    ) // the next minute's sync reads it
    await openFriday("/")
    const bar = await screen.findByRole("button", { name: "Thanksgiving" }, { timeout: 15_000 })
    expect(bar.classList.contains("fr-whole-day")).toBe(true) // the strip's bar, not a box on the hours
    expect(document.querySelector('[data-tour="calendar"] [data-block-key][title*="Thanksgiving"]')).toBeNull()
  }, 120_000)
})
