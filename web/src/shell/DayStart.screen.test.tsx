// Your day start reaches the helpers that place things by day (lib/dayStart.ts), over a real Friday: changed in
// settings, the app follows it on its next read, with no reload.
import { waitFor } from "@testing-library/react"
import { afterAll, describe, expect, it } from "vitest"
import { dayStartClock, dayStartMin, setDayStart } from "@/lib/dayStart"
import { when } from "@/lib/format"
import { friday, openFriday } from "@/test/friday"

type Settings = { time: Record<string, unknown> }
const setTime = async (day_start: string) => {
  const { time } = await friday.q<Settings>("settings")
  await friday.c("settings_set", { key: "time", value: { ...time, day_start } })
}

afterAll(async () => {
  await setTime("04:00")
  setDayStart("04:00")
})

describe("the day start", () => {
  it("is Friday's own, and a changed one is followed by what the app draws", async () => {
    const view = await openFriday("/")
    await waitFor(() => expect(view.client.getQueryData(["settings"])).toBeTruthy(), { timeout: 20_000 })
    expect(dayStartClock()).toBe("04:00")
    await setTime("06:00")
    await view.client.invalidateQueries({ queryKey: ["settings"] })
    await waitFor(() => expect(dayStartMin()).toBe(360))
    expect(when("2026-10-27T06:00", "2026-10-20")).toBe("Mon, end of day")
  })
})
