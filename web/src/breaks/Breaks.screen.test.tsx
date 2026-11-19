// Breaks on the screen, over a real Friday (black box). 19 Nov: a Light day is time a day, not a number of things
// ("the number of time that you spend total working shouldn't depend on the number of events that you choose to do
// (and the number of time that you should spend working should also be customizeable)").
import { screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"

describe("a Light day's time", () => {
  it("is a value in Settings → Breaks: common amounts, and saved as minutes a day", async () => {
    const { user } = await openFriday("/settings/breaks")
    const value = await screen.findByRole("button", { name: "Work on a light day: 2h a day" })
    await user.click(value)
    const picker = await screen.findByRole("dialog", { name: "Work on a light day" })
    await user.click(within(picker).getByRole("button", { name: "3h" }))
    expect((await waitForSent("settings_set")).body).toMatchObject({ key: "breaks", value: { work_min: 180 } })
    await waitFor(async () => expect((await friday.q<{ breaks: { work_min: number } }>("settings")).breaks.work_min).toBe(180))
    expect(await screen.findByRole("button", { name: "Work on a light day: 3h a day" })).toBeTruthy()
  })

  it("takes a typed amount too", async () => {
    const { user } = await openFriday("/settings/breaks")
    await user.click(await screen.findByRole("button", { name: /^Work on a light day: / }))
    const picker = await screen.findByRole("dialog", { name: "Work on a light day" })
    await user.type(within(picker).getByRole("textbox", { name: "Work on a light day, typed" }), "an hour and a half{Enter}")
    await waitFor(async () => expect((await friday.q<{ breaks: { work_min: number } }>("settings")).breaks.work_min).toBe(90))
  })
})
