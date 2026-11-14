// Nothing painted past its box (14 Nov: in the Google card the Terminal paragraph ran under the Gmail card, whose last
// line sat on its edge; the calendars table's "Edit here" column stood past its panel; its "Per event" menus were too
// big for what they hold). Where a cause can be said without laying the page out, it's held here; the layout itself is
// checked by web/scripts/overflow-check.mjs in a real browser.
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { MenuChoice } from "@/components/fr/controls"
import { DueCount } from "@/plan/DueCount"

// Read from disk: vitest hands CSS imports over empty.
const root = join(__dirname, "..")
const read = (path: string) => readFileSync(join(root, path), "utf8")
const css = read("theme/friday.css")

/** The declarations of the rule whose selector is exactly `selector` (the first such, outside any @-rule's own). */
function rule(selector: string, text = css): Record<string, string> {
  const at = text.search(new RegExp(`(^|\\n|\\})\\s*${selector.replace(/[.*+?^${}()|[\]\\>]/g, "\\$&")}\\s*\\{`))
  if (at < 0) throw new Error(`no rule for ${selector}`)
  const body = text.slice(text.indexOf("{", at) + 1, text.indexOf("}", at + 1))
  return Object.fromEntries(
    body
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split(";")
      .map((d) => d.split(":").map((p) => p.trim()))
      .filter(([k, v]) => k && v)
      .map(([k, v]) => [k, v]),
  )
}

/** The text of the @container block that starts with `head`. */
function container(head: string): string {
  const at = css.indexOf(head)
  if (at < 0) throw new Error(`no ${head}`)
  let depth = 0
  for (let i = css.indexOf("{", at); i < css.length; i++) {
    if (css[i] === "{") depth++
    if (css[i] === "}" && --depth === 0) return css.slice(at, i + 1)
  }
  throw new Error(`${head} isn't closed`)
}

describe("a dialog taller than the window (glass box)", () => {
  it("scrolls, and never squeezes its parts shorter than what's in them", () => {
    expect(rule(".fr-dialog")["overflow-y"]).toBe("auto")
    expect(rule(".fr-dialog > *")["flex-shrink"]).toBe("0")
  })
})

describe("a dropdown's button (glass box)", () => {
  const options = [
    { value: "auto", label: "Per event" },
    { value: "Assignment", label: "Assignment" },
    { value: "Event", label: "Event" },
  ]
  const html = renderToStaticMarkup(<MenuChoice options={options} value="Event" />)

  it("lays every option's words in one cell, so it is as wide as the longest and keeps that width", () => {
    expect(html.match(/<span/g)).toHaveLength(4) // the cell and an option each
    expect(html).toContain('data-label="Per event"')
    expect(html).toContain('data-label="Assignment"')
    expect(rule(".fr-menu-choice > span")["grid-area"]).toBe("1 / 1")
    expect(rule(".fr-menu-choice > span[data-label]::before").content).toBe("attr(data-label)")
  })

  it("shows only the chosen one as words: the page, a search of it and a screen reader have only it", () => {
    expect(html).toMatch(/<span data-chosen="">Event<\/span>/)
    expect(html.match(/aria-hidden="true"/g)).toHaveLength(2)
    expect(html).not.toContain(">Per event<") // the others aren't text (a test's getByText found a kind twice)
    expect(rule(".fr-menu-choice > span:not([data-chosen])").visibility).toBe("hidden")
  })

  it("says a value that isn't among the options as it is", () => {
    expect(renderToStaticMarkup(<MenuChoice options={options} value="Lab" />)).toMatch(/<span data-chosen="">Lab<\/span>/)
  })

  it("has no width of its own, ends in … if its row is narrower, and is a switch's height", () => {
    const button = rule(".fr-menu-button")
    expect(button["min-width"]).toBeUndefined()
    expect(button["max-width"]).toBe("100%")
    expect(rule(".fr-menu-choice > span")["text-overflow"]).toBe("ellipsis")
    const [top, , bottom = top] = button.padding.split(" ").map((p) => Number.parseFloat(p))
    expect(top + bottom + Number.parseFloat(button["line-height"])).toBe(Number.parseFloat(rule(".fr-switch").height))
  })

  it("is the one the pigment menu uses too, with no width of its own", () => {
    const pigments = read("settings/CalendarsSection.tsx")
    expect(pigments).toContain("<MenuChoice")
    expect(pigments).not.toMatch(/fr-menu-button[^>]*minWidth/)
  })
})

