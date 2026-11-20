// @vitest-environment happy-dom
// A dropdown's list, fixed over the page, is at least as wide as its button and no wider than its choices need (16 Nov,
// IMG 4240: the stylesheet's `min-width: 100%` meant the window once the list was fixed, and an event's Category list
// ran across the whole bottom of the screen, its left edge cut off).
import { cleanup, render } from "@testing-library/react"
import { useRef } from "react"
import { afterEach, describe, expect, it } from "vitest"
import { useMenuPlace } from "./menuPlace"

afterEach(cleanup)

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
      // 20 Nov, a user's notes: a list longer than its height ran out of it (the Breaks panel): it scrolls instead
      expect(list.style.overflowY).toBe("auto")
      expect(list.style.maxHeight).toBe("280px")
    } finally {
      HTMLElement.prototype.getBoundingClientRect = real
    }
  })
})

// 20 Nov, the user: "the scroll for the dropdown is bad". New exam's focus list, longer than its height, never scrolled:
// every scroll, its own too, placed it again, clearing its height to measure it, and the browser put a list as tall as
// its choices back at its top. Here a list scrolls as a browser's does: only while it's held to a height.
describe("a long dropdown list", () => {
  function scrollingAsABrowser() {
    const real = HTMLElement.prototype.getBoundingClientRect
    const tops = new WeakMap<HTMLElement, number>()
    const held = (el: HTMLElement) => el.style.maxHeight !== ""
    const top = Object.getOwnPropertyDescriptor(Element.prototype, "scrollTop")
    Object.defineProperty(HTMLElement.prototype, "scrollTop", {
      configurable: true,
      get(this: HTMLElement) {
        return tops.get(this) ?? 0
      },
      set(this: HTMLElement, v: number) {
        tops.set(this, this.getAttribute("role") === "listbox" && held(this) ? v : 0)
      },
    })
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      if (this.getAttribute("role") === "listbox" && !held(this)) tops.set(this, 0) // laid out as tall as its choices
      return this.tagName === "BUTTON" ? new DOMRect(900, 380, 140, 32) : new DOMRect(0, 0, 0, 0)
    }
    return () => {
      HTMLElement.prototype.getBoundingClientRect = real
      if (top) Object.defineProperty(HTMLElement.prototype, "scrollTop", top)
      else delete (HTMLElement.prototype as { scrollTop?: number }).scrollTop
    }
  }

  it("stays where you scroll it", () => {
    const restore = scrollingAsABrowser()
    try {
      const { getByRole } = render(<Dropdown />)
      const list = getByRole("listbox")
      list.scrollTop = 120
      list.dispatchEvent(new Event("scroll"))
      expect(list.scrollTop).toBe(120)
    } finally {
      restore()
    }
  })

  it("keeps its place when the page scrolls under it", () => {
    const restore = scrollingAsABrowser()
    try {
      const { getByRole } = render(<Dropdown />)
      const list = getByRole("listbox")
      list.scrollTop = 120
      document.dispatchEvent(new Event("scroll"))
      expect(list.scrollTop).toBe(120)
      expect(list.style.maxHeight).toBe("280px")
    } finally {
      restore()
    }
  })
})
