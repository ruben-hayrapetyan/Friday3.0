// Breaks on the screen, over a real Friday (black box). 19 Nov: a Light day is time a day, not a number of things
// ("the number of time that you spend total working shouldn't depend on the number of events that you choose to do
// (and the number of time that you should spend working should also be customizeable)").
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { friday, openFriday, waitForSent } from "@/test/friday"
import { addDays } from "@/lib/time"
import { rangeWords } from "./words"

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

// 19 Nov, of prototype 2: "i like the dragging" and, for longer breaks, "instead of the yellow inbox in the top right
// corner can we make that a 'breaks' clickable square" (no umbrella).
describe("ways into a break", () => {
  it("the Breaks button where the Inbox tray was: your breaks, and a new one today or from a day you pick", async () => {
    const { user } = await openFriday("/")
    const button = await screen.findByRole("button", { name: /^Breaks/ }, { timeout: 15_000 })
    expect(screen.queryByRole("button", { name: /waiting in your Inbox$/ })).toBeNull()
    await user.click(button)
    const panel = await screen.findByRole("dialog", { name: "Breaks" })
    expect(within(panel).getByText("Or drag across days on the calendar.")).toBeTruthy()
    await user.click(within(panel).getByRole("button", { name: "New break, starting today" }))
    const made = await screen.findByRole("dialog", { name: /break/i })
    expect(within(made).getByRole("button", { name: /Add|Make|Take/ })).toBeTruthy()
  })

  it("lists a planned break, which opens to change", async () => {
    const { today } = await friday.q<{ today: string }>("calendar", { start: "2026-01-01", days: "1" })
    const end = addDays(today, 2)
    await friday.c("vacation_add", { name: "Long weekend", start: today, end, mode: "off" })
    const { user } = await openFriday("/")
    await user.click(await screen.findByRole("button", { name: "Breaks, 1 break planned" }, { timeout: 15_000 }))
    await user.click(within(await screen.findByRole("dialog", { name: "Breaks" })).getByRole("button", { name: /^Long weekend/ }))
    expect(await screen.findByDisplayValue("Long weekend")).toBeTruthy()
    await friday.c("vacation_delete", { id: (await friday.q<{ vacations: { id: number }[] }>("vacations")).vacations[0].id })
  })

  it("dragging across days in the week's headers offers to make them a break, with their dates", async () => {
    const { user } = await openFriday("/")
    await screen.findByRole("button", { name: /^Breaks/ }, { timeout: 15_000 })
    const heads = await waitFor(() => {
      const found = [...document.querySelectorAll<HTMLElement>("div[data-span-day]")]
      expect(found.length).toBeGreaterThan(2)
      return found
    })
    const [from, , to] = heads
    const was = document.elementFromPoint
    document.elementFromPoint = () => to
    try {
      fireEvent.pointerDown(from)
      fireEvent.pointerMove(document)
      await waitFor(() => expect(heads.slice(0, 3).every((h) => h.hasAttribute("data-spanned"))).toBe(true)) // lit as you go
      expect(heads[3].hasAttribute("data-spanned")).toBe(false)
      fireEvent.pointerUp(document)
    } finally {
      document.elementFromPoint = was
    }
    const offer = await screen.findByRole("menu", { name: "These days" })
    await user.click(within(offer).getByRole("menuitem", { name: "Make these days a break…" }))
    const dialog = await screen.findByRole("dialog", { name: /break/i })
    const [a, b] = [from.dataset.spanDay!, to.dataset.spanDay!]
    expect(within(dialog).getByText(rangeWords(a, b))).toBeTruthy()
  })

  // 19 Nov, you, of 0.6.0: "when you select days for a break, it also selects all of the text on the page"
  async function weekHeads() {
    await openFriday("/")
    await screen.findByRole("button", { name: /^Breaks/ }, { timeout: 15_000 })
    return waitFor(() => {
      const found = [...document.querySelectorAll<HTMLElement>("div[data-span-day]")]
      expect(found.length).toBeGreaterThan(2)
      return found
    })
  }
  const startsSelecting = (on: Element) => on.dispatchEvent(new Event("selectstart", { bubbles: true, cancelable: true }))

  it("dragging across days selects no text on the page, and the page selects again once you let go", async () => {
    const heads = await weekHeads()
    const [from, , to] = heads
    const text = screen.getAllByText(/./).find((e) => !e.closest("[data-span-day]"))!
    const range = document.createRange()
    range.selectNodeContents(text)
    window.getSelection()!.addRange(range) // something selected before
    const was = document.elementFromPoint
    document.elementFromPoint = () => to
    try {
      expect(fireEvent.mouseDown(from)).toBe(false) // the press starts no selection
      fireEvent.pointerDown(from)
      expect(window.getSelection()!.toString()).toBe("") // what was selected is let go
      fireEvent.pointerMove(document)
      expect(startsSelecting(text)).toBe(false) // nothing on the page starts selecting while you drag
      expect(document.documentElement.classList.contains("fr-spanning")).toBe(true)
      fireEvent.pointerUp(document)
    } finally {
      document.elementFromPoint = was
    }
    expect(await screen.findByRole("menu", { name: "These days" })).toBeTruthy() // the drag still does its work
    expect(startsSelecting(text)).toBe(true)
    expect(document.documentElement.classList.contains("fr-spanning")).toBe(false)
  })

  it("a drag cut short (a touch taken back, the window left) offers nothing and leaves the page selectable", async () => {
    for (const cut of [() => fireEvent.pointerCancel(document), () => fireEvent.blur(window)]) {
      const heads = await weekHeads()
      const [from, , to] = heads
      const was = document.elementFromPoint
      document.elementFromPoint = () => to
      try {
        fireEvent.pointerDown(from)
        fireEvent.pointerMove(document)
        await waitFor(() => expect(to.hasAttribute("data-spanned")).toBe(true))
        cut()
      } finally {
        document.elementFromPoint = was
      }
      await waitFor(() => expect(to.hasAttribute("data-spanned")).toBe(false))
      fireEvent.pointerUp(document) // a late letting go does nothing either
      expect(screen.queryByRole("menu", { name: "These days" })).toBeNull()
      expect(startsSelecting(document.body)).toBe(true)
      expect(document.documentElement.classList.contains("fr-spanning")).toBe(false)
    }
  })

  it("the Breaks button is the same button as Show and Plan beside it, its height not its own (\"significantly skinnier\")", async () => {
    await openFriday("/")
    const breaks = await screen.findByRole("button", { name: /^Breaks/ }, { timeout: 15_000 })
    const plan = screen.getByRole("button", { name: /^Plan/ })
    expect(breaks.classList.contains("btn-secondary") && plan.classList.contains("btn-secondary")).toBe(true)
    for (const size of ["padding", "paddingTop", "paddingBottom", "height", "minHeight", "lineHeight"] as const) expect(breaks.style[size]).toBe(plan.style[size])
  })

  it("a press on one day without moving is still a click, not a break", async () => {
    await openFriday("/")
    await screen.findByRole("button", { name: /^Breaks/ }, { timeout: 15_000 })
    const head = await waitFor(() => {
      const found = document.querySelector<HTMLElement>("div[data-span-day]")
      expect(found).toBeTruthy()
      return found!
    })
    const was = document.elementFromPoint
    document.elementFromPoint = () => head
    try {
      fireEvent.pointerDown(head)
      fireEvent.pointerUp(document)
    } finally {
      document.elementFromPoint = was
    }
    expect(screen.queryByRole("menu", { name: "These days" })).toBeNull()
  })
})
