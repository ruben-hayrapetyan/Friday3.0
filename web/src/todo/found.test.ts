import { afterEach, describe, expect, it, vi } from "vitest"
import { FOUND_MS, flashRow, foundHref, listHolding } from "./found"

describe("a task found from its block on the calendar (8 Nov)", () => {
  afterEach(() => vi.useRealTimers())

  it("opens the to-do on that task, asking for the flash", () => {
    expect(foundHref(42)).toBe("/todo?item=42&found=1")
  })

  it("shows it in the list that holds it, and keeps the open one when it's there", () => {
    expect(listHolding({ long_term: true }, "Short term", false)).toBe("Long term")
    expect(listHolding({ long_term: false }, "Long term", false)).toBe("Short term")
    expect(listHolding({}, "Long term", false)).toBe("Short term")
    expect(listHolding({ long_term: true }, "Due", true)).toBe("Due")
  })

  /** A row as the page draws it, enough for the flash: its classes, its style and its scrolling. */
  function page(ids: number[]) {
    const rows = new Map(ids.map((id) => [id, { classes: new Set<string>(), props: new Map<string, string>(), scrolled: vi.fn() }]))
    const root = {
      querySelector: (selector: string) => {
        const id = Number(/data-todo-row="(\d+)"/.exec(selector)?.[1])
        const r = rows.get(id)
        if (!r) return null
        return {
          scrollIntoView: r.scrolled,
          offsetWidth: 0,
          style: { setProperty: (k: string, v: string) => r.props.set(k, v) },
          classList: { add: (c: string) => r.classes.add(c), remove: (c: string) => r.classes.delete(c) },
        } as unknown as HTMLElement
      },
    }
    return { root, rows }
  }

  it("scrolls its row into view and flashes it blue, once, then lets it be", () => {
    vi.useFakeTimers()
    const { root, rows } = page([7, 8])
    expect(flashRow(8, "#2a6c9c", root)).toBe(true)
    const row = rows.get(8)!
    expect(row.scrolled).toHaveBeenCalledWith({ block: "center", behavior: "smooth" })
    expect(row.classes.has("fr-found")).toBe(true)
    expect(row.props.get("--fr-found")).toBe("#2a6c9c")
    expect(rows.get(7)!.classes.size).toBe(0)
    vi.advanceTimersByTime(FOUND_MS)
    expect(row.classes.has("fr-found")).toBe(false)
  })

  it("waits while the row isn't drawn yet", () => {
    expect(flashRow(9, "#2a6c9c", page([7]).root)).toBe(false)
  })
})
