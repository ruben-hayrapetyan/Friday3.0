// @vitest-environment happy-dom
// The pigment menu (Settings → Calendars, a calendar's or a category's paint) closes on Escape and gives the focus back
// to its button, as Friday's other menus close (the audit, 12 Nov: "PigmentMenu has no Esc"); a press beside it closes
// it too. The look is a stand-in: only whether the page is light matters here.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { PigmentMenu } from "./CalendarsSection"

vi.mock("@/theme/LookProvider", () => ({ useLook: () => ({ light: true }) }))

afterEach(cleanup)

function open(value: string | null = null, onPick = vi.fn(), outer = vi.fn()) {
  const user = userEvent.setup()
  render(
    <div onKeyDown={outer}>
      <PigmentMenu value={value} onPick={onPick} />
      <button>Elsewhere</button>
    </div>,
  )
  const button = document.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!
  return { user, button, onPick, outer }
}

describe("the pigment menu, from what it should do", () => {
  it("closes on Escape, picks nothing, and puts the focus back on its button", async () => {
    const { user, button, onPick } = open()
    await user.click(button)
    expect(screen.getByRole("listbox")).toBeTruthy()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("listbox")).toBeNull()
    expect(button.getAttribute("aria-expanded")).toBe("false")
    expect(document.activeElement).toBe(button)
    expect(onPick).not.toHaveBeenCalled()
  })

  it("closes on Escape pressed on one of its pigments, the focus back on its button", async () => {
    const { user, button } = open("blue")
    await user.click(button)
    screen.getByRole("option", { name: "Ochre" }).focus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("listbox")).toBeNull()
    expect(document.activeElement).toBe(button)
  })

  it("closes on Escape even with the focus nowhere (a click in Safari doesn't focus a button)", async () => {
    const { user, button } = open()
    await user.click(button)
    button.blur()
    fireEvent.keyDown(window, { key: "Escape" })
    expect(screen.queryByRole("listbox")).toBeNull()
    expect(document.activeElement).toBe(button)
  })

  it("closes on a press beside it", async () => {
    const { user, button } = open()
    await user.click(button)
    await user.click(screen.getByRole("button", { name: "Elsewhere" }))
    expect(screen.queryByRole("listbox")).toBeNull()
  })

  it("still picks a pigment, and closes with the focus on its button", async () => {
    const { user, button, onPick } = open()
    await user.click(button)
    await user.click(screen.getByRole("option", { name: "Cerulean" }))
    expect(onPick).toHaveBeenCalledWith("blue")
    expect(screen.queryByRole("listbox")).toBeNull()
    expect(document.activeElement).toBe(button)
  })
})

describe("the pigment menu, inside", () => {
  it("keeps the Escape that closed it from the pane or dialog around it", async () => {
    const { user, button, outer } = open()
    await user.click(button)
    await user.keyboard("{Escape}")
    expect(outer.mock.calls.filter(([e]) => e.key === "Escape")).toHaveLength(0)
  })

  it("lets Escape through while it's closed, so what it's in can close", async () => {
    const { user, button, outer } = open()
    button.focus()
    await user.keyboard("{Escape}")
    expect(outer.mock.calls.filter(([e]) => e.key === "Escape")).toHaveLength(1)
  })

  it("stops listening for Escape and presses once closed", async () => {
    const add = vi.spyOn(window, "addEventListener")
    const remove = vi.spyOn(window, "removeEventListener")
    const { user, button } = open()
    await user.click(button)
    const added = add.mock.calls.filter(([type]) => type === "keydown" || type === "pointerdown").map(([type, fn]) => [type, fn])
    expect(added.map(([type]) => type).sort()).toEqual(["keydown", "pointerdown"])
    await user.keyboard("{Escape}")
    for (const [type, fn] of added) expect(remove).toHaveBeenCalledWith(type, fn)
    add.mockRestore()
    remove.mockRestore()
  })
})
