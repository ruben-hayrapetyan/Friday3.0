// Settings → Appearance → Clock, over a real Friday: 12-hour until you choose 24-hour; then the choice is Friday's
// (settings `clock`), shown at once, and every time reads on it: the preview, the calendar's hours, a time box, and the
// server's own sentences (your rules). Alex's sample; the server's live updates are stood in for by asking again.

import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterAll, describe, expect, it } from "vitest"
import { setClock } from "@/lib/clock"
import { friday, openFriday, waitForSent } from "@/test/friday"

const clockNow = async () => (await friday.q<{ clock: string }>("settings")).clock
const TWELVE = /^\d{1,2}(:\d\d)?(am|pm)$/
const TWENTY_FOUR = /^\d\d:\d\d$/

afterAll(async () => {
  await friday.c("settings_set", { key: "clock", value: "12h" })
  setClock("12h")
  window.localStorage.removeItem("friday-clock")
})

describe("the clock", () => {
  it("is 12-hour until you choose, and 24-hour reads every time on it at once, kept by Friday", async () => {
    const { user, unmount } = await openFriday("/settings/appearance")
    const choice = screen.getByRole("group", { name: "Clock" })
    await waitFor(() => expect(within(choice).getByRole("button", { name: "12-hour" }).getAttribute("aria-pressed")).toBe("true"))
    expect(screen.getByText(/^PS5 runs until 12pm\./)).toBeTruthy()

    await user.click(within(choice).getByRole("button", { name: "24-hour" }))
    // shown before the server answers
    expect(within(choice).getByRole("button", { name: "24-hour" }).getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByText(/^PS5 runs until 12:00\./)).toBeTruthy()
    expect(screen.getByText("09:00–12:00")).toBeTruthy()
    expect((await waitForSent("settings_set")).body).toEqual({ key: "clock", value: "24h" })
    await waitFor(async () => expect(await clockNow()).toBe("24h"))
    expect(window.localStorage.getItem("friday-clock")).toBe("24h") // a reload opens on it before settings load

    // Schedule's times, and a time box: "07:30", and a typed 9 is 09:00, with no am or pm filled in
    await user.click(screen.getByRole("link", { name: "Schedule" }))
    await screen.findByText("The shape of a normal day. Friday plans inside these limits.")
    const options = screen.getAllByRole("option").map((o) => o.textContent ?? "")
    expect(options.length).toBeGreaterThan(5)
    expect(options.every((t) => TWENTY_FOUR.test(t))).toBe(true)
    await user.click(screen.getByRole("button", { name: "Set each day" }))
    const wake = screen.getByRole("textbox", { name: "mon wake" }) as HTMLInputElement
    expect(wake.value).toMatch(TWENTY_FOUR)
    await user.clear(wake)
    await user.type(wake, "9")
    expect(wake.parentElement?.textContent).not.toMatch(/am|pm/)
    fireEvent.keyDown(wake, { key: "Escape" })
    unmount()

    // the server's own sentences: your rules
    const rules = await openFriday("/rules")
    expect(await screen.findByText("No work after 23:00")).toBeTruthy()
    expect(screen.queryByText("No work after 11pm")).toBeNull()
    rules.unmount()

    // the calendar's hours down its side
    await openFriday("/")
    await waitFor(() => expect(screen.getAllByText(TWENTY_FOUR).length).toBeGreaterThan(4))
    expect(screen.queryAllByText(TWELVE)).toEqual([])
  })

  it("goes back to 12-hour as it came", async () => {
    await friday.c("settings_set", { key: "clock", value: "24h" })
    const { user, unmount } = await openFriday("/settings/appearance")
    const choice = screen.getByRole("group", { name: "Clock" })
    await waitFor(() => expect(within(choice).getByRole("button", { name: "24-hour" }).getAttribute("aria-pressed")).toBe("true"))
    await user.click(within(choice).getByRole("button", { name: "12-hour" }))
    expect(screen.getByText(/^PS5 runs until 12pm\./)).toBeTruthy()
    await waitFor(async () => expect(await clockNow()).toBe("12h"))
    unmount()
    const rules = await openFriday("/rules")
    expect(await screen.findByText("No work after 11pm")).toBeTruthy()
    rules.unmount()
  })
})
