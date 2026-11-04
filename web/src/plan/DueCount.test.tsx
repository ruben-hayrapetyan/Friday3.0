import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { DueCount, dueCountLabel } from "./DueCount"

const due = (item_id: number, title: string, at: string) => ({ item_id, title, due: at })

describe("a day's deadlines in its header", () => {
  const html = renderToStaticMarkup(<DueCount dues={[due(1, "CS A4", "2026-11-05T23:59"), due(2, "Chem PS 10", "2026-11-05T00:00")]} onPick={() => {}} />)

  it("is one red button saying how many, closed until clicked", () => {
    expect(html.match(/<button/g)).toHaveLength(1)
    expect(html).toContain('class="fr-due-count"')
    expect(html).toContain("2 due")
    expect(html).toMatch(/aria-expanded="false"/)
    expect(html).toMatch(/aria-haspopup="menu"/)
  })

  it("names what's due for a screen reader and on hover", () => {
    expect(html).toContain('aria-label="2 due: CS A4, Chem PS 10"')
    expect(html).toContain('title="Due: CS A4, Chem PS 10"')
  })

  it("shows nothing on a day with nothing due", () => {
    expect(renderToStaticMarkup(<DueCount dues={[]} onPick={() => {}} />)).toBe("")
  })

  it("counts in words", () => {
    expect(dueCountLabel(1)).toBe("1 due")
    expect(dueCountLabel(12)).toBe("12 due")
  })
})
