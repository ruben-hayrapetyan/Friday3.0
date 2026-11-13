// @vitest-environment happy-dom
// Keeping Tab inside an open dialog (the audit, 12 Nov: the integration panel had no focus trap): where Tab goes, what
// it can reach, and when another dialog over this one has the keys.
import { afterEach, describe, expect, it } from "vitest"
import { inAnotherDialog, keepTabInside, tabbable, tabTarget } from "./focusTrap"

afterEach(() => void (document.body.innerHTML = ""))

describe("where Tab goes (tabTarget)", () => {
  const items = ["a", "b", "c"]

  it("lets the browser step between the first and the last", () => {
    expect(tabTarget(items, "a", false)).toBeNull()
    expect(tabTarget(items, "b", false)).toBeNull()
    expect(tabTarget(items, "c", true)).toBeNull()
    expect(tabTarget(items, "b", true)).toBeNull()
  })

  it("goes round: the first after the last, the last before the first", () => {
    expect(tabTarget(items, "c", false)).toBe("a")
    expect(tabTarget(items, "a", true)).toBe("c")
  })

  it("comes back in from outside (or from the dialog itself): Tab to the first, Shift-Tab to the last", () => {
    expect(tabTarget(items, null, false)).toBe("a")
    expect(tabTarget(items, null, true)).toBe("c")
  })

  it("stays on the dialog when there's nothing in it to reach", () => {
    expect(tabTarget([], null, false)).toBe("box")
    expect(tabTarget([], null, true)).toBe("box")
  })

  it("goes nowhere else with only one thing to reach", () => {
    expect(tabTarget(["a"], "a", false)).toBe("a")
    expect(tabTarget(["a"], "a", true)).toBe("a")
  })
})

function dialog(html: string): HTMLElement {
  document.body.innerHTML = `<button id="before">before</button><div id="box" role="dialog" aria-modal="true" tabindex="-1">${html}</div><button id="after">after</button>`
  return document.getElementById("box")!
}

describe("what Tab can reach (tabbable)", () => {
  it("is the links, buttons, fields and tab stops, in order, and nothing outside", () => {
    const box = dialog(`<a href="#x" id="link">l</a><a id="no-href">n</a><button id="b">b</button><input id="i"><select id="s"></select><textarea id="t"></textarea><span tabindex="0" id="stop">s</span><details><summary id="sum">x</summary></details>`)
    expect(tabbable(box).map((e) => e.id)).toEqual(["link", "b", "i", "s", "t", "stop", "sum"])
  })

  it("leaves out what's disabled, hidden, inert or taken out of the order", () => {
    const box = dialog(`<button disabled>d</button><input type="hidden"><span tabindex="-1">n</span><div hidden><button>h</button></div><div inert><button>i</button></div><fieldset disabled><button>f</button></fieldset><button id="ok">ok</button>`)
    expect(tabbable(box).map((e) => e.id)).toEqual(["ok"])
  })

  it("leaves out what isn't shown, and what's folded in a closed <details> (its summary stays)", () => {
    const box = dialog(`<div style="display:none"><button>gone</button></div><details><summary id="closed">more</summary><button>folded</button></details><details open><summary id="open">less</summary><button id="shown">shown</button></details>`)
    expect(tabbable(box).map((e) => e.id)).toEqual(["closed", "open", "shown"])
  })
})

describe("keeping Tab inside (keepTabInside)", () => {
  const tab = (shift = false) => new KeyboardEvent("keydown", { key: "Tab", shiftKey: shift, cancelable: true })

  it("takes the focus from the last round to the first, and from the first back to the last", () => {
    const box = dialog(`<button id="one">1</button><button id="two">2</button>`)
    document.getElementById("two")!.focus()
    const forward = tab()
    keepTabInside(forward, box)
    expect(forward.defaultPrevented).toBe(true)
    expect(document.activeElement?.id).toBe("one")
    const back = tab(true)
    keepTabInside(back, box)
    expect(back.defaultPrevented).toBe(true)
    expect(document.activeElement?.id).toBe("two")
  })

  it("leaves a step inside to the browser", () => {
    const box = dialog(`<button id="one">1</button><button id="two">2</button>`)
    document.getElementById("one")!.focus()
    const step = tab()
    keepTabInside(step, box)
    expect(step.defaultPrevented).toBe(false)
  })

  it("brings the focus in from outside, and keeps it on an empty dialog", () => {
    let box = dialog(`<button id="one">1</button>`)
    document.getElementById("before")!.focus()
    keepTabInside(tab(true), box)
    expect(document.activeElement?.id).toBe("one")
    box = dialog(`<p>nothing to press</p>`)
    box.focus()
    const step = tab()
    keepTabInside(step, box)
    expect(step.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(box)
  })

  it("does nothing for other keys, or a Tab already handled", () => {
    const box = dialog(`<button id="one">1</button>`)
    document.getElementById("after")!.focus()
    keepTabInside(new KeyboardEvent("keydown", { key: "a", cancelable: true }), box)
    expect(document.activeElement?.id).toBe("after")
    const handled = tab()
    handled.preventDefault()
    keepTabInside(handled, box)
    expect(document.activeElement?.id).toBe("after")
  })
})

describe("another dialog over this one (inAnotherDialog)", () => {
  it("has the keys while the focus is in it", () => {
    document.body.innerHTML = `<div id="under" aria-modal="true"><button id="a">a</button></div><div id="over" aria-modal="true"><button id="b">b</button></div>`
    const under = document.getElementById("under")!
    document.getElementById("b")!.focus()
    expect(inAnotherDialog(under)).toBe(true)
    document.getElementById("a")!.focus()
    expect(inAnotherDialog(under)).toBe(false)
    ;(document.activeElement as HTMLElement).blur()
    expect(inAnotherDialog(under)).toBe(false)
  })
})
