// @vitest-environment happy-dom
// A dropdown's list, fixed over the page, is at least as wide as its button and no wider than its choices need (16 Nov,
// IMG 4240: the stylesheet's `min-width: 100%` meant the window once the list was fixed, and an event's Category list
// ran across the whole bottom of the screen, its left edge cut off).
import { render } from "@testing-library/react"
import { useRef } from "react"
import { describe, expect, it } from "vitest"
import { useMenuPlace } from "./menuPlace"

function Dropdown() {
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  useMenuPlace(true, button, list)
  return (
    <div className="fr-menu" style={{ minWidth: "100%" }}>
      <button ref={button}>None</button>
      <div ref={list} role="listbox" aria-label="Category" style={{ minWidth: "100%" }} />
    </div>
  )
}

describe("a dropdown's list over the page", () => {
  it("is held to its button's width in pixels, not to a share of the window", () => {
    const real = HTMLElement.prototype.getBoundingClientRect
    HTMLElement.prototype.getBoundingClientRect = function () {
      return this.tagName === "BUTTON" ? new DOMRect(900, 380, 140, 32) : new DOMRect(0, 0, 0, 0)
    }
    try {
      const { getByRole } = render(<Dropdown />)
      const list = getByRole("listbox")
      expect(list.style.position).toBe("fixed")
      expect(list.style.minWidth).toBe("140px")
    } finally {
      HTMLElement.prototype.getBoundingClientRect = real
    }
  })
})
