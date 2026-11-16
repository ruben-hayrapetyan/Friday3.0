// @vitest-environment happy-dom
// The source box opens at the suggestion's own words (16 Nov: twelve suggestions from one 20,000-character email each
// showed the email's top, the same for every one, so after Accept or Reject "everything updated besides the black box").
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { Schemas } from "@/api/client"
import { scrollToShow, SourceText } from "./SourceText"

type Suggestion = Schemas["SuggestionOut"]

const filler = (n: number) => Array.from({ length: n }, (_, i) => `Line ${i} of a long email.`).join("\n")
const email = `Subject: Club events\n\n${filler(100)}\nRobotics workshop on Friday at 4pm.\n${filler(200)}\nBake sale on Saturday at noon.\n${filler(50)}`
const suggestion = (id: number, quote: string) => ({ id, source_text: email, quotes: { title: quote }, origin: "Club events\nGmail", source: "Gmail" }) as unknown as Suggestion

// No layout here: a mark's offsetTop is where its words start in the text, scaled to pixels (20px a line).
const lineOf = (el: HTMLElement) => (el.parentElement?.textContent ?? "").slice(0, (el.parentElement?.textContent ?? "").indexOf(el.textContent ?? "")).split("\n").length - 1
const realTop = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetTop")
const realHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetTop", { configurable: true, get() { return lineOf(this) * 20 } })
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get() { return 520 } })
})
afterEach(() => {
  cleanup()
  if (realTop) Object.defineProperty(HTMLElement.prototype, "offsetTop", realTop)
  else delete (HTMLElement.prototype as { offsetTop?: number }).offsetTop
  if (realHeight) Object.defineProperty(HTMLElement.prototype, "clientHeight", realHeight)
  else delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight
})

describe("where the source box scrolls", () => {
  it("puts the words a third of the way down the box", () => {
    expect(scrollToShow(3000, 520)).toBe(3000 - 173)
  })
  it("never above the top, for words near the start", () => {
    expect(scrollToShow(40, 520)).toBe(0)
  })
})

describe("the source box", () => {
  it("opens at this suggestion's words, not the email's top", () => {
    const workshop = suggestion(1, "Robotics workshop on Friday at 4pm")
    render(<SourceText s={workshop} all={[workshop]} />)
    expect(screen.getByLabelText("The source's text").scrollTop).toBe(scrollToShow(102 * 20, 520))
  })
  it("moves to the next suggestion's words from the same email, as Accept or Reject opens it", () => {
    const workshop = suggestion(1, "Robotics workshop on Friday at 4pm")
    const sale = suggestion(2, "Bake sale on Saturday at noon")
    const { rerender } = render(<SourceText s={workshop} all={[workshop, sale]} />)
    const box = screen.getByLabelText("The source's text")
    const first = box.scrollTop
    rerender(<SourceText s={sale} all={[workshop, sale]} />)
    expect(box.scrollTop).toBe(scrollToShow(303 * 20, 520))
    expect(box.scrollTop).toBeGreaterThan(first)
  })
  it("starts at the top when Friday found none of its words in the text", () => {
    const lost = suggestion(3, "words that aren't there")
    render(<SourceText s={lost} all={[lost]} />)
    expect(screen.getByLabelText("The source's text").scrollTop).toBe(0)
  })
})
