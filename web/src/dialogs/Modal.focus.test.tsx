// @vitest-environment happy-dom
// A dialog keeps the keys while it's open (the audit, 12 Nov: the integration panel had no focus trap): Tab and
// Shift-Tab go round inside it, Escape closes it, and the focus goes back to what opened it.
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, describe, expect, it } from "vitest"
import { Modal } from "./Dialogs"

afterEach(cleanup)

function Page() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <button>Behind</button>
      {open && (
        <Modal onClose={() => setOpen(false)} label="Test">
          <button>First</button>
          <input aria-label="Middle" />
          <button onClick={() => setOpen(false)}>Last</button>
        </Modal>
      )}
    </>
  )
}

async function opened() {
  const user = userEvent.setup()
  render(<Page />)
  const opener = screen.getByRole("button", { name: "Open" })
  await user.click(opener)
  return { user, opener, dialog: screen.getByRole("dialog", { name: "Test" }) }
}

const focused = () => (document.activeElement as HTMLElement | null)?.textContent || document.activeElement?.getAttribute("aria-label")

describe("a dialog, from the keyboard", () => {
  it("takes the focus when it opens", async () => {
    const { dialog } = await opened()
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it("keeps Tab inside it, going round from the last to the first", async () => {
    const { user, dialog } = await opened()
    const seen: (string | null | undefined)[] = []
    for (let i = 0; i < 7; i++) {
      await user.tab()
      expect(dialog.contains(document.activeElement)).toBe(true)
      seen.push(focused())
    }
    expect(seen.slice(0, 6)).toEqual(["First", "Middle", "Last", "First", "Middle", "Last"])
  })

  it("keeps Shift-Tab inside it, going round from the first to the last", async () => {
    const { user, dialog } = await opened()
    await user.tab() // First
    await user.tab({ shift: true })
    expect(focused()).toBe("Last")
    await user.tab({ shift: true })
    expect(focused()).toBe("Middle")
    for (let i = 0; i < 5; i++) {
      await user.tab({ shift: true })
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
  })

  it("closes on Escape, the focus back on what opened it", async () => {
    const { user, opener } = await opened()
    await user.tab()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(document.activeElement).toBe(opener)
  })

  it("gives the focus back however it closes", async () => {
    const { user, opener } = await opened()
    await user.click(screen.getByRole("button", { name: "Last" }))
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(document.activeElement).toBe(opener)
  })
})