describe("the calendars table (glass box)", () => {
  const table = read("settings/Calendars.tsx")

  it("is one grid whose rows are subgrids, its columns as wide as their heads or controls", () => {
    expect(table).not.toMatch(/gridTemplateColumns/) // the fixed 36+150+150+72+72px no panel under 528px could hold
    expect(rule(".fr-cal-grid")["grid-template-columns"]).toBe("36px minmax(0, 1fr) auto auto auto")
    expect(rule(".fr-cal-row")["grid-template-columns"]).toBe("subgrid")
    expect(rule(".fr-cal")["container-type"]).toBe("inline-size")
  })

  it("in a narrow panel puts the name on a line of its own and the controls under the heads", () => {
    const narrow = container("@container (max-width: 460px)")
    expect(rule(".fr-cal-row > .fr-cal-name", narrow)["grid-column"]).toBe("2 / -1")
    for (const part of ["kind", "skip", "edit"]) expect(rule(`.fr-cal-row > .fr-cal-${part}`, narrow)["grid-row"]).toBe("2")
  })

  it("gives every row's parts their column", () => {
    for (const part of ["name", "kind", "skip", "edit"]) expect(table.match(new RegExp(`className="fr-cal-${part}"`, "g"))?.length).toBeGreaterThanOrEqual(2) // the head and the row
  })
})

describe("a settings card's body (glass box)", () => {
  it("is indented past the icon, but not on a phone, where the indent would leave too little room", () => {
    expect(read("settings/Integrations.tsx")).not.toContain("paddingLeft: 50")
    expect(rule(".fr-card-body")["padding-left"]).toBe("50px")
    expect(css).toMatch(/@media \(max-width: 560px\) \{\s*\.fr-card-body \{\s*padding-left: 0;/)
  })
})

describe("the plan's blocks and a month's days (glass box)", () => {
  it("end a block's time line in … rather than cutting it", () => {
    const line = read("plan/Pieces.tsx").slice(read("plan/Pieces.tsx").indexOf("function TimeLine"))
    expect(line.slice(0, line.indexOf("\n}\n"))).toMatch(/whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"/)
  })

  it("in a day too narrow for them, drop a thing's time and the word 'due', keeping the title and the count", () => {
    const month = read("plan/MonthView.tsx")
    expect(month).toContain("repeat(${weeks.length}, minmax(min-content, 1fr))") // a week never shorter than its fullest day
    expect(month).toMatch(/className="fr-row" style=\{\{ display: "grid", gridTemplateColumns: "repeat\(7, minmax\(0,1fr\)\)", minHeight: 132 \}\}/)
    expect(month).toContain('className="fr-hover-accent fr-month-day"')
    expect(month).toContain('className="tnum fr-month-time"')
    expect(rule(".fr-month-day")["container-type"]).toBe("inline-size")
    const narrow = container("@container (max-width: 96px)")
    expect(narrow).toMatch(/\.fr-month-time,\s*\.fr-month-day \.fr-due-word \{\s*display: none;/)
    const html = renderToStaticMarkup(<DueCount dues={[{ item_id: 1, title: "CS A4", due: "2026-11-05T23:59" }]} onPick={() => {}} />)
    expect(html).toContain('<span class="tnum">1<span class="fr-due-word"> due</span></span>')
  })
})
